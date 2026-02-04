#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== CloudWatch Disk Monitoring Deployment ==="
sudo mkdir -p /opt/monitoring
sudo cp "$SCRIPT_DIR/publish_metrics.py" /opt/monitoring/
sudo chmod +x /opt/monitoring/publish_metrics.py
mkdir -p ~/logs
(crontab -l 2>/dev/null | grep -v publish_metrics; echo "*/30 * * * * /usr/bin/python3 /opt/monitoring/publish_metrics.py >> ~/logs/cloudwatch-metrics.log 2>&1") | crontab -
echo "✓ Deployed! Testing..."
/usr/bin/python3 /opt/monitoring/publish_metrics.py
