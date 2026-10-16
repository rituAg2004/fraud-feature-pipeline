"""Rule-based scoring: turns a feature row into points, rules and a band."""

import logging

import pandas as pd

from datetime import datetime, timezone

from src.config import load_rules

logger = logging.getLogger(__name__)


def _has(value):
    """True if value is a real number (not None or NaN)."""
    return value is not None and not pd.isna(value)


def score_row(row, cfg):
    """Return (points, fired_rule_names) for one feature row."""
    rules = cfg["rules"]
    points = 0
    fired = []

    r = rules["VELOCITY"]
    if _has(row["txn_count_1h"]) and row["txn_count_1h"] >= r["threshold"]:
        points += r["points"]
        fired.append("VELOCITY")

    r = rules["UNUSUAL_AMOUNT"]
    if (
        _has(row["amount_robust_z"])
        and row["history_count"] >= cfg["min_history"]
        and row["amount_robust_z"] > r["threshold"]
    ):
        points += r["points"]
        fired.append("UNUSUAL_AMOUNT")

    r = rules["IMPOSSIBLE_TRAVEL"]
    if (
        _has(row["distance_km"])
        and _has(row["speed_kmh"])
        and row["distance_km"] >= r["min_distance_km"]
        and row["speed_kmh"] > r["speed_kmh"]
    ):
        points += r["points"]
        fired.append("IMPOSSIBLE_TRAVEL")

    return min(points, 100), fired


def band_for(score, cfg):
    """Map a 0-100 score to LOW, MEDIUM or HIGH using bands from config."""
    if score >= cfg["bands"]["high"]:
        return "HIGH"
    if score >= cfg["bands"]["medium"]:
        return "MEDIUM"
    return "LOW"


def build_scores(conn, cfg=None):
    """Score every row of the features table and store results; return row count."""
    cfg = cfg or load_rules()
    df = pd.read_sql_query("SELECT * FROM features", conn)
    scored_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    rows = []
    for row in df.to_dict("records"):
        points, fired = score_row(row, cfg)
        rows.append((
            row["txn_id"],
            points,
            band_for(points, cfg),
            ",".join(fired),
            cfg["rules_version"],
            scored_at,
        ))

    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO scores "
            "(txn_id, score, band, triggered_rules, rules_version, scored_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    logger.info("stored %d scores", len(rows))
    return len(rows)