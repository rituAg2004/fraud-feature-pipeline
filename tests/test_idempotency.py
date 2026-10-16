"""Test that running ingest + clean twice changes nothing."""
from src.clean import split_raw, load_clean
from src.ingest import ingest_file

CSV_TEXT = (
    "txn_id,customer_id,ts,amount,merchant_category,city,channel\n"
    "TXN1,C001,2026-09-01 10:00:00,500,grocery,Delhi,POS\n"
    "TXN1,C001,2026-09-01 10:00:00,500,grocery,Delhi,POS\n"
    "TXN2,C001,2026-09-01 11:00:00,300,fuel, delhi,POS\n"
    "TXN3,,2026-09-01 12:00:00,200,fuel,Delhi,POS\n"
    "TXN4,C001,2026-09-01 13:00:00,-50,fuel,Delhi,POS\n"
)

STABLE_QUERIES = {
    "raw": "SELECT source_file, txn_id, customer_id, ts, amount, city "
           "FROM raw_transactions ORDER BY raw_id",
    "clean": "SELECT txn_id, customer_id, ts, ts_epoch, amount, city "
             "FROM clean_transactions ORDER BY txn_id",
    "quarantine": "SELECT txn_id, reason FROM quarantine_transactions "
                  "ORDER BY txn_id",
    "files": "SELECT file_name, sha256, row_count FROM ingested_files "
             "ORDER BY file_name",
}


def snapshot(conn):
    """Return the sorted contents of the main tables (without timestamps)."""
    return {name: conn.execute(q).fetchall() for name, q in STABLE_QUERIES.items()}


def run_pipeline(conn, csv_path):
    """Ingest one file and clean it. Returns (rows_loaded, inserted, dups)."""
    loaded = ingest_file(conn, csv_path)
    valid, _ = split_raw(conn)
    inserted, dups = load_clean(conn, valid)
    return loaded, inserted, dups


def test_rerun_is_idempotent(conn, tmp_path):
    csv_path = tmp_path / "transactions_test.csv"
    csv_path.write_text(CSV_TEXT, encoding="utf-8")

    loaded1, inserted1, _ = run_pipeline(conn, csv_path)
    after_first = snapshot(conn)

    loaded2, inserted2, _ = run_pipeline(conn, csv_path)
    after_second = snapshot(conn)

    assert loaded1 == 5 and inserted1 == 2
    assert loaded2 == 0 and inserted2 == 0
    assert after_first == after_second
    assert len(after_first["clean"]) == 2
    assert len(after_first["quarantine"]) == 2