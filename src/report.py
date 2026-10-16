"""Report outputs: flagged transaction list and rule coverage table."""
import logging
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