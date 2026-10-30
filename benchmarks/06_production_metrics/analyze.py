#!/usr/bin/env python3
"""Experiment 06: production resource use and server-side latency.

Usage: python3 analyze.py results/production_YYYYMMDD_HHMMSS

Reads the CSVs and the environment file that measure.sh wrote under the prefix.
Prints one CSV, question,subject,metric,value,unit, with a block per question.
Samples of a time series are not independent repetitions, so nothing here is
bootstrapped: percentiles are nearest-rank over samples taken at a stated step.
"""
import csv
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import stats  # noqa: E402

MIB = 1024 * 1024
GIB = 1024 * MIB
DAY = 86400
# cAdvisor's housekeeping interval and the scrape interval are both 15 s.
SAMPLE_S = 15
# The scheduler's idle level is taken from 10 to 1 minute before each ETL run.
IDLE_BEFORE_RUN = (600, 60)
# Starts closer than this belong to the same deploy.
DEPLOY_GAP = 600
RETENTION_DAYS = 180  # retention.time=180d in infra/docker-compose.prod.yml.
SIZE_CAP = 10 * GIB  # retention.size=10GB; Prometheus reads GB as GiB.

# Every question writes its rows here, so the whole summary is a single CSV.
out = csv.writer(sys.stdout)


def emit(question, subject, metric, value, unit=""):
    """Write one row of the summary."""
    out.writerow([question, subject, metric, value, unit])


