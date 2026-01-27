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

# Step 1: Stop and remove existing container
echo -e "${YELLOW}[1/4] Stopping existing container...${NC}"
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    docker-compose -f ${COMPOSE_FILE} down || true
    echo -e "${GREEN}✓ Stopped and removed existing container${NC}"
else
    echo "  No existing container found"
fi
echo ""

# Step 2: Remove old image (optional, uncomment if you want clean builds)
# echo -e "${YELLOW}[2/4] Removing old image...${NC}"
# docker rmi ${IMAGE_NAME}:${IMAGE_TAG} 2>/dev/null || true
# echo ""

# Step 3: Build new image
echo -e "${YELLOW}[2/4] Building Docker image...${NC}"
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} -f deployment/Dockerfile . || {
    echo -e "${RED}ERROR: Docker build failed${NC}"
    exit 1
}
echo -e "${GREEN}✓ Image built successfully${NC}"
echo ""

# Step 4: Start new container
echo -e "${YELLOW}[3/4] Starting new container...${NC}"
docker-compose -f ${COMPOSE_FILE} up -d || {
    echo -e "${RED}ERROR: Failed to start container${NC}"
    exit 1
}
echo -e "${GREEN}✓ Container started${NC}"
echo ""

# Step 5: Verify
echo -e "${YELLOW}[4/4] Verifying deployment...${NC}"
sleep 3

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${GREEN}✓ Container is running${NC}"
    echo ""
    echo "View logs with:"
    echo "  docker logs -f ${CONTAINER_NAME}"
    echo ""
    echo "Stop with:"
    echo "  docker-compose -f ${COMPOSE_FILE} down"
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
