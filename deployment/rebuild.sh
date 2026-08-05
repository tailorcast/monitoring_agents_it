#!/bin/bash
set -e

# Monitoring Agent - Local Rebuild and Run Script
# Builds Docker image, removes old container, and starts new one

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

IMAGE_NAME="monitoring-agent"
IMAGE_TAG="latest"
CONTAINER_NAME="monitoring-agent"
COMPOSE_FILE="deployment/docker-compose.yml"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Monitoring Agent - Rebuild & Run${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if config files exist
if [ ! -f "config/config.yaml" ]; then
    echo -e "${RED}ERROR: config/config.yaml not found${NC}"
    echo "Create it from config/config.example.yaml first"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo -e "${RED}ERROR: .env file not found${NC}"
    echo "Create it from .env.example first"
    exit 1
fi

# Check if secrets folder exists (warning only, not required for all setups)
if [ ! -d "secrets" ] || [ -z "$(ls -A secrets 2>/dev/null)" ]; then
    echo -e "${YELLOW}WARNING: secrets/ folder is empty or missing${NC}"
    echo "If you need SSH key access to VPS servers, add keys to secrets/ folder"
    echo ""
fi

# Step 1: Stop and remove existing container
echo -e "${YELLOW}[1/4] Stopping existing container...${NC}"
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    docker compose -f ${COMPOSE_FILE} down || true
    echo -e "${GREEN}✓ Stopped and removed existing container${NC}"
else
    echo "  No existing container found"
fi
echo ""

# Step 2+3: Build and start in one step.
#
# Build via `compose up --build` rather than a separate `docker build`: compose
# only runs the image named by the compose file, so a separately built and
# tagged image can be silently ignored, leaving stale code running. One command
# means the image built and the image started cannot diverge.
#
# Pass --no-cache to force a clean rebuild:  ./deployment/rebuild.sh --no-cache
BUILD_ARGS=""
if [ "$1" = "--no-cache" ]; then
    BUILD_ARGS="--no-cache"
    echo -e "${YELLOW}Clean rebuild requested (--no-cache)${NC}"
    echo ""
fi

# Stamp the current revision into the image so the verify step can prove which
# code is running. Falls back to "unknown" outside a git checkout.
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
export GIT_SHA

echo -e "${YELLOW}[2/4] Building image and starting container (${GIT_SHA})...${NC}"
if [ -n "${BUILD_ARGS}" ]; then
    docker compose -f ${COMPOSE_FILE} build ${BUILD_ARGS} || {
        echo -e "${RED}ERROR: Docker build failed${NC}"
        exit 1
    }
fi
docker compose -f ${COMPOSE_FILE} up -d --build || {
    echo -e "${RED}ERROR: Build or start failed${NC}"
    exit 1
}
echo -e "${GREEN}✓ Image built and container started${NC}"
echo ""

# Step 3: Confirm the running container has the code we just built
echo -e "${YELLOW}[3/4] Verifying running revision...${NC}"
sleep 3

RUNNING_SHA="$(docker compose -f ${COMPOSE_FILE} exec -T monitoring-agent \
    printenv GIT_SHA 2>/dev/null | tr -d '\r')" || RUNNING_SHA=""

if [ "${RUNNING_SHA}" = "${GIT_SHA}" ]; then
    echo -e "${GREEN}✓ Running revision matches working tree (${RUNNING_SHA})${NC}"
elif [ -z "${RUNNING_SHA}" ]; then
    echo -e "${YELLOW}WARNING: could not read GIT_SHA from the container${NC}"
    echo "  The container may still be starting, or predates revision stamping."
else
    echo -e "${RED}✗ STALE DEPLOY: container is running ${RUNNING_SHA}, expected ${GIT_SHA}${NC}"
    echo ""
    echo "The container did not pick up the new image. Try:"
    echo "  ./deployment/rebuild.sh --no-cache"
    exit 1
fi

if [ -n "$(git status --porcelain src/ 2>/dev/null)" ]; then
    echo -e "${YELLOW}NOTE: src/ has uncommitted changes — they are in the image,${NC}"
    echo -e "${YELLOW}      but ${GIT_SHA} alone does not describe what is running.${NC}"
fi
echo ""

# Step 4: Confirm the container is still up (it may exit on a config error)
echo -e "${YELLOW}[4/4] Verifying deployment...${NC}"

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${GREEN}✓ Container is running${NC}"
    echo ""
    echo "View logs with:"
    echo "  docker logs -f ${CONTAINER_NAME}"
    echo ""
    echo "Stop with:"
    echo "  docker compose -f ${COMPOSE_FILE} down"
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Deployment Successful!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Showing recent logs:"
    echo ""
    docker logs --tail 20 ${CONTAINER_NAME}
else
    echo -e "${RED}✗ Container failed to start${NC}"
    echo ""
    echo "Check logs with:"
    echo "  docker logs ${CONTAINER_NAME}"
    exit 1
fi
