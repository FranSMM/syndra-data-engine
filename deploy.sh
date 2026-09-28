#!/bin/bash
#
# Immutable, selective deployment to the production VPS.
#
# Images are tagged with the short git SHA of the commit that produced them,
# never only with :latest. A mutable tag cannot be rolled back to, there is
# only ever one version behind it, which made the "100% Immutable
# Infrastructure" claim in the project rules untrue in practice. The VPS .env
# records which tag each image is pinned to, so returning to a previous build
# is one variable and one `up -d`, with no rebuild.
#
# Only images whose source actually changed since what production is running
# are rebuilt. The ETL image is 4.4GB (torch plus baked-in FinBERT weights);
# rebuilding and re-pushing it to deploy a demo-only change cost minutes of
# export, unpack and manifest checks for no benefit.
#
# Everything deployed comes from HEAD on main, extracted with git archive.
# Uncommitted changes are listed and left out, never built.
#
# Usage:
#   ./deploy.sh                     Build only what changed, deploy
#   ./deploy.sh --all               Force a rebuild of both images
#   ./deploy.sh --rollback etl=abc1234    Point production at an existing tag
#   ./deploy.sh --rollback demo=abc1234
#
set -eo pipefail

REGISTRY="ghcr.io/fransmm"

# Load private variables from .env
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo ".env file not found. Make sure you have VPS_USER, VPS_IP and DEPLOY_DIR configured."
    exit 1
fi

if [ -z "$VPS_IP" ] || [ -z "$VPS_USER" ] || [ -z "$DEPLOY_DIR" ]; then
    echo "Missing VPS_USER, VPS_IP or DEPLOY_DIR variables in your .env"
    exit 1
fi

remote() { ssh "$VPS_USER@$VPS_IP" "$@"; }

# Read one pinned tag out of the VPS .env. Empty when never set, which the
# caller treats as "unknown baseline" and therefore as changed.
read_remote_tag() {
    remote "grep -E '^$1=' '$DEPLOY_DIR/.env' 2>/dev/null | tail -1 | cut -d= -f2" || true
}

write_remote_tag() {
    remote "cd '$DEPLOY_DIR' && if grep -qE '^$1=' .env; then sed -i 's|^$1=.*|$1=$2|' .env; else printf '%s=%s\n' '$1' '$2' >> .env; fi"
}

# ---------------------------------------------------------------- arguments --
FORCE_ALL=false
ROLLBACK_SPEC=""

while [ $# -gt 0 ]; do
    case "$1" in
        --all)      FORCE_ALL=true ;;
        --rollback) ROLLBACK_SPEC="$2"; shift ;;
        -h|--help)  sed -n '3,25p' "$0"; exit 0 ;;
        *)          echo "Unknown argument: $1"; exit 1 ;;
    esac
    shift
done

# ----------------------------------------------------------------- rollback --
if [ -n "$ROLLBACK_SPEC" ]; then
    IMAGE="${ROLLBACK_SPEC%%=*}"
    TAG="${ROLLBACK_SPEC#*=}"

    case "$IMAGE" in
        etl)  VAR="ETL_TAG";  SERVICES="api scheduler" ;;
        demo) VAR="DEMO_TAG"; SERVICES="demo" ;;
        *)    echo "Rollback target must be etl or demo, got '$IMAGE'"; exit 1 ;;
    esac

    # Confirm the tag exists in the registry before pointing production at it.
    # Without this the rollback "succeeds" and the pull fails on the VPS,
    # leaving .env pinned to something that cannot be pulled.
    #
    # `docker manifest inspect` does exit non-zero on a missing tag, so `set -e`
    # alone would stop here. The explicit test is kept for the message: a bare
    # `manifest unknown` does not tell you that nothing was changed or where to
    # look for valid tags. It also does not depend on that exit code staying
    # stable across Docker versions, since the check is on the manifest itself.
    echo "-- Verifying $REGISTRY/syndra-$IMAGE:$TAG exists..."
    if ! docker manifest inspect "$REGISTRY/syndra-$IMAGE:$TAG" 2>/dev/null | grep -q '"schemaVersion"'; then
        echo "   Tag not found in the registry. Nothing changed."
        echo "   Available tags: https://github.com/FranSMM?tab=packages"
        exit 1
    fi

    echo "-- Pinning $VAR=$TAG and restarting: $SERVICES"
    write_remote_tag "$VAR" "$TAG"
    remote "cd '$DEPLOY_DIR' && docker compose pull $SERVICES && docker compose up -d $SERVICES"

    echo "-- Rollback complete. $IMAGE is now on $TAG."
    exit 0
