#!/bin/bash
set -e

# IT Infrastructure Monitoring System - EC2 Deployment Script
#
# This script automates deployment to an EC2 instance:
# 1. Builds Docker image locally
# 2. Saves and compresses image
# 3. Copies to EC2 via SCP
# 4. Loads and starts container on EC2
#
# Usage:
#   ./deployment/deploy.sh [EC2_HOST] [SSH_KEY_PATH]
#
# Example:
#   ./deployment/deploy.sh ec2-user@54.123.45.67 ~/.ssh/monitoring-key.pem

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
EC2_HOST="${1:-ec2-user@your-ec2-instance.com}"
SSH_KEY="${2:-~/.ssh/monitoring-agent.pem}"
IMAGE_NAME="monitoring-agent"
IMAGE_TAG="latest"
REMOTE_DIR="/home/ec2-user/monitoring_agents"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Monitoring Agent - EC2 Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Validate inputs
if [ "$EC2_HOST" = "ec2-user@your-ec2-instance.com" ]; then
    echo -e "${RED}ERROR: Please provide EC2 host${NC}"
    echo "Usage: $0 <ec2-user@host> <ssh-key-path>"
    exit 1
fi

if [ ! -f "$SSH_KEY" ]; then
    echo -e "${RED}ERROR: SSH key not found: $SSH_KEY${NC}"
    exit 1
fi

echo "Target: $EC2_HOST"
echo "SSH Key: $SSH_KEY"
echo ""

# Step 1: Build Docker image
echo -e "${YELLOW}[1/5] Building Docker image...${NC}"
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} -f deployment/Dockerfile . || {
    echo -e "${RED}ERROR: Docker build failed${NC}"
    exit 1
}
echo -e "${GREEN}✓ Image built successfully${NC}"
echo ""

# Step 2: Save and compress image
echo -e "${YELLOW}[2/5] Saving Docker image...${NC}"
TMP_IMAGE="/tmp/${IMAGE_NAME}-${IMAGE_TAG}.tar.gz"
docker save ${IMAGE_NAME}:${IMAGE_TAG} | gzip > $TMP_IMAGE || {
    echo -e "${RED}ERROR: Failed to save image${NC}"
    exit 1
}
IMAGE_SIZE=$(du -h $TMP_IMAGE | cut -f1)
echo -e "${GREEN}✓ Image saved: $TMP_IMAGE ($IMAGE_SIZE)${NC}"
echo ""

# Step 3: Copy files to EC2
echo -e "${YELLOW}[3/5] Copying files to EC2...${NC}"

# Copy Docker image
echo "  - Copying Docker image..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no $TMP_IMAGE ${EC2_HOST}:/tmp/ || {
    echo -e "${RED}ERROR: Failed to copy image${NC}"
    exit 1
}

# Copy docker-compose.yml
echo "  - Copying docker-compose.yml..."
scp -i "$SSH_KEY" deployment/docker-compose.yml ${EC2_HOST}:${REMOTE_DIR}/ || {
    echo -e "${RED}ERROR: Failed to copy docker-compose.yml${NC}"
    exit 1
}

# Copy .env (if exists locally)
if [ -f ".env" ]; then
    echo "  - Copying .env..."
    scp -i "$SSH_KEY" .env ${EC2_HOST}:${REMOTE_DIR}/ || {
        echo -e "${YELLOW}WARNING: Failed to copy .env${NC}"
    }
fi

# Copy config.yaml (if exists locally)
if [ -f "config/config.yaml" ]; then
    echo "  - Copying config.yaml..."
    ssh -i "$SSH_KEY" ${EC2_HOST} "mkdir -p ${REMOTE_DIR}/config"
    scp -i "$SSH_KEY" config/config.yaml ${EC2_HOST}:${REMOTE_DIR}/config/ || {
        echo -e "${YELLOW}WARNING: Failed to copy config.yaml${NC}"
    }
fi

echo -e "${GREEN}✓ Files copied successfully${NC}"
echo ""

# Step 4: Deploy on EC2
echo -e "${YELLOW}[4/5] Deploying on EC2...${NC}"
ssh -i "$SSH_KEY" ${EC2_HOST} << 'ENDSSH'
set -e

echo "  - Loading Docker image..."
cd /tmp
docker load < monitoring-agent-latest.tar.gz

echo "  - Stopping existing container..."
cd ~/monitoring_agents
docker-compose down 2>/dev/null || true

echo "  - Starting new container..."
docker-compose up -d

echo "  - Cleaning up..."
rm -f /tmp/monitoring-agent-latest.tar.gz

ENDSSH

echo -e "${GREEN}✓ Deployment complete${NC}"
echo ""

# Step 5: Verify deployment
echo -e "${YELLOW}[5/5] Verifying deployment...${NC}"
ssh -i "$SSH_KEY" ${EC2_HOST} << 'ENDSSH'
cd ~/monitoring_agents

# Check container status
if docker-compose ps | grep -q "Up"; then
    echo "  ✓ Container is running"
else
    echo "  ✗ Container is not running!"
    exit 1
fi

# Show recent logs
echo ""
echo "Recent logs:"
docker-compose logs --tail=20

ENDSSH

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Deployment Successful!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Next steps:"
    echo "  - View logs: ssh -i $SSH_KEY ${EC2_HOST} 'cd ~/monitoring_agents && docker-compose logs -f'"
    echo "  - Check status: ssh -i $SSH_KEY ${EC2_HOST} 'cd ~/monitoring_agents && docker-compose ps'"
    echo "  - Stop: ssh -i $SSH_KEY ${EC2_HOST} 'cd ~/monitoring_agents && docker-compose down'"
else
    echo -e "${RED}Deployment verification failed!${NC}"
    exit 1
fi

# Cleanup local temp file
rm -f $TMP_IMAGE
