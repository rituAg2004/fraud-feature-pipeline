"""Synthetic data generator. A fixed seed makes the output identical on every run."""
import argparse
import csv
import random
from pathlib import Path
import numpy as np
from collections import Counter
from datetime import datetime, timedelta
import math

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

COORDS = {name: (lat, lon) for name, lat, lon in CITIES}

START = datetime(2026, 9, 1)
END = datetime(2026, 9, 15)          # 14 days: 1 to 14 September
TXNS_PER_CUSTOMER = 30
HOME_CITY_PROB = 0.93
TRIP_GAP_HOURS = 12                  # changing city needs a gap of at least 12 hours

CATEGORIES = ["grocery", "fuel", "dining", "transport", "electronics", "clothing", "pharmacy"]
CATEGORY_WEIGHTS = [0.30, 0.15, 0.20, 0.15, 0.05, 0.10, 0.05]
CHANNELS = ["POS", "online", "ATM"]
CHANNEL_WEIGHTS = [0.35, 0.55, 0.10]

SPLIT_AT = datetime(2026, 9, 13)     # first 12 days go to load 1, last 2 days to load 2
TXN_COLUMNS = ["txn_id", "customer_id", "ts", "amount", "merchant_category", "city", "channel"]
BAD_TS = ["31-13-2026", "not a date", "2026/09/05 10:00"]


def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line distance in km between two points on Earth."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


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



def inject_card_testing(py_rng, np_rng, txns, customers, used, n=6):
    """Add a burst of 6 to 8 small online purchases (99 to 299) within 25 minutes for n customers."""
    home = {c["customer_id"]: c["home_city"] for c in customers}
    eligible = [c["customer_id"] for c in customers if c["customer_id"] not in used]
    new_rows = []
    sizes = []
    for cid in py_rng.sample(eligible, n):
        used.add(cid)
        own = [t for t in txns if t["customer_id"] == cid]
        # Start after a home-city purchase, only once 6 earlier transactions exist,
        # and early enough that the burst stays inside the period.
        spots = [k for k in range(6, len(own))
                 if own[k]["city"] == home[cid] and own[k]["ts"] + timedelta(hours=2) < END]
        anchor = own[py_rng.choice(spots)]
        start = anchor["ts"] + timedelta(seconds=py_rng.randint(300, 3600))
        size = py_rng.randint(6, 8)
        for offset in sorted(py_rng.sample(range(0, 1501), size)):
            new_rows.append({
                "customer_id": cid,
                "ts": start + timedelta(seconds=offset),
                "amount": round(float(np_rng.uniform(99, 299)), 2),
                "merchant_category": py_rng.choices(CATEGORIES, weights=CATEGORY_WEIGHTS)[0],
                "city": home[cid],
                "channel": "online",
                "is_fraud": 1,
                "fraud_type": "card_testing",
            })
        sizes.append(size)
    txns.extend(new_rows)
    print(f"card_testing: {n} customers, burst sizes {sizes}, {len(new_rows)} rows added")


def inject_impossible_travel(py_rng, np_rng, txns, customers, used, n=8):
    """Add one normal-sized purchase 800+ km away, 10 to 30 minutes after an earlier one."""
    spend = {c["customer_id"]: c["typical_spend"] for c in customers}
    eligible = [c["customer_id"] for c in customers if c["customer_id"] not in used]
    new_rows, dists, gaps = [], [], []
    for cid in py_rng.sample(eligible, len(eligible)):
        if len(new_rows) == n:
            break
        own = sorted((t for t in txns if t["customer_id"] == cid), key=lambda t: t["ts"])
        # Anchor = the previous transaction. It needs 5 before it (so the new one has 6 earlier),
        # the next normal one must be 12+ hours later, and the period must not end too soon.
        spots = []
        for k in range(5, len(own)):
            last = k == len(own) - 1
            if (last or own[k + 1]["ts"] - own[k]["ts"] >= timedelta(hours=12)) \
                    and own[k]["ts"] + timedelta(hours=1) < END:
                spots.append(k)
        if not spots:
            continue
        used.add(cid)
        anchor = own[py_rng.choice(spots)]
        lat1, lon1 = COORDS[anchor["city"]]
        far = [c for c in CITY_NAMES
               if haversine_km(lat1, lon1, *COORDS[c]) >= 800]
        city = py_rng.choice(far)
        gap = py_rng.randint(600, 1800)
        new_rows.append({
            "customer_id": cid,
            "ts": anchor["ts"] + timedelta(seconds=gap),
            "amount": round(spend[cid] * float(np_rng.uniform(0.6, 1.4)), 2),
            "merchant_category": py_rng.choices(CATEGORIES, weights=CATEGORY_WEIGHTS)[0],
            "city": city,
            "channel": py_rng.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0],
            "is_fraud": 1,
            "fraud_type": "impossible_travel",
        })
        dists.append(round(haversine_km(lat1, lon1, *COORDS[city])))
        gaps.append(round(gap / 60))
    txns.extend(new_rows)
    print(f"impossible_travel: {len(new_rows)} customers, distances km {dists}, gaps min {gaps}")


