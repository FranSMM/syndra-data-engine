#!/bin/bash
set -e

# Load private variables from .env
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo ".env file not found. Make sure you have VPS_USER, VPS_IP and DEPLOY_DIR configured."
    exit 1
fi

# Validate that they exist
if [ -z "$VPS_IP" ] || [ -z "$VPS_USER" ] || [ -z "$DEPLOY_DIR" ]; then
    echo "Missing VPS_USER, VPS_IP or DEPLOY_DIR variables in your .env"
    exit 1
fi

# Check that there are no unpushed commits
if [ -n "$(git log origin/main..HEAD 2>/dev/null)" ]; then
    echo "Error: you have unpushed commits. Run 'git push' first."
    exit 1
fi

echo "-- [1/5] Building the Docker images..."
docker build -t ghcr.io/fransmm/syndra-etl:latest ./backend
docker build -t ghcr.io/fransmm/syndra-demo:latest ./demo

echo "-- [2/5] Pushing the images to GitHub Container Registry..."
docker push ghcr.io/fransmm/syndra-etl:latest
docker push ghcr.io/fransmm/syndra-demo:latest

# Caddy is the shared ingress: a malformed Caddyfile takes the API down along
# with the demo. Validating before the file ever reaches the VPS turns that
# into a failed deploy instead of an outage.
#
# The file is piped in on stdin rather than bind-mounted. A -v mount of a
# single file fails outright when the repo lives on a UNC path (\\wsl.localhost
# from a Windows host), which is exactly how this script gets run here.
echo "-- [3/5] Validating the Caddyfile..."
docker run --rm -i caddy:2-alpine \
    sh -c 'cat > /tmp/Caddyfile && caddy validate --adapter caddyfile --config /tmp/Caddyfile' \
    < ./infra/Caddyfile

echo "-- [4/5] Syncing infrastructure to VPS..."
scp ./infra/docker-compose.prod.yml $VPS_USER@$VPS_IP:$DEPLOY_DIR/docker-compose.yml
scp ./infra/Caddyfile $VPS_USER@$VPS_IP:$DEPLOY_DIR/Caddyfile

echo "-- [5/5] Restarting containers on VPS..."
ssh $VPS_USER@$VPS_IP << EOF
    cd $DEPLOY_DIR
    docker compose pull
    docker compose up -d --remove-orphans
EOF

echo "-- Deployment completed successfully."
