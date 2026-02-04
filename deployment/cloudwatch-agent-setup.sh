#!/bin/bash
# CloudWatch Agent Installation and Configuration Script
# This script installs and configures CloudWatch Agent on EC2 instances

set -e  # Exit on error

echo "========================================"
echo "CloudWatch Agent Installation Script"
echo "========================================"

# Detect OS
if [ -f /etc/os-release ]; then
  . /etc/os-release
  OS=$ID
  VERSION=$VERSION_ID
else
  echo "Cannot detect OS"
  exit 1
fi

echo "Detected OS: $OS $VERSION"

# Step 1: Download and Install CloudWatch Agent
echo ""
echo "Step 1: Installing CloudWatch Agent..."

case $OS in
  amzn|rhel|centos)
      echo "Installing for Amazon Linux/RHEL/CentOS..."
      wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
      sudo rpm -U ./amazon-cloudwatch-agent.rpm
      rm -f ./amazon-cloudwatch-agent.rpm
      ;;
  ubuntu|debian)
      echo "Installing for Ubuntu/Debian..."
      wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
      sudo dpkg -i -E ./amazon-cloudwatch-agent.deb
      rm -f ./amazon-cloudwatch-agent.deb
      ;;
  *)
      echo "Unsupported OS: $OS"
      exit 1
      ;;
esac

echo "✓ CloudWatch Agent installed successfully"

# Step 2: Create Configuration File
echo ""
echo "Step 2: Creating CloudWatch Agent configuration..."

sudo mkdir -p /opt/aws/amazon-cloudwatch-agent/etc/

# Create the configuration file
sudo tee /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json > /dev/null <<'EOF'
{
"agent": {
  "metrics_collection_interval": 300,
  "run_as_user": "root"
},
"metrics": {
  "namespace": "CWAgent",
  "metrics_collected": {
    "disk": {
      "measurement": [
        {
          "name": "used_percent",
          "rename": "disk_used_percent",
          "unit": "Percent"
        }
      ],
      "metrics_collection_interval": 300,
      "resources": [
        "*"
      ],
      "drop_device": true,
      "ignore_file_system_types": [
        "sysfs",
        "devtmpfs",
        "tmpfs"
      ]
    },
    "mem": {
      "measurement": [
        {
          "name": "mem_used_percent",
          "rename": "memory_used_percent",
          "unit": "Percent"
        }
      ],
      "metrics_collection_interval": 300
    }
  }
}
}
EOF

echo "✓ Configuration file created at: /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json"

# Verify configuration file exists
if [ ! -f /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json ]; then
  echo "✗ ERROR: Configuration file was not created properly"
  exit 1
fi

# Step 3: Verify IAM Role
echo ""
echo "Step 3: Verifying IAM role and permissions..."

# Function to get metadata (supports both IMDSv1 and IMDSv2)
get_metadata() {
  local path=$1
  local token=""

  # Try IMDSv2 first (get session token)
  token=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null)

  if [ -n "$token" ]; then
    # Use IMDSv2 with token
    curl -s -H "X-aws-ec2-metadata-token: $token" "http://169.254.169.254/latest/meta-data/$path" 2>/dev/null
  else
    # Fall back to IMDSv1 (no token)
    curl -s "http://169.254.169.254/latest/meta-data/$path" 2>/dev/null
  fi
}

# Get IAM role name
IAM_ROLE=$(get_metadata "iam/security-credentials/")

# Check if IAM role is attached
if [ -z "$IAM_ROLE" ] || echo "$IAM_ROLE" | grep -q "404\|401\|<html>"; then
  echo "✗ WARNING: No IAM role attached to this EC2 instance!"
  echo ""
  echo "  REQUIRED: Attach an IAM role with CloudWatch permissions:"
  echo "  - cloudwatch:PutMetricData"
  echo "  - ec2:DescribeVolumes"
  echo "  - ec2:DescribeTags"
  echo ""
  echo "  Steps to fix:"
  echo "  1. Go to EC2 Console: https://console.aws.amazon.com/ec2/"
  echo "  2. Select this instance"
  echo "  3. Actions → Security → Modify IAM role"
  echo "  4. Attach role with CloudWatchAgentServerPolicy"
  echo ""
  echo "  Continuing anyway, but agent will fail to publish metrics..."
  echo ""
