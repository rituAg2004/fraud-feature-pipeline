"""Cleaning: split raw rows into clean and quarantine, remove duplicates.

Cleaning rules. One row gets only the FIRST reason that fails, checked in
this order:

1. txn_id is empty                         -> NULL_TXN_ID
2. customer_id is empty                    -> NULL_CUSTOMER
3. amount is empty or not a number         -> NULL_AMOUNT
4. amount is zero or negative              -> NON_POSITIVE_AMOUNT
5. ts is not exactly YYYY-MM-DD HH:MM:SS   -> BAD_TIMESTAMP
   (all timestamps are assumed to be UTC)
6. Valid rows get city cleaned: trim spaces, collapse repeated spaces,
   title case (' delhi' becomes 'Delhi'). An unknown city is still valid;
   the location rule will skip it later.
7. Among valid rows with the same txn_id, keep the one with the lowest
   raw_id; the rest count as duplicates_removed. If a txn_id already
   exists in clean_transactions from an earlier load, it is ignored and
   counted the same way.
"""


import re
import logging
import pandas as pd
from datetime import datetime, timezone

log = logging.getLogger(__name__)

TS_FORMAT = "%Y-%m-%d %H:%M:%S"
TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def normalise_city(city):
    """Trim, collapse repeated spaces, title case. ' delhi' -> 'Delhi'."""
    return " ".join(str(city).split()).title()


def validate_row(row):
    """Return the first failing reason for a raw row dict, or None if valid."""
    if not str(row.get("txn_id", "")).strip():
        return "NULL_TXN_ID"
    if not str(row.get("customer_id", "")).strip():
        return "NULL_CUSTOMER"

    amount_text = str(row.get("amount", "")).strip()
    if not amount_text:
        return "NULL_AMOUNT"
    try:
        amount = float(amount_text)
    except ValueError:
        return "NULL_AMOUNT"
    if amount != amount:  # NaN check
        return "NULL_AMOUNT"
    if amount <= 0:
        return "NON_POSITIVE_AMOUNT"

    ts_text = str(row.get("ts", "")).strip()
    if not TS_PATTERN.match(ts_text):
        return "BAD_TIMESTAMP"
    try:
        datetime.strptime(ts_text, TS_FORMAT)
    except ValueError:
        return "BAD_TIMESTAMP"

    return None


SOURCE_COLS = ["txn_id", "customer_id", "ts", "amount",
               "merchant_category", "city", "channel"]


def split_raw(conn):
    """Read raw rows, return (valid_df, invalid_df); rebuild quarantine table."""
    raw = pd.read_sql_query(
        "SELECT raw_id, source_file, " + ", ".join(SOURCE_COLS)
        + " FROM raw_transactions ORDER BY raw_id",
        conn,
    )
    reasons = raw.apply(lambda r: validate_row(r.to_dict()), axis=1)
    invalid = raw[reasons.notna()].copy()
    invalid["reason"] = reasons[reasons.notna()]
    valid = raw[reasons.isna()].copy()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        (r.source_file, r.txn_id, r.customer_id, r.ts, r.amount,
         r.merchant_category, r.city, r.channel, r.reason, now)
        for r in invalid.itertuples(index=False)
    ]
    with conn:
        conn.execute("DELETE FROM quarantine_transactions")
        conn.executemany(
            "INSERT INTO quarantine_transactions "
            "(source_file, txn_id, customer_id, ts, amount, "
            " merchant_category, city, channel, reason, quarantined_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    log.info("split raw: %d valid, %d quarantined", len(valid), len(invalid))
    return valid, invalid


def load_clean(conn, valid):
    """Dedupe valid rows by txn_id and insert into clean_transactions.

    Returns (rows_inserted, duplicates_removed).
    """
    df = valid.sort_values("raw_id").drop_duplicates("txn_id", keep="first").copy()
    dup_in_batch = len(valid) - len(df)

    df["city"] = df["city"].apply(normalise_city)
    df["amount"] = df["amount"].astype(float)
    parsed = pd.to_datetime(df["ts"], format=TS_FORMAT, utc=True)
    df["ts_epoch"] = (parsed - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = list(zip(
        df["txn_id"].tolist(), df["customer_id"].tolist(), df["ts"].tolist(),
        df["ts_epoch"].astype(int).tolist(), df["amount"].tolist(),
        df["merchant_category"].tolist(), df["city"].tolist(),
        df["channel"].tolist(), df["source_file"].tolist(), [now] * len(df),
    ))

    with conn:
        before = conn.execute("SELECT COUNT(*) FROM clean_transactions").fetchone()[0]
        conn.executemany(
            "INSERT OR IGNORE INTO clean_transactions "
            "(txn_id, customer_id, ts, ts_epoch, amount, merchant_category, "
            " city, channel, source_file, loaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        after = conn.execute("SELECT COUNT(*) FROM clean_transactions").fetchone()[0]

    inserted = after - before
    ignored_existing = len(df) - inserted
    duplicates_removed = dup_in_batch + ignored_existing
    log.info("clean load: %d inserted, %d duplicates removed", inserted, duplicates_removed)
    return inserted, duplicates_removed