def inject_large_amount(py_rng, np_rng, txns, customers, used, n=8):
    """Add one purchase of 15 to 40 times typical spend, in the home city at a normal hour."""
    home = {c["customer_id"]: c["home_city"] for c in customers}
    spend = {c["customer_id"]: c["typical_spend"] for c in customers}
    eligible = [c["customer_id"] for c in customers if c["customer_id"] not in used]
    new_rows, ratios = [], []
    for cid in py_rng.sample(eligible, len(eligible)):
        if len(new_rows) == n:
            break
        own = sorted((t for t in txns if t["customer_id"] == cid), key=lambda t: t["ts"])
        # Anchor = an earlier home-city purchase between 09:00 and 19:59, with 5 before it.
        # The next normal purchase must also be at home, so no accidental fast city change appears.
        spots = []
        for k in range(5, len(own)):
            next_at_home = k == len(own) - 1 or own[k + 1]["city"] == home[cid]
            if own[k]["city"] == home[cid] and next_at_home \
                    and 9 <= own[k]["ts"].hour <= 19 \
                    and own[k]["ts"] + timedelta(hours=2) < END:
                spots.append(k)
        if not spots:
            continue
        used.add(cid)
        anchor = own[py_rng.choice(spots)]
        ratio = float(np_rng.uniform(15, 40))
        new_rows.append({
            "customer_id": cid,
            "ts": anchor["ts"] + timedelta(seconds=py_rng.randint(300, 3600)),
            "amount": round(spend[cid] * ratio, 2),
            "merchant_category": py_rng.choices(CATEGORIES, weights=CATEGORY_WEIGHTS)[0],
            "city": home[cid],
            "channel": py_rng.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0],
            "is_fraud": 1,
            "fraud_type": "large_amount",
        })
        ratios.append(round(ratio, 1))
    txns.extend(new_rows)
    print(f"large_amount: {len(new_rows)} customers, amount / typical_spend = {ratios}")


def assign_txn_ids(txns):
    """Sort all transactions by time and give each an id like T000001."""
    txns.sort(key=lambda t: (t["ts"], t["customer_id"], t["amount"]))
    for i, t in enumerate(txns, start=1):
        t["txn_id"] = f"T{i:06d}"


def write_ground_truth(path, txns):
    """Write the answer key: txn_id, is_fraud, fraud_type for every transaction."""
    rows = [(t["txn_id"], t["is_fraud"], t["fraud_type"]) for t in txns]
    write_csv(path, ["txn_id", "is_fraud", "fraud_type"], rows)
    counts = Counter(t["fraud_type"] for t in txns)
    print(f"ground truth: {len(rows)} rows, {dict(sorted(counts.items()))}")


def make_source_rows(txns):
    """Turn transactions into text rows (7 columns). Remember which load each row belongs to."""
    rows = []
    for t in txns:
        rows.append({
            "txn_id": t["txn_id"],
            "customer_id": t["customer_id"],
            "ts": t["ts"].strftime("%Y-%m-%d %H:%M:%S"),
            "amount": f"{t['amount']:.2f}",
            "merchant_category": t["merchant_category"],
            "city": t["city"],
            "channel": t["channel"],
            "_normal": t["fraud_type"] == "normal",
            "_load": 1 if t["ts"] < SPLIT_AT else 2,
        })
    return rows


def inject_quality_problems(py_rng, rows):
    """Damage some ordinary rows on purpose. Each damaged row gets exactly one problem."""
    n = len(rows)
    counts = {
        "duplicates": round(0.02 * n),
        "null_customer": round(0.005 * n),
        "null_amount": round(0.005 * n),
        "non_positive_amount": round(0.005 * n),
        "bad_timestamp": round(0.005 * n),
        "city_variant": round(0.02 * n),
    }
    candidates = [i for i, r in enumerate(rows) if r["_normal"]]
    py_rng.shuffle(candidates)
    chosen, pos = {}, 0
    for name, k in counts.items():
        chosen[name] = candidates[pos:pos + k]
        pos += k

    for i in chosen["null_customer"]:
        rows[i]["customer_id"] = ""
    for i in chosen["null_amount"]:
        rows[i]["amount"] = ""
    for i in chosen["non_positive_amount"]:
        rows[i]["amount"] = py_rng.choice(["0", "0.00", "-" + rows[i]["amount"]])
    for i in chosen["bad_timestamp"]:
        rows[i]["ts"] = py_rng.choice(BAD_TS)
    for i in chosen["city_variant"]:
        city = rows[i]["city"]
        rows[i]["city"] = py_rng.choice(
            [city.lower(), city.upper(), " " + city, city + " ", "  " + city.lower()]
        )
    # Exact copies of untouched rows (same txn_id), placed in the same load as the original.
    rows.extend(dict(rows[i]) for i in chosen["duplicates"])
    print("quality problems added:", {k: len(v) for k, v in chosen.items()})


def write_transaction_files(py_rng, out_dir, rows):
    """Shuffle each load and write transactions_day1.csv and transactions_day2.csv."""
    for load in (1, 2):
        part = [r for r in rows if r["_load"] == load]
        py_rng.shuffle(part)
        write_csv(
            out_dir / f"transactions_day{load}.csv",
            TXN_COLUMNS,
            [[r[c] for c in TXN_COLUMNS] for r in part],
        )
        print(f"transactions_day{load}.csv: {len(part)} rows")


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

    used = {t["customer_id"] for t in txns if t["fraud_type"] != "normal"}
    inject_card_testing(py_rng, np_rng, txns, customers, used)
    inject_impossible_travel(py_rng, np_rng, txns, customers, used)
    inject_large_amount(py_rng, np_rng, txns, customers, used)
    assign_txn_ids(txns)
    write_ground_truth(out_dir / "ground_truth.csv", txns)

    rows = make_source_rows(txns)
    inject_quality_problems(py_rng, rows)
    write_transaction_files(py_rng, out_dir, rows)

if __name__ == "__main__":
    main()