else
  echo "✓ IAM role attached: $IAM_ROLE"

  # Check if credentials are available
  CREDS=$(get_metadata "iam/security-credentials/$IAM_ROLE")
  if echo "$CREDS" | grep -q "AccessKeyId"; then
    echo "✓ IAM credentials available"
  else
    echo "✗ WARNING: IAM credentials not available"
  fi
fi

# Step 4: Start CloudWatch Agent
echo ""
echo "Step 4: Starting CloudWatch Agent..."

# Stop agent if already running
sudo systemctl stop amazon-cloudwatch-agent 2>/dev/null || true

# Start with configuration
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
  -s

echo "✓ CloudWatch Agent started successfully"

# Step 5: Verify Agent Status
echo ""
echo "Step 5: Verifying agent status..."

sleep 5

# Check if agent process is running
if pgrep -f amazon-cloudwatch-agent > /dev/null; then
  echo "✓ Agent process is running"
else
  echo "✗ Agent process is NOT running"
  exit 1
fi

# Check systemd service status
if systemctl is-active --quiet amazon-cloudwatch-agent; then
  echo "✓ Service is active"
else
  echo "✗ Service is not active"
fi

echo ""
echo "========================================"
echo "Installation Complete!"
echo "========================================"
echo ""

# Wait and check logs for success/errors
echo "Waiting 10 seconds for agent to initialize..."
sleep 10

echo ""
echo "Checking agent logs for errors..."

# Count errors (ensure we get a single integer)
ERROR_COUNT=$(sudo grep -i "error" /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log 2>/dev/null | wc -l | tr -d ' ' || echo "0")
SUCCESS_COUNT=$(sudo grep -i "successfully published" /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log 2>/dev/null | wc -l | tr -d ' ' || echo "0")

# Ensure we have valid integers (remove any whitespace or newlines)
ERROR_COUNT=$(echo "$ERROR_COUNT" | tr -d '\n\r ')
SUCCESS_COUNT=$(echo "$SUCCESS_COUNT" | tr -d '\n\r ')

# Default to 0 if empty
ERROR_COUNT=${ERROR_COUNT:-0}
SUCCESS_COUNT=${SUCCESS_COUNT:-0}

if [ "$ERROR_COUNT" -gt 0 ]; then
  echo "⚠️  Found $ERROR_COUNT errors in logs"
  echo ""
  echo "Recent errors:"
  sudo tail -50 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log | grep -i "error" | tail -3
  echo ""

  # Check for permission errors
  if sudo grep -q "AccessDenied\|NoCredentialProviders" /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log; then
      echo "❌ PERMISSION ISSUE DETECTED"
      echo ""
      echo "   The IAM role lacks required permissions!"
      echo ""
      echo "   Fix: Add this policy to the IAM role:"
      echo "   {{"
      echo "     \"Effect\": \"Allow\","
      echo "     \"Action\": ["
      echo "       \"cloudwatch:PutMetricData\","
      echo "       \"ec2:DescribeVolumes\","
      echo "       \"ec2:DescribeTags\""
      echo "     ],"
      echo "     \"Resource\": \"*\""
      echo "   }}"
      echo ""
      echo "   Then restart: sudo systemctl restart amazon-cloudwatch-agent"
      echo ""
  fi
fi

if [ "$SUCCESS_COUNT" -gt 0 ]; then
  echo "✅ SUCCESS: Agent is publishing metrics to CloudWatch!"
  echo "   Found $SUCCESS_COUNT successful publishes in logs"
else
  echo "⚠️  No successful metric publishes detected yet"
  echo "   This is normal for the first 2-5 minutes"
fi

echo ""
echo "Next steps:"
echo ""
echo "1. Check current agent status:"
echo "   sudo systemctl status amazon-cloudwatch-agent"
echo ""
echo "2. View agent logs:"
echo "   sudo tail -50 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log"
echo ""
echo "3. Wait 15-20 minutes, then verify metrics in CloudWatch Console:"
echo "   - Navigate to: https://console.aws.amazon.com/cloudwatch/"
echo "   - Go to: Metrics → All metrics"
echo "   - Select: 'CWAgent' namespace"
echo "   - Look for: 'disk_used_percent' metric"
echo ""
echo "4. If no IAM role attached or permission errors:"
echo "   - Attach IAM role with 'CloudWatchAgentServerPolicy' (AWS managed)"
echo "   - OR attach role with cloudwatch:PutMetricData permission"
echo "   - Then: sudo systemctl restart amazon-cloudwatch-agent"
echo ""
echo "5. Enable disk monitoring in your config:"
echo "   monitor_disk: true"
echo ""
