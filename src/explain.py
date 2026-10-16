"""AI explanation layer: prompt, template fallback, validator, storage."""
import logging
import math
import numbers
import re
from datetime import datetime, timezone

import pandas as pd

from src.config import load_rules
from src.llm_client import LLMUnavailable

logger = logging.getLogger(__name__)

# Which feature values matter for which rule (only these go into the prompt).
RULE_FACTS = {
    "VELOCITY": ["txn_count_1h"],
    "UNUSUAL_AMOUNT": ["baseline_median", "amount_robust_z"],
    "IMPOSSIBLE_TRAVEL": ["prev_city", "minutes_since_prev", "distance_km", "speed_kmh"],
}


def _fmt(value) -> str:
    """Format a fact for the prompt: floats to 1 decimal, everything else as text."""
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _is_missing(value) -> bool:
    """True for None and NaN."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def fired_rules(row: dict) -> list:
    """Turn the comma-separated triggered_rules string into a list."""
    text = row.get("triggered_rules") or ""
    return [r for r in text.split(",") if r]


def build_prompt(row: dict, rules: dict) -> str:
    """Take one scored row (dict) and the rules config; return the LLM prompt text."""
    fired = fired_rules(row)
    lines = [
        f"amount: {_fmt(row['amount'])}",
        f"city: {row['city']}",
        f"score: {row['score']}",
        f"band: {row['band']}",
        f"fired rules: {', '.join(fired)}",
    ]
    for rule in fired:
        for feature in RULE_FACTS.get(rule, []):
            value = row.get(feature)
            if not _is_missing(value):
                lines.append(f"{feature}: {_fmt(value)}")
    if "VELOCITY" in fired:
        lines.append(f"window_minutes: {rules['window_minutes']}")

    facts = "\n".join(lines)
    return (
        "You help a fraud analyst. Below are facts about one flagged transaction.\n\n"
        f"{facts}\n\n"
        "Write two short sentences for the analyst.\n"
        "Use only the facts given above.\n"
        "Do not invent numbers, places or causes.\n"
        "Do not say it is certainly fraud."
    )

def _num(value) -> str:
    """Human-friendly number: 48000 -> '48,000', 77.74 -> '77.7', 20.0 -> '20'."""
    value = float(value)
    if abs(value) >= 100:
        return f"{value:,.0f}"
    return f"{value:.1f}".rstrip("0").rstrip(".")


def template_explanation(row: dict, rules: dict) -> str:
    """Take a scored row and rules config; return a fixed-format explanation text."""
    fired = fired_rules(row)
    parts = []
    if "VELOCITY" in fired:
        parts.append(
            f"{int(row['txn_count_1h'])} transactions by this customer "
            f"within {rules['window_minutes']} minutes"
        )
    if "UNUSUAL_AMOUNT" in fired:
        parts.append(
            f"amount {_num(row['amount'])} is far above this customer's "
            f"usual {_num(row['baseline_median'])}"
        )
    if "IMPOSSIBLE_TRAVEL" in fired:
        parts.append(
            f"previous transaction was in {row['prev_city']} "
            f"{_num(row['minutes_since_prev'])} minutes earlier, "
            f"about {_num(row['distance_km'])} km away"
        )
    if not parts:
        parts.append("flagged by the scoring rules")
    text = "; ".join(parts)
    return f"{text[0].upper()}{text[1:]}. Score {row['score']} ({row['band']})."

MAX_EXPLANATION_CHARS = 600
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers_in(obj) -> list:
    """Collect every int/float inside a (nested) dict or list, ignoring bools and NaN."""
    found = []
    if isinstance(obj, dict):
        for value in obj.values():
            found.extend(_numbers_in(value))
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            found.extend(_numbers_in(value))
    elif isinstance(obj, numbers.Real) and not isinstance(obj, bool):
        if not math.isnan(float(obj)):
            found.append(float(obj))
    return found


def allowed_numbers(row: dict, cfg: dict) -> list:
    """Numbers the AI may quote: facts shown in the prompt plus rules.yaml values."""
    facts = [row.get("amount"), row.get("score")]
    for rule in fired_rules(row):
        for feature in RULE_FACTS.get(rule, []):
            facts.append(row.get(feature))
    return _numbers_in(facts) + _numbers_in(cfg)


def validate_explanation(text, row: dict, cfg: dict, known_cities=()):
    """Return (ok, reason). Rejects empty, long, invented-number or wrong-city text."""
    if not text or not text.strip():
        return False, "empty answer"
    if len(text) >= MAX_EXPLANATION_CHARS:
        return False, "answer too long"

    allowed = allowed_numbers(row, cfg)
    for token in NUMBER_RE.findall(text):
        value = float(token.replace(",", ""))
        if not any(math.isclose(value, a, rel_tol=0.01, abs_tol=0.05) for a in allowed):
            return False, f"number not in facts: {token}"

    own_cities = {str(row.get("city", "")).lower(), str(row.get("prev_city", "")).lower()}
    for city in known_cities:
        if city.lower() in own_cities:
            continue
        if re.search(rf"\b{re.escape(city)}\b", text, flags=re.IGNORECASE):
            return False, f"city not in facts: {city}"

    return True, "ok"


FLAGGED_SQL = """
SELECT s.txn_id, s.score, s.band, s.triggered_rules,
       c.customer_id, c.ts, c.amount, c.city,
       f.txn_count_1h, f.baseline_median, f.amount_robust_z,
       f.prev_city, f.minutes_since_prev, f.distance_km, f.speed_kmh
