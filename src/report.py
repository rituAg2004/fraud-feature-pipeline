"""Report outputs: flagged transaction list and rule coverage table."""
import logging
from src.config import load_rules
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")

FLAGGED_REPORT_SQL = """
SELECT s.txn_id, c.customer_id, c.ts, c.amount, c.city,
       s.score, s.band, s.triggered_rules,
       e.explanation_text AS explanation, e.source
FROM scores s
JOIN clean_transactions c ON c.txn_id = s.txn_id
LEFT JOIN explanations e ON e.txn_id = s.txn_id
WHERE s.band IN ('MEDIUM', 'HIGH')
ORDER BY s.score DESC, s.txn_id
"""


def write_flagged_report(conn, out_dir=OUTPUT_DIR) -> int:
    """Write every MEDIUM/HIGH transaction to flagged_report.csv; return the row count."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_sql_query(FLAGGED_REPORT_SQL, conn)
    path = out_dir / "flagged_report.csv"
    df.to_csv(path, index=False)
    logger.info("wrote %d flagged rows to %s", len(df), path)
    return len(df)


COVERAGE_SQL = """
SELECT g.fraud_type, g.is_fraud, COUNT(*) AS n,
       SUM(s.band IN ('MEDIUM', 'HIGH')) AS flagged,
       {rule_columns}
FROM scores s
JOIN eval_ground_truth g ON g.txn_id = s.txn_id
GROUP BY g.fraud_type, g.is_fraud
ORDER BY g.is_fraud DESC, g.fraud_type
"""


def write_rule_coverage(conn, out_dir=OUTPUT_DIR) -> Path:
    """Write rule_coverage.md: per fraud_type, how many rows each rule fired on."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rule_names = list(load_rules()["rules"].keys())
    rule_columns = ", ".join(
        f"SUM(COALESCE(s.triggered_rules, '') LIKE '%{name}%') AS {name}"
        for name in rule_names
    )
    df = pd.read_sql_query(COVERAGE_SQL.format(rule_columns=rule_columns), conn)

    header = ["fraud_type", "is_fraud", "transactions", "flagged"] + rule_names
    lines = [
        "# Rule coverage (sanity check, not accuracy)",
        "",
        "Labels come from our own synthetic generator, so this only shows which "
        "rule catches which injected pattern.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]
    for r in df.itertuples(index=False):
        cells = [r.fraud_type, r.is_fraud, r.n, r.flagged] + [
            getattr(r, name) for name in rule_names
        ]
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")

    clean = df[df["is_fraud"] == 0]
    lines += [
        "",
        f"Not-fraud transactions that were still flagged: "
        f"{int(clean['flagged'].sum())} of {int(clean['n'].sum())}.",
    ]

    path = out_dir / "rule_coverage.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("wrote rule coverage to %s", path)
    return path