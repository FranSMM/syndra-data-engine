#!/usr/bin/env python3
"""Hypothesis tests over the raw data of experiments 02 to 05.

Writes two CSVs next to the given prefix: <prefix>_normality.csv with
Shapiro-Wilk for every sample, and <prefix>_mannwhitney.csv with every
comparison, its Holm-adjusted p-value and its effect size.

Usage: venv/bin/python analyze.py results/hypothesis_YYYYMMDD
"""
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from scipy import stats

BENCH = Path(__file__).resolve().parents[1]
ALPHA = 0.05

# Same merge as 02_etl_latency/analyze.py: the extract task was renamed in April 2026.
STAGE_ALIASES = {"Extract Scrapy Spider": "Extract: Generic RSS Spiders"}


def latest_raw(folder, prefix):
    """Return the most recent raw CSV of an experiment.

    The timestamp in the file name makes alphabetical order chronological.
    Summary and environment files are skipped.
    """
    files = [f for f in (BENCH / folder / "results").glob(f"{prefix}_*.csv")
             if not f.stem.endswith(("_summary", "_environment"))]
    return sorted(files)[-1]


def read(path):
    """Read a CSV into a list of dicts, one per row."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def drop_first(rows, rep_field, value_field):
    """Return the measured values without the first repetition.

    The first repetition pays the cold start, so every experiment reports it apart.
    """
    rows = sorted(rows, key=lambda r: int(r[rep_field]))
    return [float(r[value_field]) for r in rows[1:]]


def etl_comparisons(path):
    """Yield one comparison per ETL stage: one feed against three feeds (02)."""
    groups = defaultdict(list)
    for r in read(path):
        if r["state"] != "COMPLETED" or not r["seconds"] or not r["n_feeds"]:
            continue
        stage = STAGE_ALIASES.get(r["stage"], r["stage"])
        groups[(stage, int(r["n_feeds"]))].append(float(r["seconds"]))
    for stage in sorted({s for s, _ in groups}):
        yield "02", stage, "1 feed", groups[(stage, 1)], "3 feeds", groups[(stage, 3)]


def index_comparisons(path):
    """Yield each index variant against no index, per table size and ticker class (03)."""
    groups = defaultdict(list)
    for r in read(path):
        groups[(int(r["table_rows"]), r["variant"], r["ticker_class"])].append(r)
    for (size, variant, ticker), rows in sorted(groups.items()):
        if variant == "baseline":
            continue
        baseline = drop_first(groups[(size, "baseline", ticker)], "rep", "execution_ms")
        yield ("03", f"{size} rows, {ticker} ticker", "baseline", baseline,
               variant, drop_first(rows, "rep", "execution_ms"))


def inference_comparisons(path):
    """Yield each batch size against production, which classifies one text at a time (04)."""
    groups = defaultdict(list)
    for r in read(path):
        groups[(r["mode"], int(r["batch_size"]))].append(r)
    production = drop_first(groups[("production", 1)], "rep", "wall_ms")
    for (mode, batch), rows in sorted(groups.items()):
        if mode != "production":
            yield ("04", "wall time", "production", production,
                   f"batch {batch}", drop_first(rows, "rep", "wall_ms"))


def api_comparisons(path):
    """Yield the cold cache against the warm cache, for each API operation (05)."""
    runs = defaultdict(list)
    for r in read(path):
        runs[(r["scenario"], int(r["run"]))].append(r)
    latency = defaultdict(list)
    for (scenario, _), rows in runs.items():
        rows.sort(key=lambda r: int(r["seq"]))
        # The first request of each run pays the TLS handshake, as in 05_api_latency.
        latency[scenario] += [float(r["latency_ms"]) for r in rows[1:] if r["code"] == "200"]
    for op in ("sentiment", "search"):
        yield "05", op, "warm", latency[f"{op}_warm"], "cold", latency[f"{op}_cold"]


def holm(p_values):
    """Adjust p-values for multiple comparisons with Holm's step-down method.

    The smallest p-value is multiplied by m, the next by m - 1, and so on.
    Reference: Holm (1979), A Simple Sequentially Rejective Multiple Test Procedure.

    Args:
        p_values: raw p-values, in any order.

    Returns:
        Adjusted p-values, in the same order as the input.
    """
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        # max() keeps the adjusted values from decreasing, as the procedure requires.
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def main(prefix):
    sources = {
        "02": latest_raw("02_etl_latency", "etl"),
        "03": latest_raw("03_jsonb_gin", "queries"),
        "04": latest_raw("04_inference_resources", "inference"),
        "05": latest_raw("05_api_latency", "latency"),
    }
    for exp, path in sources.items():
        print(f"{exp}: {path.relative_to(BENCH)}", file=sys.stderr)

    comparisons = [
        *etl_comparisons(sources["02"]),
        *index_comparisons(sources["03"]),
        *inference_comparisons(sources["04"]),
        *api_comparisons(sources["05"]),
    ]

    # A sample can appear in several comparisons (the baseline of 03, production in 04),
    # but it is tested for normality once.
    samples = {}
    for exp, what, label_a, a, label_b, b in comparisons:
        samples[(exp, what, label_a)] = a
        samples[(exp, what, label_b)] = b

    # Shapiro and Wilk (1965); scipy.stats.shapiro.
    with open(f"{prefix}_normality.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["experiment", "group", "condition", "n", "w", "p_value", "normal"])
        rejected = 0
        for (exp, what, label), values in samples.items():
            w, p = stats.shapiro(values)
            rejected += p < ALPHA
            writer.writerow([exp, what, label, len(values), f"{w:.4f}", f"{p:.3g}",
                             "no" if p < ALPHA else "not rejected"])

    # Mann and Whitney (1947); scipy.stats.mannwhitneyu.
    results = []
    for exp, what, label_a, a, label_b, b in comparisons:
        u, p = stats.mannwhitneyu(b, a, alternative="two-sided")
        # U / (n_a * n_b) estimates P(b > a), the common language effect size of
        # McGraw and Wong (1992): 0.5 means no difference.
        results.append([exp, what, label_a, label_b, len(a), len(b),
                        statistics.median(a), statistics.median(b), p, u / (len(a) * len(b))])
    adjusted = holm([r[8] for r in results])

    with open(f"{prefix}_mannwhitney.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["experiment", "group", "a", "b", "n_a", "n_b", "median_a", "median_b",
                         "p_value", "p_holm", "p_b_greater", "significant"])
        for row, p_holm in zip(results, adjusted):
            exp, what, label_a, label_b, n_a, n_b, med_a, med_b, p, prob = row
            writer.writerow([exp, what, label_a, label_b, n_a, n_b, f"{med_a:.3f}", f"{med_b:.3f}",
                             f"{p:.3g}", f"{p_holm:.3g}", f"{prob:.3f}",
                             "yes" if p_holm < ALPHA else "no"])

    significant = sum(p < ALPHA for p in adjusted)
    print(f"normality rejected in {rejected} of {len(samples)} samples", file=sys.stderr)
    print(f"{significant} of {len(results)} comparisons significant after Holm", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])
