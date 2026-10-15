"""Tests for the cleaning step: duplicates and invalid rows."""
from src.clean import split_raw, load_clean
from tests.conftest import insert_raw


def test_duplicate_txn_id_keeps_one(conn):
    insert_raw(conn, [
        ("TXN1", "C001", "2026-09-01 10:00:00", "500", "grocery", "Delhi", "POS"),
        ("TXN1", "C001", "2026-09-01 10:00:00", "500", "grocery", "Delhi", "POS"),
        ("TXN2", "C001", "2026-09-01 11:00:00", "300", "fuel", "Delhi", "POS"),
    ])

    valid, invalid = split_raw(conn)
    inserted, duplicates_removed = load_clean(conn, valid)

    clean_count = conn.execute("SELECT COUNT(*) FROM clean_transactions").fetchone()[0]
    assert clean_count == 2
    assert duplicates_removed == 1