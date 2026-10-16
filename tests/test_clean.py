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



def test_invalid_rows_quarantined_with_reasons(conn):
    insert_raw(conn, [
        ("TXN1", "C001", "2026-09-01 10:00:00", "500", "grocery", "Delhi", "POS"),
        ("TXN2", "",     "2026-09-01 10:05:00", "500", "grocery", "Delhi", "POS"),
        ("TXN3", "C001", "2026-09-01 10:10:00", "",    "grocery", "Delhi", "POS"),
        ("TXN4", "C001", "2026-09-01 10:15:00", "-50", "grocery", "Delhi", "POS"),
        ("TXN5", "C001", "31-13-2026",          "500", "grocery", "Delhi", "POS"),
    ])

    valid, invalid = split_raw(conn)
    load_clean(conn, valid)

    clean_count = conn.execute("SELECT COUNT(*) FROM clean_transactions").fetchone()[0]
    quarantine_count = conn.execute("SELECT COUNT(*) FROM quarantine_transactions").fetchone()[0]
    reasons = {r[0] for r in conn.execute("SELECT reason FROM quarantine_transactions")}

    assert clean_count == 1
    assert quarantine_count == 4
    assert reasons == {"NULL_CUSTOMER", "NULL_AMOUNT",
                       "NON_POSITIVE_AMOUNT", "BAD_TIMESTAMP"}