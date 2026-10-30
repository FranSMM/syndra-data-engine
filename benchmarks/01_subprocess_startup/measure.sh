#!/usr/bin/env bash
# Experiment 01: startup cost of the extraction and load subprocesses.
# Read-only: imports and `scrapy list`, no network and no writes.
#
# Usage: REPS=30 ./measure.sh   (from WSL, with SSH access to the VPS)
# Writes results/startup_<stamp>.csv and results/startup_<stamp>_environment.txt.
set -euo pipefail
cd "$(dirname "$0")"
source ../lib/common.sh

# The scheduler container is where the real Extract and Load subprocesses run.
CONTAINER="${CONTAINER:-syndra_scheduler}"
REPS="${REPS:-30}"

mkdir -p results
STAMP="$(new_stamp)"
CSV="results/startup_${STAMP}.csv"
ENVIRONMENT="results/startup_${STAMP}_environment.txt"

write_environment_header "$ENVIRONMENT"
# Image, hardware and library versions, so a later run can be compared with this one.
# The \$ are escaped so they expand on the VPS, not here.
{
  echo "repetitions: $REPS"
  vps "
    echo image: \$(docker inspect -f '{{.Config.Image}}' $CONTAINER)
    echo cores: \$(nproc)
    echo memory_mb: \$(free -m | awk '/Mem:/{print \$2}')
    docker exec $CONTAINER python -c 'import sys, scrapy, sqlalchemy; print(\"python:\", sys.version.split()[0]); print(\"scrapy:\", scrapy.__version__); print(\"sqlalchemy:\", sqlalchemy.__version__)'
  "
} >> "$ENVIRONMENT"

echo "measurement,repetition,ms" > "$CSV"
# The timing loop runs inside the container, so SSH and docker exec are not in
# the measured time. The heredoc is unquoted so $REPS is filled in here.
# Each spawn is timed with time.perf_counter around subprocess.run, output discarded.
# See https://docs.python.org/3/library/time.html and https://docs.python.org/3/library/subprocess.html
vps "docker exec -i $CONTAINER python -" >> "$CSV" <<PY
import subprocess, time

REPS = $REPS
MEASUREMENTS = [
    ("python_empty",       ["python", "-c", "pass"],                          "/code"),
    ("import_scrapy",      ["python", "-c", "import scrapy"],                 "/code"),
    ("import_sqlalchemy",  ["python", "-c", "import sqlalchemy"],             "/code"),
    ("extraction_startup", ["scrapy", "list"],                                "/code/app/scraper"),
    ("load_startup",       ["python", "-c", "import app.scraper.load_to_db"], "/code"),
]

for name, command, workdir in MEASUREMENTS:
    for i in range(1, REPS + 1):
        t0 = time.perf_counter()
        subprocess.run(command, cwd=workdir, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"{name},{i},{(time.perf_counter() - t0) * 1000:.1f}")
PY

echo "Data:        $CSV"
echo "Environment: $ENVIRONMENT"
