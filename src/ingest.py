"""Raw ingestion: load CSV files into raw_transactions exactly as they arrive."""
import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

from src.config import DB_PATH, SCHEMA_PATH

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