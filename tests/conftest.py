"""Shared pytest fixtures: an empty in-memory database and a raw-row helper."""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMA_PATH = ROOT / "sql" / "01_schema.sql"


@pytest.fixture
def conn():
    """Fresh in-memory SQLite database with the full schema."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    yield connection
    connection.close()


def insert_raw(conn, rows, source_file="test.csv"):
    """Insert hand-made rows into raw_transactions.

    Each row is a tuple of 7 text values:
    (txn_id, customer_id, ts, amount, merchant_category, city, channel)
    """
    conn.executemany(
        "INSERT INTO raw_transactions "
        "(source_file, txn_id, customer_id, ts, amount, "
        " merchant_category, city, channel, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '2026-01-01 00:00:00')",
        [(source_file, *row) for row in rows],
    )
    conn.commit()