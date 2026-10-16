"""Run the whole pipeline with one command: ingest, clean (more steps later)."""
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.clean import split_raw, load_clean
from src.config import SAMPLE_DIR
from src.ingest import connect, init_db, ingest_file, load_reference_tables

from src.features import build_features
from src.scoring import build_scores

log = logging.getLogger(__name__)


def now_utc():
    """Current UTC time as 'YYYY-MM-DD HH:MM:SS' text."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def start_run(conn):
    """Insert a RUNNING row into pipeline_runs and return its run_id."""
    with conn:
        cur = conn.execute(
            "INSERT INTO pipeline_runs (started_at, status) VALUES (?, 'RUNNING')",
            (now_utc(),),
        )
    return cur.lastrowid


def finish_run(conn, run_id, stats, status="SUCCESS"):
    """Fill the counts and final status for a run.

    stats is a dict with keys: files_loaded, rows_in, rows_clean,
    rows_quarantined, duplicates_removed, flagged_medium, flagged_high.
    Missing keys are stored as 0.
    """
    with conn:
        conn.execute(
            "UPDATE pipeline_runs SET finished_at = ?, status = ?, "
            "files_loaded = ?, rows_in = ?, rows_clean = ?, "
            "rows_quarantined = ?, duplicates_removed = ?, "
            "flagged_medium = ?, flagged_high = ? "
            "WHERE run_id = ?",
            (
                now_utc(), status,
                stats.get("files_loaded", 0), stats.get("rows_in", 0),
                stats.get("rows_clean", 0), stats.get("rows_quarantined", 0),
                stats.get("duplicates_removed", 0),
                stats.get("flagged_medium", 0), stats.get("flagged_high", 0),
                run_id,
            ),
        )

def main(files=None):
    """Run ingest and clean for the given CSV files (default: all samples)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    conn = connect()
    init_db(conn)
    run_id = start_run(conn)
    try:
        paths = [Path(f) for f in files] if files else sorted(
            SAMPLE_DIR.glob("transactions_*.csv"))
        files_loaded = 0
        for p in paths:
            if ingest_file(conn, p) > 0:
                files_loaded += 1
        load_reference_tables(conn)

        rows_in = conn.execute(
            "SELECT COUNT(*) FROM raw_transactions").fetchone()[0]
        valid, invalid = split_raw(conn)
        _, dups = load_clean(conn, valid)
        rows_clean = conn.execute(
            "SELECT COUNT(*) FROM clean_transactions").fetchone()[0]

        build_features(conn)
        build_scores(conn)
        band_counts = dict(conn.execute(
            "SELECT band, COUNT(*) FROM scores GROUP BY band").fetchall())

        stats = {
            "files_loaded": files_loaded, "rows_in": rows_in,
            "rows_clean": rows_clean, "rows_quarantined": len(invalid),
            "duplicates_removed": dups,
            "flagged_medium": band_counts.get("MEDIUM", 0),
            "flagged_high": band_counts.get("HIGH", 0),
        }
        finish_run(conn, run_id, stats)
        log.info("run %d SUCCESS: %s", run_id, stats)
    except Exception:
        finish_run(conn, run_id, {}, status="FAILED")
        log.exception("run %d FAILED", run_id)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the fraud pipeline.")
    parser.add_argument("--files", nargs="+", help="CSV files to load")
    args = parser.parse_args()
    main(args.files)