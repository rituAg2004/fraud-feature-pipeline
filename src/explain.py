"""AI explanation layer: prompt, template fallback, validator, storage."""
import logging
import math

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