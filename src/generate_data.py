"""Synthetic data generator. A fixed seed makes the output identical on every run."""
import argparse
import csv
import random
from pathlib import Path
import numpy as np
from collections import Counter
from datetime import datetime, timedelta

from src.config import REFERENCE_DIR, SAMPLE_DIR

SEED = 42
N_CUSTOMERS = 150

# Real latitude and longitude of 12 Indian cities.
CITIES = [
    ("Delhi", 28.6139, 77.2090),
    ("Mumbai", 19.0760, 72.8777),
    ("Bengaluru", 12.9716, 77.5946),
    ("Kolkata", 22.5726, 88.3639),
    ("Chennai", 13.0827, 80.2707),
    ("Hyderabad", 17.3850, 78.4867),
    ("Pune", 18.5204, 73.8567),
    ("Ahmedabad", 23.0225, 72.5714),
    ("Jaipur", 26.9124, 75.7873),
    ("Lucknow", 26.8467, 80.9462),
    ("Chandigarh", 30.7333, 76.7794),
    ("Kochi", 9.9312, 76.2673),
]
CITY_NAMES = [c[0] for c in CITIES]

START = datetime(2026, 9, 1)
END = datetime(2026, 9, 15)          # 14 days: 1 to 14 September
TXNS_PER_CUSTOMER = 30
HOME_CITY_PROB = 0.93
TRIP_GAP_HOURS = 12                  # changing city needs a gap of at least 12 hours

CATEGORIES = ["grocery", "fuel", "dining", "transport", "electronics", "clothing", "pharmacy"]
CATEGORY_WEIGHTS = [0.30, 0.15, 0.20, 0.15, 0.05, 0.10, 0.05]
CHANNELS = ["POS", "online", "ATM"]
CHANNEL_WEIGHTS = [0.35, 0.55, 0.10]


def write_csv(path, header, rows):
    """Write rows to a CSV file with fixed line endings, so output is the same on every OS."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def make_customers(py_rng, np_rng, n=N_CUSTOMERS):
    """Return n customers, each with a home city and a typical spend (skewed, 150 to 5000)."""
    spends = np.clip(np_rng.lognormal(mean=6.7, sigma=0.9, size=n), 150, 5000)
    customers = []
    for i in range(n):
        customers.append({
            "customer_id": f"C{i + 1:03d}",
            "home_city": py_rng.choice(CITY_NAMES),
            "typical_spend": round(float(spends[i]), 2),
        })
    return customers


def pick_times(np_rng, n, span):
    """Pick n random second-offsets inside the period, at most 2 per clock hour."""
    per_hour = {}
    times = []
    while len(times) < n:
        t = int(np_rng.integers(0, span))
        hour = t // 3600
        if per_hour.get(hour, 0) >= 2:
            continue
        per_hour[hour] = per_hour.get(hour, 0) + 1
        times.append(t)
    return sorted(times)


def make_normal_transactions(py_rng, np_rng, customers):
    """Return normal transactions as dicts (no txn_id yet). Spend and travel stay plausible."""
    span = int((END - START).total_seconds())
    txns = []
    for cust in customers:
        others = [c for c in CITY_NAMES if c != cust["home_city"]]
        prev_city, prev_t = None, None
        for t in pick_times(np_rng, TXNS_PER_CUSTOMER, span):
            if py_rng.random() < HOME_CITY_PROB:
                wanted = cust["home_city"]
            else:
                wanted = py_rng.choice(others)
            # Changing city is allowed only if the previous transaction is 12+ hours old.
            if prev_city is not None and wanted != prev_city and (t - prev_t) < TRIP_GAP_HOURS * 3600:
                city = prev_city
            else:
                city = wanted
            factor = float(np_rng.uniform(0.6, 1.4))
            txns.append({
                "customer_id": cust["customer_id"],
                "ts": START + timedelta(seconds=t),
                "amount": round(cust["typical_spend"] * factor, 2),
                "merchant_category": py_rng.choices(CATEGORIES, weights=CATEGORY_WEIGHTS)[0],
                "city": city,
                "channel": py_rng.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0],
                "is_fraud": 0,
                "fraud_type": "normal",
            })
            prev_city, prev_t = city, t
    return txns

def add_legit_large(py_rng, np_rng, txns, customers, n=5):
    """Turn n ordinary purchases into legitimate large ones (about 15x typical spend)."""
    spend = {c["customer_id"]: c["typical_spend"] for c in customers}
    ratios = []
    for cust in py_rng.sample(customers, n):
        own = [t for t in txns if t["customer_id"] == cust["customer_id"]]
        # Skip the first 10, so the customer already has history for the amount baseline.
        row = own[py_rng.randrange(10, len(own))]
        row["amount"] = round(spend[cust["customer_id"]] * float(np_rng.uniform(14, 16)), 2)
        row["is_fraud"] = 0
        row["fraud_type"] = "legit_large"
        ratios.append(round(row["amount"] / spend[cust["customer_id"]], 1))
    print(f"legit_large: {n} rows, amount / typical_spend = {ratios}")


def summarize(txns, customers):
    """Print quick checks on the generated transactions."""
    home = {c["customer_id"]: c["home_city"] for c in customers}
    at_home = sum(1 for t in txns if t["city"] == home[t["customer_id"]])
    per_hour = Counter(
        (t["customer_id"], int((t["ts"] - START).total_seconds()) // 3600) for t in txns
    )
    bad_trips = sum(
        1 for a, b in zip(txns, txns[1:])
        if a["customer_id"] == b["customer_id"] and a["city"] != b["city"]
        and (b["ts"] - a["ts"]).total_seconds() < TRIP_GAP_HOURS * 3600
    )
    print(f"{len(txns)} transactions, {at_home / len(txns):.1%} in home city")
    print(f"max per customer-hour: {max(per_hour.values())}, city changes under 12h: {bad_trips}")
    print(f"first: {min(t['ts'] for t in txns)}, last: {max(t['ts'] for t in txns)}")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic transactions.")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--out", default=str(SAMPLE_DIR))
    args = parser.parse_args()

    py_rng = random.Random(args.seed)
    np_rng = np.random.default_rng(args.seed)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    write_csv(REFERENCE_DIR / "city_coords.csv", ["city", "lat", "lon"], CITIES)

    customers = make_customers(py_rng, np_rng)
    write_csv(
        out_dir / "customers.csv",
        ["customer_id", "home_city", "typical_spend"],
        [(c["customer_id"], c["home_city"], c["typical_spend"]) for c in customers],
    )
    print(f"Wrote {len(CITIES)} cities and {len(customers)} customers (seed={args.seed})")

    txns = make_normal_transactions(py_rng, np_rng, customers)
    add_legit_large(py_rng, np_rng, txns, customers)
    summarize(txns, customers)


if __name__ == "__main__":
    main()