FROM scores s
JOIN features f ON f.txn_id = s.txn_id
JOIN clean_transactions c ON c.txn_id = s.txn_id
LEFT JOIN explanations e ON e.txn_id = s.txn_id
WHERE e.txn_id IS NULL
  AND s.txn_id IN (
      SELECT txn_id FROM scores
      WHERE band IN ('MEDIUM', 'HIGH')
      ORDER BY score DESC, txn_id
      LIMIT ?
  )
ORDER BY s.score DESC, s.txn_id
"""


def explain_flagged(conn, client, cfg=None) -> dict:
    """Explain MEDIUM/HIGH rows that have no explanation yet; return counts by source."""
    cfg = cfg or load_rules()
    max_items = cfg["explain"]["max_items"]
    timeout = cfg["explain"]["timeout_s"]

    rows = pd.read_sql_query(FLAGGED_SQL, conn, params=(max_items,)).to_dict("records")
    known_cities = [r[0] for r in conn.execute("SELECT city FROM city_coords")]

    max_fail = cfg["explain"]["max_consecutive_failures"]
    fail_streak = 0
    counts = {"llm": 0, "fallback": 0}
    for row in rows:
        text, source, model = None, "fallback", "template"
        if fail_streak < max_fail:
            try:
                answer = client.generate(build_prompt(row, cfg), timeout=timeout)
                fail_streak = 0  # LLM answered, even if validator rejects it
                ok, reason = validate_explanation(answer, row, cfg, known_cities)
                if ok:
                    text, source, model = answer.strip(), "llm", client.name
                else:
                    logger.warning("AI answer rejected for %s: %s", row["txn_id"], reason)
            except LLMUnavailable as exc:
                fail_streak += 1
                logger.warning("LLM unavailable for %s: %s", row["txn_id"], exc)
                if fail_streak == max_fail:
                    logger.warning("LLM failed %d times in a row; using template for the rest",
                                   max_fail)

        if text is None:
            text = template_explanation(row, cfg)

        conn.execute(
            "INSERT OR IGNORE INTO explanations "
            "(txn_id, explanation_text, source, model_name, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (row["txn_id"], text, source, model,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
        counts[source] += 1

    logger.info("explained %d rows: %d by llm, %d by fallback",
                len(rows), counts["llm"], counts["fallback"])
    return counts