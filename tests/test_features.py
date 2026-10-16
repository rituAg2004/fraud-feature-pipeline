"""Tests for feature computation (velocity, cold start, MAD zero)."""
from src.config import load_rules
from src.features import build_features
from src.scoring import build_scores

BASE = 1_788_000_000  # an arbitrary epoch second used as 10:00 in tests


def insert_clean(conn, rows):
    """Insert hand-made rows into clean_transactions.

    Each row is a tuple: (txn_id, customer_id, ts_epoch, amount, city).
    """
    conn.executemany(
        "INSERT INTO clean_transactions "
        "(txn_id, customer_id, ts, ts_epoch, amount, merchant_category, "
        " city, channel, source_file, loaded_at) "
        "VALUES (?, ?, 'x', ?, ?, 'grocery', ?, 'online', 'test.csv', 'x')",
        rows,
    )
    conn.executemany(
        "INSERT OR REPLACE INTO city_coords (city, lat, lon) VALUES (?, ?, ?)",
        [("Delhi", 28.6139, 77.2090), ("Mumbai", 19.0760, 72.8777)],
    )
    conn.commit()


def test_velocity_counts_last_hour(conn):
    """Six transactions in 25 minutes count 1..6; a later one counts 1."""
    rows = [
        (f"T{i}", "C1", BASE + i * 300, 199.0, "Delhi")  # every 5 minutes
        for i in range(6)
    ]
    rows.append(("T6", "C1", BASE + 25 * 60 + 2 * 3600, 199.0, "Delhi"))
    insert_clean(conn, rows)

    build_features(conn)
    build_scores(conn)

    counts = [
        r[0] for r in conn.execute(
            "SELECT txn_count_1h FROM features ORDER BY ts_epoch, txn_id"
        )
    ]
    assert counts == [1, 2, 3, 4, 5, 6, 1]

    score, band, rules = conn.execute(
        "SELECT score, band, triggered_rules FROM scores WHERE txn_id = 'T4'"
    ).fetchone()
    assert (score, band, rules) == (40, "MEDIUM", "VELOCITY")


def test_cold_start_no_crash(conn):
    """First transaction with a huge amount: NULL features, score 0, no crash."""
    insert_clean(conn, [("T0", "C9", BASE, 90000.0, "Delhi")])

    build_features(conn)
    build_scores(conn)

    z, hist, speed, dist, prev_city = conn.execute(
        "SELECT amount_robust_z, history_count, speed_kmh, distance_km, prev_city "
        "FROM features WHERE txn_id = 'T0'"
    ).fetchone()
    assert z is None
    assert hist == 0
    assert speed is None
    assert dist is None
    assert prev_city is None

    score, band, rules = conn.execute(
        "SELECT score, band, triggered_rules FROM scores WHERE txn_id = 'T0'"
    ).fetchone()
    assert (score, band, rules) == (0, "LOW", "")