fi

# ------------------------------------------------------------------- deploy --
# The image tag is a commit, so that commit must be one that lives on main.
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
    echo "Error: on '$BRANCH'. Deploy only from main."
    exit 1
fi

if [ -n "$(git log origin/main..HEAD 2>/dev/null)" ]; then
    echo "Error: you have unpushed commits. Run 'git push' first."
    exit 1
fi

GIT_SHA=$(git rev-parse --short HEAD)

# Images and infra config come from the commit, never from the working tree:
# `docker build ./backend` copies whatever is on disk, so uncommitted edits used
# to ship under a SHA that does not contain them.
SRC_DIR=$(mktemp -d)
trap 'rm -rf "$SRC_DIR"' EXIT
git archive HEAD | tar -x -C "$SRC_DIR"
INFRA="$SRC_DIR/infra"

UNCOMMITTED=$(git status --porcelain -- backend demo infra)
if [ -n "$UNCOMMITTED" ]; then
    echo "-- Not deploying $(printf '%s\n' "$UNCOMMITTED" | wc -l) uncommitted change(s):"
    printf '%s\n' "$UNCOMMITTED" | head -10 | sed 's/^/     /'
fi

DEPLOYED_ETL=$(read_remote_tag ETL_TAG)
DEPLOYED_DEMO=$(read_remote_tag DEMO_TAG)

# True when the given path changed since the deployed commit. An empty or
# unknown baseline (first run with this scheme, or a tag whose commit is not in
# this clone) counts as changed: building unnecessarily is wasteful, but not
# building when you should ships stale code.
changed_since() {
    local baseline="$1" path="$2"
    if [ -z "$baseline" ] || ! git cat-file -e "${baseline}^{commit}" 2>/dev/null; then
        return 0
    fi
    [ -n "$(git diff --name-only "${baseline}..HEAD" -- "$path")" ]
}

BUILD_ETL=false
BUILD_DEMO=false

if [ "$FORCE_ALL" = true ]; then
    BUILD_ETL=true
    BUILD_DEMO=true
else
    if changed_since "$DEPLOYED_ETL" backend/; then BUILD_ETL=true; fi
    if changed_since "$DEPLOYED_DEMO" demo/;   then BUILD_DEMO=true; fi
fi

echo "-- [1/5] Building images (HEAD is $GIT_SHA)..."
if [ "$BUILD_ETL" = true ]; then
    docker build -t "$REGISTRY/syndra-etl:$GIT_SHA" -t "$REGISTRY/syndra-etl:latest" "$SRC_DIR/backend"
    ETL_TAG="$GIT_SHA"
else
    echo "   backend/ unchanged since $DEPLOYED_ETL: skipping build"
    ETL_TAG="$DEPLOYED_ETL"
fi

if [ "$BUILD_DEMO" = true ]; then
    docker build -t "$REGISTRY/syndra-demo:$GIT_SHA" -t "$REGISTRY/syndra-demo:latest" "$SRC_DIR/demo"
    DEMO_TAG="$GIT_SHA"
else
    echo "   demo/ unchanged since $DEPLOYED_DEMO: skipping build"
    DEMO_TAG="$DEPLOYED_DEMO"
fi

echo "-- [2/5] Pushing to GitHub Container Registry..."
if [ "$BUILD_ETL" = true ]; then
    docker push "$REGISTRY/syndra-etl:$GIT_SHA"
    docker push "$REGISTRY/syndra-etl:latest"
fi
if [ "$BUILD_DEMO" = true ]; then
    docker push "$REGISTRY/syndra-demo:$GIT_SHA"
    docker push "$REGISTRY/syndra-demo:latest"
fi
if [ "$BUILD_ETL" = false ] && [ "$BUILD_DEMO" = false ]; then
    echo "   Nothing rebuilt: only infrastructure files will be synced."
fi

