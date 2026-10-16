"""T10: the detector must not read generator-only tables."""
from src.features import build_features
from src.scoring import build_scores


def seed_clean(conn):
    """Six small Delhi purchases, then 5000 in Mumbai 20 minutes later."""
    conn.executemany(
        "INSERT INTO city_coords (city, lat, lon) VALUES (?, ?, ?)",
        [("Delhi", 28.61, 77.21), ("Mumbai", 19.08, 72.88)],
    )
    base = 1789000000
    rows = []
    for i in range(6):
        rows.append((f"A{i}", "C001", "2026-09-10 09:00:00", base + i * 3600,
                     199.0, "Delhi"))
    rows.append(("A6", "C001", "2026-09-10 15:20:00", base + 5 * 3600 + 1200,
                 5000.0, "Mumbai"))
    conn.executemany(
        "INSERT INTO clean_transactions "
        "(txn_id, customer_id, ts, ts_epoch, amount, merchant_category, "
        " city, channel, source_file, loaded_at) "
        "VALUES (?, ?, ?, ?, ?, 'grocery', ?, 'POS', 'test.csv', "
        " '2026-01-01 00:00:00')",
        rows,
    )
    conn.commit()


def seed_generator_tables(conn):
    """Fill the tables that only the generator and the report may use."""
    conn.execute("INSERT INTO gen_customers (customer_id, home_city, typical_spend) "
                 "VALUES ('C001', 'Delhi', 199.0)")
    conn.execute("INSERT INTO eval_ground_truth (txn_id, is_fraud, fraud_type) "
                 "VALUES ('A6', 1, 'impossible_travel')")
    conn.commit()


def run_detector(conn):
    """Compute features and scores; return the comparable columns."""
    build_features(conn)
    build_scores(conn)
    return conn.execute(
        "SELECT txn_id, score, band, triggered_rules FROM scores ORDER BY txn_id"
    ).fetchall()


def test_detector_independent_of_generator_tables(conn):
    """T10: emptying gen_customers and eval_ground_truth changes no score."""
    seed_clean(conn)
    seed_generator_tables(conn)
    with_tables = run_detector(conn)

    conn.execute("DELETE FROM gen_customers")
    conn.execute("DELETE FROM eval_ground_truth")
    conn.commit()
    without_tables = run_detector(conn)

    assert len(with_tables) == 7
    assert any(score > 0 for _, score, _, _ in with_tables)
    assert with_tables == without_tables