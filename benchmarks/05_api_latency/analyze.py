#!/usr/bin/env python3
"""Experiment 05: latency percentiles per scenario, with bootstrap confidence intervals.

Reads the raw CSV written by measure.sh (one row per request) and prints one
summary row per scenario to stdout.

Usage: python3 analyze.py results/latency_YYYYMMDD_HHMMSS.csv > results/latency_YYYYMMDD_HHMMSS_summary.csv
"""
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import stats  # noqa: E402

# The median alone hides the slow requests a user notices, hence the high percentiles.
# Reference: Dean and Barroso (2013), The Tail at Scale.
PERCENTILES = (50, 90, 95, 99)


def load_runs(csv_path):
    """Group the request rows by (scenario, run)."""
    runs = defaultdict(list)
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            runs[(row["scenario"], int(row["run"]))].append(row)
    return runs


def summarise(runs):
    """Merge the runs of each scenario, splitting first requests, the rest and errors.

    Returns:
        {scenario: {"first": [ms], "rest": [ms], "errors": int, "codes": {code: count}}}.
        Only 200 responses enter "first" and "rest".
    """
    by_scenario = defaultdict(lambda: {"first": [], "rest": [], "errors": 0, "codes": defaultdict(int)})
    for (scenario, _), rows in runs.items():
        rows.sort(key=lambda r: int(r["seq"]))
        agg = by_scenario[scenario]
        for i, row in enumerate(rows):
            agg["codes"][row["code"]] += 1
            if row["code"] != "200":
                agg["errors"] += 1
                continue
            # The first request of each run pays the TLS handshake and, in the
            # warm scenarios, the only cache miss: it is reported apart.
            (agg["first"] if i == 0 else agg["rest"]).append(float(row["latency_ms"]))
    return by_scenario


def main(csv_path):
    """Print the summary CSV: nearest-rank percentiles and their 95 % bootstrap intervals.

    Reference: Hyndman and Fan (1996), Sample Quantiles in Statistical Packages (definition 1).
    Reference: Efron and Tibshirani (1993), An Introduction to the Bootstrap (percentile interval).
    """
    rng = random.Random(stats.SEED)
    header = ["scenario", "n", "errors", "codes", "first_median_ms"]
    for p in PERCENTILES:
        header += [f"p{p}_ms", f"p{p}_ci95_low", f"p{p}_ci95_high"]
    header.append("max_ms")
    print(",".join(header))

    for scenario, agg in summarise(load_runs(csv_path)).items():
        rest = sorted(agg["rest"])
        first = sorted(agg["first"])
        codes = " ".join(f"{c}:{k}" for c, k in sorted(agg["codes"].items()))
        row = [scenario, str(len(rest)), str(agg["errors"]), codes,
               f"{stats.percentile(first, 50):.1f}" if first else ""]
        # A bootstrap needs at least two values to resample.
        if len(rest) >= 2:
            ci =stats.ci95_percentiles(rest, PERCENTILES, rng)
            for p in PERCENTILES:
                row += [f"{stats.percentile(rest, p):.1f}", f"{ci[p][0]:.1f}", f"{ci[p][1]:.1f}"]
            row.append(f"{rest[-1]:.1f}")
        print(",".join(row))


if __name__ == "__main__":
    main(sys.argv[1])