# Caddy is the shared ingress: a malformed Caddyfile takes the API down along
# with the demo. Validating before the file ever reaches the VPS turns that
# into a failed deploy instead of an outage.
#
# The file is piped in on stdin rather than bind-mounted. A -v mount of a single
# file fails outright when the repo lives on a UNC path (\\wsl.localhost from a
# Windows host), which is exactly how this script gets run here.
echo "-- [3/5] Validating infrastructure configuration..."
docker run --rm -i caddy:2-alpine \
    sh -c 'cat > /tmp/Caddyfile && caddy validate --adapter caddyfile --config /tmp/Caddyfile' \
    < "$INFRA/Caddyfile"

# Prometheus refuses to start on a malformed config and, unlike Caddy, it fails
# alone and quietly: the API keeps serving while metrics collection is simply
# gone, and the gap only becomes visible when the graph is needed. Checked with
# promtool from the exact image production runs: read out of the compose file
# rather than repeated here, so the two cannot drift apart.
PROM_IMAGE=$(grep -oE 'prom/prometheus:[^[:space:]]+' "$INFRA/docker-compose.prod.yml" | head -1)
if [ -z "$PROM_IMAGE" ]; then
    echo "   Could not find the prom/prometheus image in infra/docker-compose.prod.yml"
    exit 1
fi
docker run --rm -i --entrypoint sh "$PROM_IMAGE" \
    -c 'cat > /tmp/prometheus.yml && promtool check config /tmp/prometheus.yml' \
    < "$INFRA/prometheus.yml"

echo "-- [4/5] Syncing infrastructure to VPS..."
scp "$INFRA/docker-compose.prod.yml" "$VPS_USER@$VPS_IP:$DEPLOY_DIR/docker-compose.yml"
scp "$INFRA/Caddyfile" "$VPS_USER@$VPS_IP:$DEPLOY_DIR/Caddyfile"

# Whether prometheus.yml changed decides whether Prometheus gets restarted
# below, so the comparison has to happen before the file is overwritten.
PROM_CONF_CHANGED=true
if [ "$(remote "md5sum '$DEPLOY_DIR/prometheus.yml' 2>/dev/null | cut -d' ' -f1")" \
   = "$(md5sum "$INFRA/prometheus.yml" | cut -d' ' -f1)" ]; then
    PROM_CONF_CHANGED=false
fi
scp "$INFRA/prometheus.yml" "$VPS_USER@$VPS_IP:$DEPLOY_DIR/prometheus.yml"

# Pin before pulling: compose resolves the image tags from these variables.
write_remote_tag ETL_TAG "$ETL_TAG"
write_remote_tag DEMO_TAG "$DEMO_TAG"

echo "-- [5/5] Restarting containers on VPS (etl=$ETL_TAG demo=$DEMO_TAG)..."
remote "cd '$DEPLOY_DIR' && docker compose pull && docker compose up -d --remove-orphans"

# Both Caddy and Prometheus read their configuration from a bind mount, and a
# bind mount is invisible to `docker compose up -d`: the file on disk changes,
# nothing about the container definition does, so the container is left running
# whatever it parsed at boot. This is not hypothetical: the 403 on /metrics was
# written, validated, shipped and silently not applied, and the endpoint served
# 200 to the public internet until Caddy was reloaded by hand.
#
# Caddy is reloaded unconditionally because the reload is graceful and costs
# nothing: it swaps the config with no dropped connections.
echo "-- Reloading Caddy (bind-mounted config is not picked up by up -d)..."
remote "cd '$DEPLOY_DIR' && docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile" \
    || { echo "   Caddy reload FAILED: it is still serving the previous config."; exit 1; }

# Prometheus has no graceful reload without --web.enable-lifecycle, which would
# add a mutating admin endpoint for the sake of a config that changes twice a
# year. A restart costs a few missed scrapes and no data: the TSDB is on a
# volume and the WAL survives. Conditional, so ordinary deploys leave the series
# unbroken.
if [ "$PROM_CONF_CHANGED" = true ]; then
    echo "-- prometheus.yml changed: restarting Prometheus..."
    remote "cd '$DEPLOY_DIR' && docker compose restart prometheus"
fi

echo "-- Deployment completed. etl=$ETL_TAG demo=$DEMO_TAG"
echo "-- Roll back with: ./deploy.sh --rollback etl=<sha>   (or demo=<sha>)"
