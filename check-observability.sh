#!/bin/bash
#
# Read-only health check of the observability stack on the production VPS.
#
# Sibling of deploy.sh and the same shape: runs from the laptop, talks to the
# VPS over SSH, touches nothing. Answers the question "is Prometheus actually
# collecting, and is what it collected any good" without opening a browser.
#
# Prints PASS/WARN per check and exits non-zero if anything is WARN, so it can
# be dropped into a cron or a CI job later without rewriting it.
#
# Usage:
#   ./check-observability.sh            Check the last 5 days
#   ./check-observability.sh 14d        Check any Prometheus range
#
set -eo pipefail

WINDOW="${1:-5d}"

if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo ".env not found. Needs VPS_USER and VPS_IP, same as deploy.sh."
    exit 1
fi

if [ -z "$VPS_IP" ] || [ -z "$VPS_USER" ]; then
    echo "Missing VPS_USER or VPS_IP in your .env"
    exit 1
fi

# The payload runs on the VPS because Prometheus listens on loopback there and
# is deliberately not reachable from anywhere else. Passing the window through
# the environment rather than interpolating it into the script keeps the quoting
# survivable across ssh.
ssh "$VPS_USER@$VPS_IP" "WINDOW='$WINDOW' python3 -" <<'REMOTE'
import json, os, time, urllib.parse, urllib.request

WINDOW = os.environ.get("WINDOW", "5d")
BASE = "http://127.0.0.1:9090/api/v1/"
RETENTION_DAYS = 180
SIZE_CAP_GB = 10

warnings = []

def q(expr):
    url = BASE + "query?" + urllib.parse.urlencode({"query": expr})
    return json.load(urllib.request.urlopen(url, timeout=30))["data"]["result"]

def v(expr):
    """Scalar value or None. Never conflate a real 0 with a missing series."""
    r = q(expr)
    return float(r[0]["value"][1]) if r else None

def line(status, text):
    if status == "WARN":
        warnings.append(text)
    print("  [%s] %s" % (status, text))

print("\n=== SCRAPING (ventana: %s) ===" % WINDOW)
targets = q("avg_over_time(up[%s])" % WINDOW)
if not targets:
    line("WARN", "Prometheus no devuelve ningun objetivo")
for r in sorted(targets, key=lambda r: r["metric"].get("job", "")):
    job = r["metric"]["job"]
    uptime = float(r["value"][1]) * 100
    now = v('up{job="%s"}' % job)
    if now != 1:
        line("WARN", "%s esta CAIDO ahora mismo" % job)
    elif uptime < 99:
        line("WARN", "%s solo estuvo arriba el %.2f%% de la ventana" % (job, uptime))
    else:
        line("PASS", "%-12s arriba, %.3f%% de la ventana" % (job, uptime))

print("\n=== CARDINALIDAD Y DISCO ===")
series = v("prometheus_tsdb_head_series")
sps = v("rate(prometheus_tsdb_head_samples_appended_total[6h])")
if series:
    print("  %d series activas, %.1f muestras/s (%.1f M/dia)"
          % (series, sps or 0, (sps or 0) * 86400 / 1e6))
    for r in sorted(q('count by (job) ({__name__=~".+"})'), key=lambda r: -int(r["value"][1])):
        print("      %-12s %6s" % (r["metric"].get("job", "?"), r["value"][1]))

# Projected footprint from the measured ingestion rate. This is the check that
# the 2GB cap originally failed: a guardrail that quietly becomes the binding
# limit deletes the earliest history, which is the history worth keeping.
if sps:
    bytes_per_sample = 1.75
    projected_gb = sps * 86400 * RETENTION_DAYS * bytes_per_sample / 1e9
    pct = projected_gb / SIZE_CAP_GB * 100
    if pct > 80:
        line("WARN", "proyeccion a %dd: %.2f GB, el %.0f%% del tope de %d GB"
             % (RETENTION_DAYS, projected_gb, pct, SIZE_CAP_GB))
    else:
        line("PASS", "proyeccion a %dd: %.2f GB de %d GB (%.0f%%), manda el tiempo"
             % (RETENTION_DAYS, projected_gb, SIZE_CAP_GB, pct))