def iso(epoch):
    """Format a Unix timestamp as UTC ISO 8601, to the minute."""
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def read_csv(path):
    """Read a CSV into a list of dicts, one per row."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def number(row, column):
    """Return a cell as a float, or None when Prometheus had no value at that step."""
    return float(row[column]) if row[column] != "" else None


def read_environment(path):
    """Read the "key: value" lines of the environment file into a dict, skipping comments."""
    environment = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if ": " in line and not line.startswith("#"):
            key, value = line.split(": ", 1)
            environment[key] = value
    return environment


# Question 1: resource use against the limits.

def containers(rows, host_memory, period_start):
    """Report each container's memory peak against its limit, its OOM events and its starts.

    Args:
        rows: rows of _containers.csv, one per container and 15-minute step.
        host_memory: host RAM in bytes, the reference for a container without a limit.
        period_start: epoch of the first step; starts before it are not counted.
    """
    by_name = defaultdict(list)
    for row in rows:
        by_name[row["container"]].append(row)

    starts = []  # (start epoch, container name)
    for name, series in sorted(by_name.items()):
        peak = max(series, key=lambda r: number(r, "working_set_bytes") or 0)
        peak_ws = number(peak, "working_set_bytes")
        peak_rss = max(number(r, "rss_bytes") or 0 for r in series)
        # cAdvisor reports 0 when there is no limit, so 0 is dropped like an empty cell.
        # A set, so a limit changed by a deploy shows up as two values.
        limits = {number(r, "limit_bytes") for r in series if number(r, "limit_bytes")}
        oom = max(number(r, "oom_events_total") or 0 for r in series)
        # Each distinct start time is one creation of the container.
        own_starts = sorted({number(r, "start_time") for r in series
                             if number(r, "start_time") and number(r, "start_time") >= period_start})
        starts += [(t, name) for t in own_starts]

        emit("1-containers", name, "peak_working_set", f"{peak_ws / MIB:.0f}", "MiB")
        emit("1-containers", name, "peak_working_set_at", iso(int(peak["timestamp"])))
        emit("1-containers", name, "peak_rss", f"{peak_rss / MIB:.0f}", "MiB")
        if limits:
            limit = max(limits)
            emit("1-containers", name, "limit", f"{limit / MIB:.0f}" + ("" if len(limits) == 1 else " (changed in period)"), "MiB")
            emit("1-containers", name, "peak_working_set_of_limit", f"{100 * peak_ws / limit:.1f}", "%")
        else:
            emit("1-containers", name, "limit", "none")
            emit("1-containers", name, "peak_working_set_of_host", f"{100 * peak_ws / host_memory:.1f}", "%")
        emit("1-containers", name, "oom_events", f"{oom:.0f}")
        emit("1-containers", name, "starts_in_period", len(own_starts))

    # Containers started within minutes of each other were recreated together
    # by a deploy. A start on its own is either a one-service deploy or a crash.
    starts.sort()
    groups = []
    for t, name in starts:
        # Compared with the last start of the group, so a slow deploy stays in one group.
        if groups and t - groups[-1][-1][0] <= DEPLOY_GAP:
            groups[-1].append((t, name))
        else:
            groups.append([(t, name)])
    emit("1-starts", "all", "start_groups", len(groups))
    for group in groups:
        names = sorted({name.removeprefix("syndra_") for _, name in group})
        emit("1-starts", iso(int(group[0][0])), "containers_started", " ".join(names))


def overlaps_run(start, end, runs):
    """Tell whether the interval [start, end] overlaps any (start, end) run."""
    return any(s <= end and start <= e for s, e in runs)


def host(rows, host_memory, etl_runs):
    """Report the host's CPU busy share and its lowest available memory.

    The CPU counters are cumulative seconds, so each minute is the difference of
    two consecutive samples: busy = 1 - idle / total.

    Args:
        rows: rows of _host.csv, one per minute.
        host_memory: host RAM in bytes.
        etl_runs: (start, end) epochs of every ETL run.
    """
    rows = [r for r in rows if r["cpu_idle_seconds"] and r["cpu_total_seconds"]]
    busy = []  # (timestamp, fraction of both cores busy over the minute)
    for previous, current in zip(rows, rows[1:]):
        total = number(current, "cpu_total_seconds") - number(previous, "cpu_total_seconds")
        idle = number(current, "cpu_idle_seconds") - number(previous, "cpu_idle_seconds")
        if total > 0 and idle >= 0:  # a counter reset means a reboot: skip that minute
            busy.append((int(current["timestamp"]), 1 - idle / total))

    values = sorted(b for _, b in busy)
    emit("1-host", "cpu", "samples", len(values), "1-minute averages")
    emit("1-host", "cpu", "busy_median", f"{100 * stats.percentile(values, 50):.1f}", "% of 2 cores")
    emit("1-host", "cpu", "busy_p95", f"{100 * stats.percentile(values, 95):.1f}", "% of 2 cores")
    emit("1-host", "cpu", "busy_max", f"{100 * values[-1]:.1f}", "% of 2 cores")

    hourly = defaultdict(list)
    for t, b in busy:
        hourly[t // 3600].append(b)
    # Only hours with at least 50 of their 60 minutes, so a gap does not skew the mean.
    hours = sorted(statistics.fmean(v) for v in hourly.values() if len(v) >= 50)
    emit("1-host", "cpu", "hourly_mean_median", f"{100 * stats.percentile(hours, 50):.1f}", f"% of 2 cores, {len(hours)} hours")
    emit("1-host", "cpu", "hourly_mean_p95", f"{100 * stats.percentile(hours, 95):.1f}", f"% of 2 cores, {len(hours)} hours")

    # A sample stamped t averages the minute before it. The ETL runs about
    # 20 s, so a minute that overlaps a run is still mostly idle time.
    etl = sorted(b for t, b in busy if overlaps_run(t - 60, t, etl_runs))
    rest = sorted(b for t, b in busy if not overlaps_run(t - 60, t, etl_runs))
    emit("1-host", "cpu", "busy_median_etl_minutes", f"{100 * stats.percentile(etl, 50):.1f}", f"% of 2 cores, {len(etl)} minutes overlapping an ETL run")
    emit("1-host", "cpu", "busy_p95_etl_minutes", f"{100 * stats.percentile(etl, 95):.1f}", "% of 2 cores")
    emit("1-host", "cpu", "busy_median_other_minutes", f"{100 * stats.percentile(rest, 50):.1f}", "% of 2 cores")

    # Each sample is already the lowest of its minute (min_over_time in export.py).
    memory = [r for r in rows if r["mem_available_min_bytes"]]
    lowest = min(memory, key=lambda r: number(r, "mem_available_min_bytes"))
    available = number(lowest, "mem_available_min_bytes")
    emit("1-host", "memory", "total", f"{host_memory / MIB:.0f}", "MiB")
    emit("1-host", "memory", "available_min", f"{available / MIB:.0f}", "MiB")
    emit("1-host", "memory", "available_min_of_total", f"{100 * available / host_memory:.1f}", "%")
    emit("1-host", "memory", "available_min_at", iso(int(lowest["timestamp"])))
    emit("1-host", "memory", "available_median", f"{statistics.median(number(r, 'mem_available_min_bytes') for r in memory) / MIB:.0f}", "MiB")


def disk(rows):
    """Report the root filesystem: size, growth per day, free space and reboots seen.

    The growth is the difference between the first and the last hourly sample.
    """
    rows = [r for r in rows if r["fs_size_bytes"]]
    first, last = rows[0], rows[-1]
    # Used = size - free, as df counts it; avail also leaves out the blocks reserved for root.
    used = [number(r, "fs_size_bytes") - number(r, "fs_free_bytes") for r in (first, last)]
    days = (int(last["timestamp"]) - int(first["timestamp"])) / DAY
    emit("1-host", "disk", "size", f"{number(last, 'fs_size_bytes') / GIB:.1f}", "GiB")
    emit("1-host", "disk", "used_first", f"{used[0] / GIB:.2f}", f"GiB at {iso(int(first['timestamp']))}")
    emit("1-host", "disk", "used_last", f"{used[1] / GIB:.2f}", f"GiB at {iso(int(last['timestamp']))}")
    emit("1-host", "disk", "growth_per_day", f"{(used[1] - used[0]) / days / MIB:.0f}", f"MiB/day over {days:.1f} days")
    emit("1-host", "disk", "available_last", f"{number(last, 'fs_avail_bytes') / GIB:.1f}", "GiB")
    # Every new boot time in the series is a reboot of the host.
    boots = sorted({number(r, "host_boot_time") for r in rows if r["host_boot_time"]})
    emit("1-host", "reboots", "boot_times_seen", " ".join(iso(int(b)) for b in boots))


# Question 2: latency inside the API during the windows of experiment 05.

def bucket_interval(buckets, q):
    """Return the (lower, upper] bounds, in ms, of the bucket holding quantile q.

    Prometheus buckets are cumulative: each count holds every request up to its
    bound, and the last bound, +Inf, holds them all. The first bucket that reaches
    the share q holds the quantile; nothing is interpolated inside it.

    Args:
        buckets: (upper bound in ms, cumulative count) pairs, sorted by bound.
        q: quantile between 0 and 1.
    """
    total = buckets[-1][1]
    lower = 0.0
    for le, count in buckets:
        if count / total >= q:
            return lower, le
        lower = le
    return lower, float("inf")


def bound(ms):
    """Format a bucket bound in ms, with +Inf as "inf"."""
    return "inf" if ms == float("inf") else f"{ms:g}"


def server_latency(rows, client_summary):
    """Report the server-side latency of each 05 scenario and the network share.

    Args:
        rows: rows of _latency.csv, counters read at both ends of each 05 window.
        client_summary: path of the 05 summary with the client percentiles, or None.
    """
    counts = defaultdict(lambda: defaultdict(float))  # scenario -> le -> requests
    requests = defaultdict(lambda: defaultdict(float))  # scenario -> "handler status" -> requests
    for row in rows:
        # What the window added to the counter; the runs of a scenario are summed.
        delta = float(row["value_at_end"]) - float(row["value_at_start"])
        if delta < 0:
            sys.exit(f"counter reset in {row['scenario']} run {row['run']}: the API restarted mid-window")
        if row["kind"] == "bucket":
            counts[row["scenario"]][row["key"]] += delta
        else:
            requests[row["scenario"]][row["key"]] += delta

    client = {r["scenario"]: r for r in read_csv(client_summary)} if client_summary else {}
    for scenario in counts:
        handlers = requests[scenario]
        # The histogram has no handler label, so the busiest handler and status
        # is taken as the endpoint under test and the rest is counted apart.
        test = max(handlers, key=handlers.get)
        other = sum(v for k, v in handlers.items() if k != test)
        emit("2-latency", scenario, "requests_test_endpoint", f"{handlers[test]:.0f}", test)
        emit("2-latency", scenario, "requests_other", f"{other:.0f}", "same windows, any other handler")

        # le is in seconds; the bounds are kept in ms, like the client figures of 05.
        buckets = sorted(((float("inf") if le == "+Inf" else float(le) * 1000, c)
                          for le, c in counts[scenario].items()))
        for p in (50, 95, 99):
            low, high = bucket_interval(buckets, p / 100)
            emit("2-latency", scenario, f"server_p{p}", f"({bound(low)}, {bound(high)}]", "ms, histogram bucket")
            if scenario in client:
                c = float(client[scenario][f"p{p}_ms"])
                # A difference of quantiles, not the quantile of a difference:
                # an approximation of where the network share lies.
                # The server quantile is in (low, high], so client minus server is
                # in [c - high, c - low), floored at 0.
                emit("2-latency", scenario, f"client_p{p}", f"{c:.1f}", "ms, from experiment 05")
                emit("2-latency", scenario, f"network_p{p}",
                     f"[{bound(max(0.0, c - high))}, {c - low:.1f})" if high != float("inf") else f"< {c - low:.1f}",
                     "ms, client minus server bucket")
        # Cumulative share at the smallest bounds, where these requests fall.
        for le, c in buckets[:6]:
            emit("2-latency", scenario, f"share_le_{bound(le)}ms", f"{100 * c / buckets[-1][1]:.1f}", "%")


# Question 3: the scheduler during the ETL, against experiment 04.

def scheduler(rows, etl_runs, full_period_peak, inference_summary):
    """Report the scheduler's memory peak in each ETL run, against its idle level and 04.

    Per run, the idle level is the median of the samples before it (IDLE_BEFORE_RUN)
    and the peak is the largest sample during it.

    Args:
        rows: rows of _scheduler.csv, one per 15 s sample.
        etl_runs: (start, end) epochs of every ETL run.
        full_period_peak: {"working_set": bytes, "rss": bytes}, maxima of the 15-minute series.
        inference_summary: path of the 04 summary, or None.
    """
    samples = [(int(r["timestamp"]), number(r, "working_set_bytes"), number(r, "rss_bytes")) for r in rows]
    samples = [s for s in samples if None not in s]
    first, last = samples[0][0], samples[-1][0]

    peaks = {"working_set": [], "rss": []}
    idles = {"working_set": [], "rss": []}
    above_half = {"working_set": [], "rss": []}
    for start, end in etl_runs:
        if start - IDLE_BEFORE_RUN[0] < first or end + SAMPLE_S > last:
            continue  # the run is not fully inside the detailed series
        # A sample stamped t can describe memory up to SAMPLE_S earlier.
        during = [s for s in samples if start <= s[0] <= end + SAMPLE_S]
        before = [s for s in samples if start - IDLE_BEFORE_RUN[0] <= s[0] <= start - IDLE_BEFORE_RUN[1]]
        for i, metric in ((1, "working_set"), (2, "rss")):
            idle = statistics.median(s[i] for s in before)
            peak = max(s[i] for s in during)
            peaks[metric].append(peak)
            idles[metric].append(idle)
            # Samples above halfway from idle to peak: how long the peak lasts, as sampled.
            above_half[metric].append(sum(1 for s in during if s[i] > idle + (peak - idle) / 2))

    emit("3-scheduler", "etl_runs", "count", len(peaks["rss"]), f"runs inside the detailed series, {SAMPLE_S} s samples")
    for metric in ("rss", "working_set"):
        p = sorted(peaks[metric])
        emit("3-scheduler", metric, "idle_median", f"{statistics.median(idles[metric]) / MIB:.0f}", "MiB, before each run")
        emit("3-scheduler", metric, "peak_median", f"{stats.percentile(p, 50) / MIB:.0f}", "MiB, per ETL run as sampled")
        emit("3-scheduler", metric, "peak_p90", f"{stats.percentile(p, 90) / MIB:.0f}", "MiB, per ETL run as sampled")
        emit("3-scheduler", metric, "peak_max", f"{p[-1] / MIB:.0f}", "MiB, detailed series")
        # The models stay loaded for a few seconds and memory is sampled every
        # 15 s, so most runs are sampled outside that moment.
        caught = sum(1 for v in p if v >= p[-1] / 2)
        emit("3-scheduler", metric, "runs_sampled_near_peak", f"{caught} of {len(p)}", "peak at least half the maximum")
        emit("3-scheduler", metric, "samples_above_half_peak_median", f"{statistics.median(above_half[metric]):.0f}", f"samples of {SAMPLE_S} s")
    emit("3-scheduler", "working_set", "peak_max_full_period", f"{full_period_peak['working_set'] / MIB:.0f}", "MiB, experiment 06 containers series")
    emit("3-scheduler", "rss", "peak_max_full_period", f"{full_period_peak['rss'] / MIB:.0f}", "MiB, experiment 06 containers series")

    if inference_summary:
        # Production mode of 04 classifies one text at a time, as the scheduler does.
        production = next(r for r in read_csv(inference_summary) if r["mode"] == "production")
        emit("3-scheduler", "experiment_04", "peak_rss_production_mode", production["peak_rss_mb"], "MiB, FinBERT alone, laptop")
        emit("3-scheduler", "experiment_04", "rss_after_model_load", production["load_rss_mb"], "MiB")


# Question 5: what keeps the CPU busy outside the ETL.

OBSERVABILITY = {"syndra_cadvisor", "syndra_node_exporter", "syndra_prometheus"}
# Modes in which the host is running code; iowait is waiting and steal is time
# the hypervisor gave to other machines, both outside our control.
RUNNING_MODES = ("user", "system", "nice", "irq", "softirq")
BLOCK_S = 900  # the 15-minute step of _cpu.csv


def idle_cpu(rows, etl_runs, cores):
    """Attribute the CPU used outside the ETL to each container and to the host.

    Every figure is a share of what a block can hold, BLOCK_S seconds per core.
    The host part is the running modes minus every container, which leaves what
    runs outside them.

    Args:
        rows: rows of _cpu.csv, CPU seconds per source and 15-minute block.
        etl_runs: (start, end) epochs of every ETL run.
        cores: number of host cores, from the environment file.
    """
    blocks = defaultdict(dict)  # block end -> source -> CPU seconds
    for row in rows:
        blocks[int(row["timestamp"])][row["source"]] = float(row["cpu_seconds"])
    # A block stamped t covers the 15 minutes before it. Blocks that touch an
    # ETL run, or that predate cAdvisor, are left out.
    quiet = {t: v for t, v in blocks.items()
             if "syndra_cadvisor" in v and not overlaps_run(t - BLOCK_S, t, etl_runs)}
    capacity = BLOCK_S * cores

    def report(subject, values, note=""):
        """Emit the median and p95 of CPU seconds per block, as a share of the capacity."""
        values = sorted(100 * v / capacity for v in values)
        emit("5-cpu", subject, "median", f"{stats.percentile(values, 50):.2f}", f"% of {cores:g} cores{note}")
        emit("5-cpu", subject, "p95", f"{stats.percentile(values, 95):.2f}", f"% of {cores:g} cores")

    emit("5-cpu", "blocks", "count", len(quiet), "15-minute blocks without an ETL run")
    # Container names only; the host_<mode> sources come from node_exporter.
    names = sorted({s for v in quiet.values() for s in v if not s.startswith("host_")})
    for name in names:
        report(name, [v[name] for v in quiet.values() if name in v])

    def total(block, names_in):
        """Sum the CPU seconds of some sources in one block; a missing one counts as 0."""
        return sum(block.get(n, 0) for n in names_in)

    containers_all = [total(v, names) for v in quiet.values()]
    report("group_observability", [total(v, OBSERVABILITY) for v in quiet.values()], ", cadvisor + node_exporter + prometheus")
    report("group_syndra", [total(v, set(names) - OBSERVABILITY) for v in quiet.values()], ", every other container")
    report("all_containers", containers_all)
    running = [total(v, [f"host_{m}" for m in RUNNING_MODES]) for v in quiet.values()]
    report("host_running", running, ", user + system + nice + irq + softirq")
    # Docker, containerd, the kernel and anything else outside a container.
    # Container CPU comes from increase(), which extrapolates, so this carries its error.
    report("host_outside_containers", [r - c for r, c in zip(running, containers_all)])
    report("host_steal", [v.get("host_steal", 0) for v in quiet.values()], ", taken by the hypervisor")
    report("host_iowait", [v.get("host_iowait", 0) for v in quiet.values()], ", waiting for disk")
    report("host_busy", [sum(x for k, x in v.items() if k.startswith("host_") and k != "host_idle")
                         for v in quiet.values()], ", every mode but idle, as in question 1")


# Question 4: size of the observability data.

def tsdb(rows, series_rows):
    """Report the TSDB size, its growth per day and whether the retention fits the size cap.

    Args:
        rows: rows of _storage.csv, one per hour.
        series_rows: rows of _series.csv, active series per scrape job.

    Reference: https://docs.python.org/3/library/statistics.html (linear_regression).
    """
    rows = [r for r in rows if r["tsdb_blocks_bytes"]]
    last = rows[-1]
    t_last = int(last["timestamp"])
    on_disk = number(last, "tsdb_blocks_bytes") + number(last, "tsdb_wal_bytes")
    emit("4-tsdb", "now", "blocks", f"{number(last, 'tsdb_blocks_bytes') / MIB:.0f}", "MiB")
    emit("4-tsdb", "now", "wal", f"{number(last, 'tsdb_wal_bytes') / MIB:.0f}", "MiB")

    # Blocks grow in steps as Prometheus compacts, so the rate is a least-squares
    # slope over hourly samples, not the difference of two of them.
    for days in (7, 14):
        recent = [r for r in rows if int(r["timestamp"]) >= t_last - days * DAY]
        # x in days, so the slope is bytes per day.
        slope = statistics.linear_regression(
            [int(r["timestamp"]) / DAY for r in recent],
            [number(r, "tsdb_blocks_bytes") for r in recent]).slope
        emit("4-tsdb", f"last_{days}_days", "growth_per_day", f"{slope / MIB:.1f}", "MiB/day")
        if days == 14:
            # Once retention is reached, old blocks are deleted as new ones arrive,
            # so the blocks level off at the daily growth times RETENTION_DAYS.
            projected = slope * RETENTION_DAYS + number(last, "tsdb_wal_bytes")
            emit("4-tsdb", "projection", "size_at_180_days", f"{projected / GIB:.2f}", "GiB, blocks plus current WAL")
            emit("4-tsdb", "projection", "share_of_size_cap", f"{100 * projected / SIZE_CAP:.0f}", "% of 10 GiB")
            # Days of data that fit under the cap at this rate, to compare with RETENTION_DAYS.
            emit("4-tsdb", "projection", "days_until_size_cap", f"{SIZE_CAP / slope:.0f}", "days, at this rate")

    # Most series held in memory at once in the period (max_over_time in export.py).
    head = sorted(number(r, "head_series_max") for r in rows if r["head_series_max"])
    emit("4-tsdb", "series", "head_series_max_in_period", f"{head[-1]:.0f}")
    for row in series_rows:
        emit("4-tsdb", "series_now", row["job"], row["series"])
    emit("4-tsdb", "now", "total_on_disk", f"{on_disk / MIB:.0f}", "MiB")


def main(prefix):
    """Read every dataset under prefix and print the summary, question by question."""
    environment = read_environment(f"{prefix}_environment.txt")
    host_memory = float(environment["host_memory_bytes"])
    # "period: START to END"; fromisoformat only accepts a trailing Z from Python 3.11.
    period_start = datetime.fromisoformat(environment["period"].split(" to ")[0].replace("Z", "+00:00")).timestamp()
    here = Path(__file__).resolve().parent

    def sibling(key):
        """Path of a file the environment names relative to this folder, or None."""
        value = environment.get(key, "none")
        return here / value if value not in ("none", "") else None

    container_rows = read_csv(f"{prefix}_containers.csv")
    etl_runs = [(int(r["start_epoch"]), int(r["end_epoch"])) for r in read_csv(f"{prefix}_etl_runs.csv")]
    scheduler_rows = [r for r in container_rows if r["container"] == "syndra_scheduler"]
    # The 15-minute series covers the whole period, not only the detailed days,
    # and keeps every peak through max_over_time.
    full_period_peak = {
        "working_set": max(number(r, "working_set_bytes") or 0 for r in scheduler_rows),
        "rss": max(number(r, "rss_bytes") or 0 for r in scheduler_rows),
    }

    out.writerow(["question", "subject", "metric", "value", "unit"])
    containers(container_rows, host_memory, period_start)
    host(read_csv(f"{prefix}_host.csv"), host_memory, etl_runs)
    disk(read_csv(f"{prefix}_storage.csv"))
    # measure.sh only writes _latency.csv when it found a run of 05.
    if Path(f"{prefix}_latency.csv").exists():
        server_latency(read_csv(f"{prefix}_latency.csv"), sibling("latency_client_summary"))
    scheduler(read_csv(f"{prefix}_scheduler.csv"), etl_runs, full_period_peak, sibling("inference_summary"))
    tsdb(read_csv(f"{prefix}_storage.csv"), read_csv(f"{prefix}_series.csv"))
    if Path(f"{prefix}_cpu.csv").exists():
        idle_cpu(read_csv(f"{prefix}_cpu.csv"), etl_runs, float(environment["host_cores"]))


if __name__ == "__main__":
    main(sys.argv[1])
