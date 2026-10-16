"""Tests for rule scoring."""
from src.features import build_features
from src.scoring import build_scores
from tests.test_features import insert_clean, BASE


def _rules_for(conn, txn_id):
    """Return (score, triggered_rules) for one transaction."""
    return conn.execute(
        "SELECT score, triggered_rules FROM scores WHERE txn_id = ?", (txn_id,)
    ).fetchone()


def test_impossible_travel(conn):
    """Delhi then Mumbai in 20 minutes fires; in 10 hours it does not."""
    rows = [
        ("A0", "C3", BASE, 500.0, "Delhi"),
        ("A1", "C3", BASE + 20 * 60, 500.0, "Mumbai"),
        ("B0", "C4", BASE, 500.0, "Delhi"),
        ("B1", "C4", BASE + 10 * 3600, 500.0, "Mumbai"),
    ]
    insert_clean(conn, rows)

    build_features(conn)
    build_scores(conn)

    assert _rules_for(conn, "A1") == (40, "IMPOSSIBLE_TRAVEL")
    assert _rules_for(conn, "B1") == (0, "")

    speed_b = conn.execute(
        "SELECT speed_kmh FROM features WHERE txn_id = 'B1'"
    ).fetchone()[0]
    assert 100 < speed_b < 130