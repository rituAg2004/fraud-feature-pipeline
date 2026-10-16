"""Show why a robust z-score catches fraud that a normal z-score misses."""
import numpy as np

from src.features import _mad, robust_z

earlier = np.array([100, 150, 200, 120, 180, 80000], dtype=float)
current = 15000.0

# Normal z-score: mean and standard deviation (population std).
mean, std = earlier.mean(), earlier.std()
normal_z = (current - mean) / std

# Robust z-score: median and MAD, same function the pipeline uses.
median = float(np.median(earlier))
mad = float(_mad(earlier))
robust = robust_z(current, median, mad)

print(f"Earlier amounts : {earlier.astype(int).tolist()}")
print(f"Current amount  : {current:,.0f}")
print()
print(f"Normal z-score  : mean {mean:,.0f}, std {std:,.0f} -> z = {normal_z:.2f}  (looks normal, MISSED)")
print(f"Robust z-score  : median {median:,.0f}, MAD {mad:,.0f} -> z = {robust:.1f}  (very unusual, CAUGHT)")
print()
print("Why: one big past purchase (80,000) inflates the mean and std,")
print("so the next big amount looks normal. Median and MAD barely move.")