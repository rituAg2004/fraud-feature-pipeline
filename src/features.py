"""Feature computation: SQL window features plus pandas statistics."""

import logging
from pathlib import Path

import pandas as pd
import numpy as np

from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def load_sql_features(conn):
    """Run sql/02_features.sql and return a DataFrame sorted by customer and time."""
    sql = (SQL_DIR / "02_features.sql").read_text(encoding="utf-8")
    df = pd.read_sql_query(sql, conn)
    df = df.sort_values(["customer_id", "ts_epoch", "txn_id"]).reset_index(drop=True)
    logger.info("loaded %d rows from SQL features", len(df))
    return df


EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Return great-circle distance in km between points (works on arrays)."""
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = phi2 - phi1
    dlmb = np.radians(lon2) - np.radians(lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def add_location_features(df, coords):
    """Add minutes_since_prev, distance_km and speed_kmh; NaN if unknown."""
    out = df.copy()
    c = coords.set_index("city")

    out["lat"] = out["city"].map(c["lat"])
    out["lon"] = out["city"].map(c["lon"])
    out["prev_lat"] = out["prev_city"].map(c["lat"])
    out["prev_lon"] = out["prev_city"].map(c["lon"])

    known = set(c.index)
    cities = set(out["city"].dropna()) | set(out["prev_city"].dropna())
    unknown = sorted(cities - known)
    if unknown:
        logger.warning("cities missing from city_coords: %s", unknown)

    out["minutes_since_prev"] = (out["ts_epoch"] - out["prev_epoch"]) / 60
    out["distance_km"] = haversine_km(
        out["prev_lat"], out["prev_lon"], out["lat"], out["lon"]
    )
    minutes = out["minutes_since_prev"].clip(lower=1)
    out["speed_kmh"] = out["distance_km"] / (minutes / 60)

    return out.drop(columns=["lat", "lon", "prev_lat", "prev_lon"])


def _mad(values):
    """Median absolute deviation of a 1-D array, ignoring NaN."""
    med = np.nanmedian(values)
    return np.nanmedian(np.abs(values - med))


def add_amount_baseline(df, window=50, min_history=5):
    """Add history_count, baseline_median, baseline_mad from earlier amounts only."""
    out = df.sort_values(["customer_id", "ts_epoch", "txn_id"]).copy()
    earlier = out.groupby("customer_id")["amount"].shift(1)
    out["_earlier"] = earlier

    grouped = out.groupby("customer_id")["_earlier"]
    out["history_count"] = (
        grouped.rolling(window, min_periods=1).count().reset_index(level=0, drop=True)
    )
    out["baseline_median"] = (
        grouped.rolling(window, min_periods=min_history).median().reset_index(level=0, drop=True)
    )
    out["baseline_mad"] = (
        grouped.rolling(window, min_periods=min_history)
        .apply(_mad, raw=True)
        .reset_index(level=0, drop=True)
    )
    out["history_count"] = out["history_count"].fillna(0).astype(int)
    return out.drop(columns=["_earlier"]).sort_index()


def robust_z(amount, median, mad, history=None):
    """Return robust z-score of amount; NaN if no baseline is available."""
    if np.isnan(median) or np.isnan(mad):
        return np.nan
    if mad > 0:
        scale = 1.4826 * mad
    else:
        scale = 0.0
        if history is not None and len(history) > 0:
            h = np.asarray(history, dtype=float)
            h = h[~np.isnan(h)]
            if len(h) > 0:
                scale = 1.253314 * np.mean(np.abs(h - median))
        if scale == 0:
            scale = max(0.1 * median, 1.0)
    return (amount - median) / scale


FEATURE_COLUMNS = [
    "txn_id", "customer_id", "ts_epoch", "amount",
    "txn_count_1h", "history_count", "baseline_median", "baseline_mad",
    "amount_robust_z", "prev_city", "minutes_since_prev",
    "distance_km", "speed_kmh", "computed_at",
]


def build_features(conn, window=50, min_history=5):
    """Compute all features, store them in the features table, return row count."""
    df = load_sql_features(conn)
    coords = pd.read_sql_query("SELECT city, lat, lon FROM city_coords", conn)

    df = add_location_features(df, coords)
    df = add_amount_baseline(df, window=window, min_history=min_history)

    # df is sorted by customer and time, so cumcount() is the position
    # of each row inside its customer's history.
    amounts_by_customer = {
        cid: g["amount"].to_numpy() for cid, g in df.groupby("customer_id")
    }
    position = df.groupby("customer_id").cumcount()

    z_values = []
    for a, m, d, cid, pos in zip(
        df["amount"], df["baseline_median"], df["baseline_mad"],
        df["customer_id"], position,
    ):
        history = None
        if not np.isnan(d) and d == 0:
            history = amounts_by_customer[cid][max(0, pos - window):pos]
        z_values.append(robust_z(a, m, d, history))
    df["amount_robust_z"] = z_values

    df["computed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    out = df[FEATURE_COLUMNS].astype(object)
    out = out.where(df[FEATURE_COLUMNS].notna(), None)
    placeholders = ",".join("?" * len(FEATURE_COLUMNS))
    sql = (
        f"INSERT OR REPLACE INTO features ({','.join(FEATURE_COLUMNS)}) "
        f"VALUES ({placeholders})"
    )
    with conn:
        conn.executemany(sql, out.itertuples(index=False, name=None))
    logger.info("stored %d feature rows", len(out))
    return len(out)