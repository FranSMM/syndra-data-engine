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

echo "-- [1/4] Building the new Docker image..."
docker build -t ghcr.io/fransmm/syndra-etl:latest ./backend

echo "-- [2/4] Pushing the image to GitHub Container Registry..."
docker push ghcr.io/fransmm/syndra-etl:latest

echo "-- [3/4] Syncing infrastructure (docker-compose) to VPS..."
scp ./infra/docker-compose.prod.yml $VPS_USER@$VPS_IP:$DEPLOY_DIR/docker-compose.yml

echo "-- [4/4] Restarting containers on VPS..."
ssh $VPS_USER@$VPS_IP << EOF
    cd $DEPLOY_DIR
    docker compose pull
    docker compose up -d --remove-orphans
EOF

echo "-- Deployment completed successfully."