print("\n=== DATOS DE SYNDRA ===")
for r in sorted(q("syndra_articles"), key=lambda r: r["metric"]["source"]):
    src = r["metric"]["source"]
    now = float(r["value"][1])
    old = v('syndra_articles{source="%s"} offset %s' % (src, WINDOW))
    delta = "  (+%d)" % (now - old) if old is not None else "  (nuevo)"
    print("  %-22s %8d%s" % (src, now, delta))

pending = v("syndra_ingestion_pending")
failed = v("syndra_ingestion_failed")
if failed is None or pending is None:
    line("WARN", "los gauges de ingesta no existen: fallo el refresco contra Postgres")
else:
    line("WARN" if failed > 0 else "PASS", "pendientes=%d fallidos=%d" % (pending, failed))

print("\n=== FRESCURA POR FUENTE ===")
for r in sorted(q("syndra_source_last_article_age_seconds"), key=lambda r: -float(r["value"][1])):
    src = r["metric"]["source"]
    hours = float(r["value"][1]) / 3600
    # A negative age means the newest published_at is in the future, which is a
    # data bug, not freshness. Deliberately not clamped to zero anywhere in the
    # pipeline: clamping would render it as "perfectly fresh" and hide it.
    if hours < 0:
        line("WARN", "%s tiene fechas en el FUTURO (%.0f h): bug de parseo de fecha" % (src, -hours))
    elif hours > 72:
        line("WARN", "%s lleva %.1f h sin articulo nuevo" % (src, hours))
    else:
        line("PASS", "%-22s %.1f h" % (src, hours))

print("\n=== PIPELINE ETL ===")
stages = q('syndra_etl_stage_duration_seconds{stat="avg"}')
for r in sorted(stages, key=lambda r: -float(r["value"][1])):
    print("  %-32s %6.2f s" % (r["metric"]["stage"], float(r["value"][1])))
if not stages:
    line("WARN", "sin duraciones por etapa: no se pudo leer prefect_db")

last_run = v("syndra_etl_last_flow_run_timestamp_seconds")
if last_run:
    mins = (time.time() - last_run) / 60
    # The flow is hourly, so anything past two hours means it missed a slot.
    line("WARN" if mins > 120 else "PASS", "ultimo flow run hace %.0f min" % mins)

fresh = v("syndra_etl_metrics_last_success_timestamp_seconds")
if fresh:
    age = time.time() - fresh
    # Without this the gauges above could be frozen from hours ago and look fine.
    line("WARN" if age > 300 else "PASS", "gauges refrescados hace %.0f s" % age)

for r in q("syndra_etl_flow_runs"):
    print("  flow runs 24h: %s=%s" % (r["metric"]["state"], r["value"][1]))

print("\n=== RECURSOS (lo que pide el Cap. 4) ===")
for name in ("syndra_scheduler", "syndra_api"):
    peak = v('max_over_time(container_memory_working_set_bytes{name="%s"}[%s])' % (name, WINDOW))
    avg = v('avg_over_time(container_memory_working_set_bytes{name="%s"}[%s])' % (name, WINDOW))
    if peak:
        print("  %-18s pico %7.1f MB   media %7.1f MB" % (name, peak / 1e6, avg / 1e6))

# cAdvisor lives pinned at its ceiling by design: almost all of its resident set
# is reclaimable kernel cache. anon is the only number that would signal a leak.
anon = v('container_memory_rss{name="syndra_cadvisor"}')
if anon is not None:
    line("WARN" if anon > 100e6 else "PASS",
         "cadvisor anon %.1f MB (normal ~10 MB; su techo alto es cache reclamable)" % (anon / 1e6))

print("\n" + "=" * 52)
if warnings:
    print("%d AVISO(S):" % len(warnings))
    for w in warnings:
        print("  - %s" % w)
    # Non-zero on warnings so this can be wired into cron or CI unchanged. Said
    # out loud because otherwise `make obs` ends on a bare "Error 1" that reads
    # as the tool being broken rather than as the system having something to say.
    print("\nSalida 1, que es lo esperado cuando hay avisos. La herramienta esta bien.")
else:
    print("Todo correcto.")
print("=" * 52)

raise SystemExit(1 if warnings else 0)
REMOTE
