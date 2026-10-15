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
from datetime import datetime

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