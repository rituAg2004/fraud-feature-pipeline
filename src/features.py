"""Feature computation: SQL window features plus pandas statistics."""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def load_sql_features(conn):
    """Run sql/02_features.sql and return a DataFrame sorted by customer and time."""
    sql = (SQL_DIR / "02_features.sql").read_text(encoding="utf-8")
    df = pd.read_sql_query(sql, conn)
    df = df.sort_values(["customer_id", "ts_epoch", "txn_id"]).reset_index(drop=True)
    logger.info("loaded %d rows from SQL features", len(df))
    return df