#!/bin/bash
#
# Runs the integration suite against a throwaway stack.
#
# test_security.py is the only test file that needs live infrastructure: it
# talks to Postgres, to Redis, and over HTTP to the API itself. Everything else
# in tests/ stubs the session and runs anywhere.
#
# It gets its own disposable stack rather than the development one for two
# reasons. It writes to the database: inserting and then deleting API keys,
# so a crashed run leaves rows behind, and the local stack is somewhere you
# keep data you care about. And its containers are named distinctly, so running
# this never collides with whatever you already have up.
#
# NEVER point this at production. The suite inserts a working API key whose
# value ('syndra_test_valid_123') is written in the source file, and fires 100
# requests to provoke a 429. On the VPS that is a guessable live credential for
# the duration of the run, plus synthetic traffic landing in the same
# http_requests_total and latency histograms the results chapter is built from.
#
# Usage:
#   ./run-integration-tests.sh                 # builds from ./backend
#   ./run-integration-tests.sh some-image:tag  # reuses an image you already built
#
set -uo pipefail

IMAGE="${1:-}"
NET=syndra_itest_net
PG=syndra_itest_pg
REDIS=syndra_itest_redis
QDRANT=syndra_itest_qdrant
API=syndra_itest_api

if [ ! -f .env ]; then
    echo "Falta el .env de la raiz: de ahi salen las credenciales de Postgres."
    exit 1
fi
set -a
source .env
set +a

cleanup() {
    docker rm -f "$API" "$PG" "$REDIS" "$QDRANT" >/dev/null 2>&1
    docker network rm "$NET" >/dev/null 2>&1
}
# Runs on success, on failure and on Ctrl+C: a half-torn-down stack would hold
# the container names and make the next run fail for an unrelated reason.
trap cleanup EXIT INT TERM
cleanup

if [ -z "$IMAGE" ]; then
    IMAGE=syndra-integration-tests:local
    echo "-- construyendo la imagen"
    docker build -q -t "$IMAGE" ./backend >/dev/null || exit 1
fi

echo "-- levantando postgres, redis y qdrant"
docker network create "$NET" >/dev/null
docker run -d --name "$PG" --network "$NET" \
    -e POSTGRES_USER="$POSTGRES_USER" \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e POSTGRES_DB="$POSTGRES_DB" \
    postgres:15-alpine >/dev/null
docker run -d --name "$REDIS" --network "$NET" redis:7-alpine >/dev/null
docker run -d --name "$QDRANT" --network "$NET" qdrant/qdrant:v1.17.0 >/dev/null

for _ in $(seq 1 60); do
    docker exec "$PG" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1 && break
    sleep 1
done

echo "-- levantando la API"
# tests/ is in .dockerignore and so is not in the image; docker cp puts it in
# after create and before start.
docker create --name "$API" --network "$NET" \
    -e POSTGRES_USER="$POSTGRES_USER" \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e POSTGRES_DB="$POSTGRES_DB" \
    -e POSTGRES_SERVER="$PG" -e POSTGRES_PORT=5432 \
    -e REDIS_URL="redis://$REDIS:6379" \
    -e QDRANT_HOST="$QDRANT" -e QDRANT_PORT=6333 \
    -e ENVIRONMENT=test \
    "$IMAGE" uvicorn app.main:app --host 0.0.0.0 --port 8000 >/dev/null
docker cp ./backend/tests "$API:/code/tests" >/dev/null
docker cp ./backend/pytest.ini "$API:/code/pytest.ini" >/dev/null
docker start "$API" >/dev/null

for _ in $(seq 1 60); do
    docker exec "$API" python -c \
        "import urllib.request;urllib.request.urlopen('http://localhost:8000/health',timeout=2)" \
        >/dev/null 2>&1 && break
    sleep 2
done

echo "-- migraciones"
docker exec "$API" alembic upgrade head 2>&1 | grep -E "Running upgrade|ERROR" | tail -5

echo
docker exec "$API" python -m pytest /code/tests/test_security.py -q
