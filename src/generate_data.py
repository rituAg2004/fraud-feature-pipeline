"""Synthetic data generator. A fixed seed makes the output identical on every run."""
import argparse
import csv
import random
from pathlib import Path

import numpy as np

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


if __name__ == "__main__":
    main()