#!/bin/bash
set -e

echo "=================================================="
echo "IT Infrastructure Monitoring System"
echo "=================================================="

# Wait for network to be ready (helpful in some environments)
echo "Waiting for network initialization..."
sleep 5

# Verify configuration file exists
if [ ! -f /app/config/config.yaml ]; then
    echo "ERROR: Configuration file not found at /app/config/config.yaml"
    echo "Please create it from /app/config/config.example.yaml"
    exit 1
fi

# Verify .env variables are set (optional but recommended)
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "WARNING: TELEGRAM_BOT_TOKEN not set"
fi

if [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "WARNING: TELEGRAM_CHAT_ID not set"
fi

# Set proper permissions for SSH keys if they exist
if [ -d /app/secrets ]; then
    echo "Setting SSH key permissions..."
    find /app/secrets -type f -name "*key*" -exec chmod 600 {} \; 2>/dev/null || true
fi

echo "Starting monitoring system..."
echo "=================================================="

# Run the application with any provided arguments
# If no arguments, runs with scheduler (default)
exec python -m src.main "$@"
