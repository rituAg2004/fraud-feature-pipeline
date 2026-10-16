"""Tests for rule scoring."""
from src.features import build_features
from src.config import load_rules
from src.scoring import band_for, build_scores, score_row
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

def test_two_rules_together_give_high():
    """Impossible travel plus unusual amount adds up to 70 points, band HIGH."""
    cfg = load_rules()
    row = {
        "txn_count_1h": 1,
        "history_count": 10,
        "amount_robust_z": 77.7,
        "distance_km": 1150.0,
        "speed_kmh": 3450.0,
    }
    points, fired = score_row(row, cfg)
    assert points == 70
    assert set(fired) == {"IMPOSSIBLE_TRAVEL", "UNUSUAL_AMOUNT"}
    assert band_for(points, cfg) == "HIGH"

    # one rule alone stays MEDIUM
    row["amount_robust_z"] = 0.5
    points, fired = score_row(row, cfg)
    assert points == 40
    assert band_for(points, cfg) == "MEDIUM"