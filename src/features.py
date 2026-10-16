"""Feature computation: SQL window features plus pandas statistics."""

import logging
from pathlib import Path

import pandas as pd
import numpy as np

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