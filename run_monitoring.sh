#!/bin/bash
# Monitoring System Runner
# Loads environment variables and runs the monitoring system

set -e

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Load environment variables from .env
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)
    echo "✅ Environment loaded"
else
    echo "❌ Error: .env file not found"
    exit 1
fi

# Verify critical vars are set
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ Error: TELEGRAM_BOT_TOKEN not set"
    exit 1
fi

if [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "❌ Error: TELEGRAM_CHAT_ID not set"
    exit 1
fi

echo "✅ TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:0:10}... (${#TELEGRAM_BOT_TOKEN} chars)"
echo "✅ TELEGRAM_CHAT_ID: $TELEGRAM_CHAT_ID"
echo ""

# Parse arguments
CONFIG_FILE="${1:-config/config.yaml}"
shift || true  # Remove first argument, ignore error if no args

echo "Running monitoring system..."
echo "  Config: $CONFIG_FILE"
echo "  Additional args: $@"
echo ""

# Run the monitoring system with all remaining arguments
if [ $# -eq 0 ]; then
    # No additional arguments - run scheduler
    echo "Starting scheduler mode (runs every hour based on cron schedule in config)..."
    python -m src.main --config "$CONFIG_FILE"
else
    # Pass all remaining arguments
    python -m src.main --config "$CONFIG_FILE" "$@"
fi
