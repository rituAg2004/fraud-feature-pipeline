"""Raw ingestion: load CSV files into raw_transactions exactly as they arrive."""
import hashlib
import csv
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

from src.config import DB_PATH, REFERENCE_DIR, SAMPLE_DIR, SCHEMA_PATH

log = logging.getLogger(__name__)

SOURCE_COLUMNS = ["txn_id", "customer_id", "ts", "amount", "merchant_category", "city", "channel"]

def connect(db_path=DB_PATH):
    """Open the SQLite database, creating the data folder if needed."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def init_db(conn):
    """Create every table from sql/01_schema.sql. Safe to run again."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def sha256_of_file(path):
    """Return the SHA-256 fingerprint of a file as a 64-character hex string."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def now_utc():
    """Current UTC time as text, for the audit columns."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ingest_file(conn, path):
    """Load one CSV into raw_transactions. Returns the rows loaded, or 0 if the file was skipped."""
    path = Path(path)
    name = path.name
    digest = sha256_of_file(path)

    seen = conn.execute(
        "SELECT sha256 FROM ingested_files WHERE file_name = ?", (name,)
    ).fetchone()
    if seen is not None:
        if seen[0] == digest:
            log.info("%s: skipped (already ingested)", name)
        else:
            log.warning("%s: same name but content changed, not loaded", name)
        return 0

    # dtype=str keeps every value as text, so a bad value never breaks the load.
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    loaded_at = now_utc()
    records = [
        (name, *values, loaded_at)
        for values in df[SOURCE_COLUMNS].itertuples(index=False, name=None)
    ]

    # One transaction: if anything fails, nothing is saved.
    with conn:
        conn.executemany(
            "INSERT INTO raw_transactions (source_file, txn_id, customer_id, ts, amount, "
            "merchant_category, city, channel, ingested_at) VALUES (?,?,?,?,?,?,?,?,?)",
            records,
        )
        conn.execute(
            "INSERT INTO ingested_files (file_name, sha256, row_count, loaded_at) VALUES (?,?,?,?)",
            (name, digest, len(records), loaded_at),
        )
    log.info("%s: loaded %d rows", name, len(records))
    return len(records)

def read_csv_rows(path):
    """Read a small CSV into a list of dictionaries."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_reference_tables(conn):
    """Load city_coords, gen_customers and eval_ground_truth. Safe to run again."""
    cities = read_csv_rows(REFERENCE_DIR / "city_coords.csv")
    customers = read_csv_rows(SAMPLE_DIR / "customers.csv")
    truth = read_csv_rows(SAMPLE_DIR / "ground_truth.csv")
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO city_coords (city, lat, lon) VALUES (?,?,?)",
            [(r["city"], float(r["lat"]), float(r["lon"])) for r in cities],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO gen_customers (customer_id, home_city, typical_spend) VALUES (?,?,?)",
            [(r["customer_id"], r["home_city"], float(r["typical_spend"])) for r in customers],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO eval_ground_truth (txn_id, is_fraud, fraud_type) VALUES (?,?,?)",
            [(r["txn_id"], int(r["is_fraud"]), r["fraud_type"]) for r in truth],
        )
    log.info("reference tables: %d cities, %d customers, %d ground-truth rows",
             len(cities), len(customers), len(truth))


def main(files=None):
    """Load every transaction CSV (or the given files), then the reference tables."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    conn = connect()
    init_db(conn)
    paths = files or sorted(SAMPLE_DIR.glob("transactions_*.csv"))
    for p in paths:
        ingest_file(conn, p)
    load_reference_tables(conn)
    total = conn.execute("SELECT COUNT(*) FROM raw_transactions").fetchone()[0]
    log.info("raw_transactions now has %d rows", total)
    conn.close()


if __name__ == "__main__":
    main()