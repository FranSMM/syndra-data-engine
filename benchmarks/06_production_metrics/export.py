"""Exports Prometheus data as CSV on stdout.

Runs on the VPS host, fed through stdin by measure.sh (`python3 - DATASET ARGS`),
so nothing is copied to the server. Standard library only, and read-only: it
only sends GET requests to the Prometheus API published on 127.0.0.1.

Datasets: period, series, latency WINDOW..., and containers, host, storage,
cpu or scheduler START END (epochs).
Reference: https://prometheus.io/docs/prometheus/latest/querying/api/
"""
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request

PROMETHEUS = "http://127.0.0.1:9090/api/v1/"
# Prometheus refuses range queries of more than 11,000 points per series.
MAX_POINTS = 10_000
# Label matchers: every Syndra container, and the root filesystem.
CONTAINERS = 'name=~"syndra_.+"'
ROOT_FS = 'mountpoint="/"'


def api(path, **params):
    """Send a GET to the Prometheus HTTP API and return the data field of the reply.

    Exits with the error Prometheus gives when the status is not "success".
    """
    url = PROMETHEUS + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120) as response:
        body = json.load(response)
    if body["status"] != "success":
        sys.exit(f"{path}: {body.get('error')}")
    return body["data"]


def instant(expr, at=None):
    """Run an instant query at epoch `at`, or now, and return its list of series."""
    params = {"query": expr} if at is None else {"query": expr, "time": at}
    return api("query", **params)["result"]


def scalar(expr, at=None):
    """Return the value of a single-series instant query, or None if it is empty."""
    result = instant(expr, at)
    # Each value is [timestamp, "value as a string"].
    return float(result[0]["value"][1]) if result else None


def by_label(expr, label, start, end, step):
    """Run a range query, fetched in chunks, and index its points by one label.

    Args:
        expr: PromQL expression.
        label: label that tells the series apart; "" when there is a single series.
        start, end: epochs of the range, both included.
        step: seconds between points.

    Returns:
        {label value: {timestamp: value}}.
    """
    series = {}
    chunk_start = start
    while chunk_start <= end:
        # MAX_POINTS - 1 steps after its start, so a chunk holds at most MAX_POINTS points.
        chunk_end = min(end, chunk_start + step * (MAX_POINTS - 1))
        result = api("query_range", query=expr, start=chunk_start, end=chunk_end, step=step)["result"]
        for r in result:
            points = series.setdefault(r["metric"].get(label, ""), {})
            points.update((int(t), float(v)) for t, v in r["values"])
        # One step later, so no point is fetched twice.
        chunk_start = chunk_end + step
    return series


def write_wide(keyed, key_column=None):
    """Write one row per (key, timestamp) and one column per query; empty where missing.

    Args:
        keyed: {column name: by_label() result}.
        key_column: header of the key column. Without it every query returns a
            single series and no key is written.
    """
    writer = csv.writer(sys.stdout)
    writer.writerow(([key_column] if key_column else []) + ["timestamp"] + list(keyed))
    keys = sorted({k for series in keyed.values() for k in series})
    for key in keys:
        stamps = sorted({t for series in keyed.values() for t in series.get(key, {})})
        for t in stamps:
            values = [format_value(keyed[c].get(key, {}).get(t)) for c in keyed]
            writer.writerow(([key] if key_column else []) + [t] + values)


def format_value(v):
    """Format a value for the CSV: empty for None, no trailing zeros."""
    # Three decimals keep CPU-second counters exact enough; bytes stay integers.
    if v is None:
        return ""
    return f"{v:.3f}".rstrip("0").rstrip(".")


def period():
    """Print the environment lines: what is being read and since when."""
    now = int(time.time())
    # Oldest sample still in the TSDB, so the start of the data.
    start = int(scalar("prometheus_tsdb_lowest_timestamp_seconds"))
    print(f"now_epoch: {now}")
    print(f"data_start_epoch: {start}")
    for metric, label in [("prometheus_build_info", "prometheus"),
                          ("cadvisor_version_info", "cadvisor"),
                          ("node_exporter_build_info", "node_exporter")]:
        result = instant(metric)
        # cAdvisor keeps its version in the cadvisorVersion label, the others in version.
        version = result[0]["metric"].get("cadvisorVersion" if label == "cadvisor" else "version") if result else "unknown"
        print(f"{label}_version: {version}")
    print(f"retention: {api('status/runtimeinfo')['storageRetention']}")
    scrape = re.search(r"scrape_interval:\s*(\S+)", api("status/config")["yaml"])
    print(f"scrape_interval: {scrape.group(1) if scrape else 'unknown'}")
    # node_exporter has one idle series per core.
    cores = scalar('count(node_cpu_seconds_total{mode="idle"})')
    memory = scalar("node_memory_MemTotal_bytes")
    print(f"host_cores: {cores:.0f}")
    print(f"host_memory_bytes: {memory:.0f}")
    # Jobs were added at different times, so each has its own start.
    first = by_label("count by (job) (up)", "job", start, now, 3600)
    for job, points in sorted(first.items()):
        print(f"first_sample_{job}: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(min(points)))}")


def containers(start, end):
    """Write memory peaks, limit, start time and OOM events per container, every 15 min.

    Reference: https://github.com/google/cadvisor/blob/master/docs/storage/prometheus.md
    """
    # max_over_time over the full step keeps every peak the scrapes saw. Each
    # recreated container is a new cAdvisor series, so series are merged by name.
    step = 900
    queries = {
        "working_set_bytes": f"max by (name) (max_over_time(container_memory_working_set_bytes{{{CONTAINERS}}}[15m]))",
        "rss_bytes": f"max by (name) (max_over_time(container_memory_rss{{{CONTAINERS}}}[15m]))",
        "limit_bytes": f"max by (name) (container_spec_memory_limit_bytes{{{CONTAINERS}}})",
        "start_time": f"max by (name) (container_start_time_seconds{{{CONTAINERS}}})",
        "oom_events_total": f"max by (name) (max_over_time(container_oom_events_total{{{CONTAINERS}}}[15m]))",
    }
    write_wide({c: by_label(q, "name", start, end, step) for c, q in queries.items()}, "container")


