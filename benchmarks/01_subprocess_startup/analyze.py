#!/usr/bin/env python3
"""Experiment 01: statistical summary of the subprocess startup cost.

Reads the raw CSV written by measure.sh and prints one summary row per
measurement to stdout: first repetition, median, quartiles and a 95 %
bootstrap interval of the median.

Usage: python3 analyze.py results/startup_YYYYMMDD_HHMMSS.csv > results/startup_YYYYMMDD_HHMMSS_summary.csv
"""
import csv
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# Makes benchmarks/lib/stats.py importable without installing it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import stats  # noqa: E402


def main(csv_path):
    """Group the raw rows by measurement and print the summary CSV.

    Medians and quartiles rather than means: a few slow spawns cannot move them.
    Reference: Hoefler and Belli (2015), Scientific Benchmarking of Parallel Computing Systems.
    """
    series = defaultdict(list)
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            series[row["measurement"]].append((int(row["repetition"]), float(row["ms"])))

    rng = random.Random(stats.SEED)
    print("measurement,n,first_ms,median_ms,p25_ms,p75_ms,ci95_low_ms,ci95_high_ms")
    for measurement, rows in series.items():
        # Tuples sort by repetition number first, so rows[0] is the first run.
        rows.sort()
        # The first repetition pays the cold page cache, so it is reported apart.
        # Reference: Jain (1991), The Art of Computer Systems Performance Analysis (transient removal).
        first = rows[0][1]
        rest = [ms for _, ms in rows[1:]]
        # statistics.quantiles needs at least two values.
        if len(rest) < 2:
            print(f"{measurement},{len(rest)},{first:.0f},,,,,")
            continue
        # Default "exclusive" method, which interpolates, unlike stats.percentile.
        # See https://docs.python.org/3/library/statistics.html
        p25, _, p75 = statistics.quantiles(rest, n=4)
        low, high = stats.ci95(rest, statistics.median, rng)
        print(f"{measurement},{len(rest)},{first:.0f},{statistics.median(rest):.0f},"
              f"{p25:.0f},{p75:.0f},{low:.0f},{high:.0f}")


if __name__ == "__main__":
    main(sys.argv[1])