def host(start, end):
    """Write the host's CPU counters and its lowest available memory, every minute."""
    # Raw CPU counters, not rate(): differences of consecutive samples cover
    # every second, with no gaps between windows.
    step = 60
    queries = {
        "cpu_idle_seconds": 'sum(node_cpu_seconds_total{mode="idle"})',
        "cpu_total_seconds": "sum(node_cpu_seconds_total)",
        "mem_available_min_bytes": "min_over_time(node_memory_MemAvailable_bytes[1m])",
    }
    write_wide({c: by_label(q, "", start, end, step) for c, q in queries.items()})


def storage(start, end):
    """Write root filesystem, TSDB size, head series and boot time, every hour."""
    step = 3600
    queries = {
        "fs_size_bytes": f"node_filesystem_size_bytes{{{ROOT_FS}}}",
        "fs_free_bytes": f"node_filesystem_free_bytes{{{ROOT_FS}}}",
        "fs_avail_bytes": f"node_filesystem_avail_bytes{{{ROOT_FS}}}",
        "tsdb_blocks_bytes": "prometheus_tsdb_storage_blocks_bytes",
        "tsdb_wal_bytes": "prometheus_tsdb_wal_storage_size_bytes",
        "head_series_max": "max_over_time(prometheus_tsdb_head_series[1h])",
        "host_boot_time": "node_boot_time_seconds",
    }
    write_wide({c: by_label(q, "", start, end, step) for c, q in queries.items()})


def cpu(start, end):
    """Write CPU seconds per source and 15-minute block, one row each.

    Long format rather than one column per source, since containers come and go.
    Reference: https://github.com/google/cadvisor/blob/master/docs/storage/prometheus.md
    """
    # CPU seconds per 15-minute block: per container, and for the whole host by
    # mode. increase() is taken per series before summing, so a container
    # recreated by a deploy does not look like a counter reset.
    step = 900
    sources = {
        **by_label(f"sum by (name) (increase(container_cpu_usage_seconds_total{{{CONTAINERS}}}[15m]))",
                   "name", start, end, step),
        **{f"host_{mode}": points for mode, points in
           by_label("sum by (mode) (increase(node_cpu_seconds_total[15m]))", "mode", start, end, step).items()},
    }
    writer = csv.writer(sys.stdout)
    writer.writerow(["source", "timestamp", "cpu_seconds"])
    for source, points in sorted(sources.items()):
        for t, v in sorted(points.items()):
            writer.writerow([source, t, format_value(v)])


def scheduler(start, end):
    """Write the scheduler's working set and RSS at the scrape interval."""
    # At the scrape interval, to see the shape of each ETL peak. max() merges
    # the series of a scheduler recreated by a deploy.
    step = 15
    queries = {
        "working_set_bytes": 'max(container_memory_working_set_bytes{name="syndra_scheduler"})',
        "rss_bytes": 'max(container_memory_rss{name="syndra_scheduler"})',
    }
    write_wide({c: by_label(q, "", start, end, step) for c, q in queries.items()})


def series_by_job():
    """Write the number of active series per scrape job, now.

    Reference: https://prometheus.io/docs/prometheus/latest/querying/basics/
    """
    writer = csv.writer(sys.stdout)
    writer.writerow(["job", "series"])
    # {__name__!=""} selects every series; PromQL refuses an empty {} selector.
    for r in sorted(instant('count by (job) ({__name__!=""})'), key=lambda r: r["metric"]["job"]):
        writer.writerow([r["metric"]["job"], r["value"][1]])


def latency(windows):
    """Write the request and histogram counters at both ends of each 05 window.

    Args:
        windows: "scenario,run,start_epoch,end_epoch" strings built by measure.sh.
    """
    # Counters read at both ends of each window, not increase(), which
    # extrapolates. The end is read 30 s late so the last scrape is included.
    writer = csv.writer(sys.stdout)
    writer.writerow(["scenario", "run", "start", "end", "kind", "key", "value_at_start", "value_at_end"])
    for window in windows:
        scenario, run, t0, t1 = window.split(",")
        # Requests per handler and status, and the cumulative latency buckets.
        for kind, expr, labels in [
            ("requests", "sum by (handler, status) (http_requests_total)", ("handler", "status")),
            ("bucket", "sum by (le) (http_request_duration_highr_seconds_bucket)", ("le",)),
        ]:
            at_start = {tuple(r["metric"].get(l, "") for l in labels): float(r["value"][1])
                        for r in instant(expr, int(t0))}
            at_end = {tuple(r["metric"].get(l, "") for l in labels): float(r["value"][1])
                      for r in instant(expr, int(t1) + 30)}
            for key in sorted(set(at_start) | set(at_end)):
                writer.writerow([scenario, run, t0, t1, kind, " ".join(key),
                                 f"{at_start.get(key, 0):.0f}", f"{at_end.get(key, 0):.0f}"])


if __name__ == "__main__":
    # The first argument picks the dataset; the range datasets take START END epochs.
    dataset, args = sys.argv[1], sys.argv[2:]
    if dataset == "period":
        period()
    elif dataset == "series":
        series_by_job()
    elif dataset == "latency":
        latency(args)
    else:
        {"containers": containers, "host": host, "storage": storage, "cpu": cpu,
         "scheduler": scheduler}[dataset](int(args[0]), int(args[1]))
