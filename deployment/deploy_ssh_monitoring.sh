#!/bin/bash
# Deploy CloudWatch Disk Monitoring to EC2 Instance via SSH
# Usage: ./deploy_ssh_monitoring.sh <instance_host> [ssh_user]
#
# Example:
#   ./deploy_ssh_monitoring.sh spim_vm3
#   ./deploy_ssh_monitoring.sh 172.31.26.135 ubuntu
#   ./deploy_ssh_monitoring.sh ec2-user@spim_vm3

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Configuration
MONITORING_DIR="/opt/monitoring"
LOG_DIR="~/logs"
SCRIPT_NAME="publish_metrics.py"
CRON_INTERVAL="*/5"  # Every 5 minutes

# Function to print colored output
print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_header() {
    echo ""
    echo "========================================"
    echo "$1"
    echo "========================================"
}

# Check arguments
if [ $# -lt 1 ]; then
    print_error "Usage: $0 <instance_host> [ssh_user]"
    echo ""
    echo "Examples:"
    echo "  $0 spim_vm3"
    echo "  $0 172.31.26.135 ubuntu"
    echo "  $0 ec2-user@spim_vm3"
    exit 1
fi

# Parse arguments
INSTANCE_HOST="$1"
SSH_USER="${2:-}"

# If user is specified in host (user@host), parse it
if [[ "$INSTANCE_HOST" == *"@"* ]]; then
    SSH_USER="${INSTANCE_HOST%%@*}"
    INSTANCE_HOST="${INSTANCE_HOST#*@}"
fi

# Build SSH connection string
if [ -n "$SSH_USER" ]; then
    SSH_TARGET="${SSH_USER}@${INSTANCE_HOST}"
else
    SSH_TARGET="${INSTANCE_HOST}"
fi

print_header "CloudWatch Disk Monitoring Deployment"
print_info "Target: $SSH_TARGET"
echo ""

# Step 1: Test SSH connectivity
print_info "Testing SSH connectivity..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$SSH_TARGET" "echo 'SSH OK'" >/dev/null 2>&1; then
    print_error "Cannot connect to $SSH_TARGET"
    print_info "Ensure SSH key is configured and host is reachable"
    exit 1
fi
print_success "SSH connection successful"

# Step 2: Check if script exists locally
print_info "Checking local files..."
if [ ! -f "$SCRIPT_DIR/$SCRIPT_NAME" ]; then
    print_error "Script not found: $SCRIPT_DIR/$SCRIPT_NAME"
    exit 1
fi
print_success "Found $SCRIPT_NAME"

# Step 3: Get instance metadata to verify it's an EC2 instance
print_info "Verifying instance is an EC2 instance..."
INSTANCE_ID=$(ssh "$SSH_TARGET" 'python3 -c "
import requests
import sys
try:
    token = requests.put(\"http://169.254.169.254/latest/api/token\",
                        headers={\"X-aws-ec2-metadata-token-ttl-seconds\": \"21600\"},
                        timeout=2).text
    instance_id = requests.get(\"http://169.254.169.254/latest/meta-data/instance-id\",
                              headers={\"X-aws-ec2-metadata-token\": token},
                              timeout=2).text
    print(instance_id)
except:
    sys.exit(1)
" 2>/dev/null' || echo "")

if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" == "404" ]; then
    print_error "Cannot retrieve instance metadata. Is this an EC2 instance?"
    print_warning "Metadata service not accessible or instance is not EC2"
    exit 1
fi
print_success "Verified EC2 instance: $INSTANCE_ID"

# Step 4: Check IAM role
print_info "Checking IAM role..."
IAM_ROLE=$(ssh "$SSH_TARGET" 'python3 -c "
import requests
try:
    token = requests.put(\"http://169.254.169.254/latest/api/token\",
                        headers={\"X-aws-ec2-metadata-token-ttl-seconds\": \"21600\"},
                        timeout=2).text
    role = requests.get(\"http://169.254.169.254/latest/meta-data/iam/security-credentials/\",
                       headers={\"X-aws-ec2-metadata-token\": token},
                       timeout=2).text
    print(role)
except:
    print(\"\")
" 2>/dev/null' || echo "")

if [ -z "$IAM_ROLE" ]; then
    print_error "No IAM role attached to instance"
    print_warning "Attach an IAM role with CloudWatch PutMetricData permission"
    exit 1
fi
print_success "IAM role attached: $IAM_ROLE"

# Step 5: Check Python dependencies
print_info "Checking Python dependencies..."
MISSING_DEPS=$(ssh "$SSH_TARGET" 'python3 -c "
import sys
missing = []
try:
    import boto3
except ImportError:
    missing.append(\"boto3\")
try:
    import requests
except ImportError:
    missing.append(\"requests\")
print(\",\".join(missing))
" 2>/dev/null' || echo "boto3,requests")

if [ -n "$MISSING_DEPS" ]; then
    print_warning "Missing Python packages: $MISSING_DEPS"
    print_info "Installing Python dependencies..."

    # Detect OS type
    OS_TYPE=$(ssh "$SSH_TARGET" 'cat /etc/os-release 2>/dev/null | grep "^ID=" | cut -d= -f2 | tr -d "\""' || echo "unknown")

    INSTALL_SUCCESS=false

    # Try system package manager first (preferred method)
    case "$OS_TYPE" in
        amzn)
            print_info "Detected Amazon Linux, using system packages..."
            if ssh "$SSH_TARGET" 'command -v dnf >/dev/null 2>&1'; then
                # Amazon Linux 2023 uses dnf
                ssh "$SSH_TARGET" 'sudo dnf install -y python3-boto3 python3-requests >/dev/null 2>&1' && INSTALL_SUCCESS=true
            else
                # Amazon Linux 2 uses yum
                ssh "$SSH_TARGET" 'sudo yum install -y python3-boto3 python3-requests >/dev/null 2>&1' && INSTALL_SUCCESS=true
            fi
            ;;
        ubuntu|debian)
            print_info "Detected $OS_TYPE, using apt..."
            ssh "$SSH_TARGET" 'sudo apt-get update >/dev/null 2>&1 && sudo apt-get install -y python3-boto3 python3-requests >/dev/null 2>&1' && INSTALL_SUCCESS=true
            ;;
        rhel|centos|fedora)
            print_info "Detected $OS_TYPE, using system packages..."
            if ssh "$SSH_TARGET" 'command -v dnf >/dev/null 2>&1'; then
                ssh "$SSH_TARGET" 'sudo dnf install -y python3-boto3 python3-requests >/dev/null 2>&1' && INSTALL_SUCCESS=true
            else
                ssh "$SSH_TARGET" 'sudo yum install -y python3-boto3 python3-requests >/dev/null 2>&1' && INSTALL_SUCCESS=true
            fi
            ;;
        *)
            print_info "Unknown OS, trying pip..."
            ssh "$SSH_TARGET" 'python3 -m pip install --user boto3 requests >/dev/null 2>&1' && INSTALL_SUCCESS=true
            ;;
    esac

    # If system packages failed, try pip as fallback
    if [ "$INSTALL_SUCCESS" = false ]; then
        print_info "System packages failed, trying pip..."
        ssh "$SSH_TARGET" 'python3 -m pip install --user boto3 requests >/dev/null 2>&1' && INSTALL_SUCCESS=true
    fi

    # If everything failed, provide OS-specific instructions
    if [ "$INSTALL_SUCCESS" = false ]; then
        print_error "Failed to install dependencies automatically"
        echo ""
        print_warning "Please install manually based on your OS:"
        echo ""
        case "$OS_TYPE" in
            amzn)
                echo "  # Amazon Linux 2023:"
                echo "  ssh $SSH_TARGET 'sudo dnf install -y python3-boto3 python3-requests'"
                echo ""
                echo "  # Amazon Linux 2:"
                echo "  ssh $SSH_TARGET 'sudo yum install -y python3-boto3 python3-requests'"
                ;;
            ubuntu|debian)
                echo "  ssh $SSH_TARGET 'sudo apt-get update && sudo apt-get install -y python3-boto3 python3-requests'"
                ;;
            rhel|centos|fedora)
                echo "  # RHEL/CentOS 9+ / Fedora:"
                echo "  ssh $SSH_TARGET 'sudo dnf install -y python3-boto3 python3-requests'"
                echo ""
                echo "  # RHEL/CentOS 7-8:"
                echo "  ssh $SSH_TARGET 'sudo yum install -y python3-boto3 python3-requests'"
                ;;
            *)
                echo "  ssh $SSH_TARGET 'python3 -m pip install --user boto3 requests'"
                ;;
        esac
        echo ""
        echo "  Then re-run: $0 $INSTANCE_HOST"
        echo ""
        print_info "See docs/PYTHON_DEPENDENCIES.md for detailed instructions"
        exit 1
    fi

    print_success "Dependencies installed via system packages"
else
    print_success "All Python dependencies available"
fi

# Step 6: Create monitoring directory
print_info "Creating monitoring directory..."
ssh "$SSH_TARGET" "sudo mkdir -p $MONITORING_DIR && sudo chown \$(whoami):\$(id -gn) $MONITORING_DIR" || {
    print_error "Failed to create $MONITORING_DIR"
    exit 1
}
print_success "Created $MONITORING_DIR"

# Step 7: Copy script to instance
print_info "Copying $SCRIPT_NAME to instance..."
scp -q "$SCRIPT_DIR/$SCRIPT_NAME" "$SSH_TARGET:/tmp/$SCRIPT_NAME" || {
    print_error "Failed to copy script"
    exit 1
}
ssh "$SSH_TARGET" "mv /tmp/$SCRIPT_NAME $MONITORING_DIR/$SCRIPT_NAME && chmod +x $MONITORING_DIR/$SCRIPT_NAME" || {
    print_error "Failed to move script to final location"
    exit 1
}
print_success "Script deployed to $MONITORING_DIR/$SCRIPT_NAME"

# Step 8: Create log directory
print_info "Creating log directory..."
ssh "$SSH_TARGET" "mkdir -p $LOG_DIR" || {
    print_error "Failed to create log directory"
    exit 1
}
print_success "Created $LOG_DIR"

# Step 9: Test script execution
print_info "Testing script execution..."
TEST_OUTPUT=$(ssh "$SSH_TARGET" "python3 $MONITORING_DIR/$SCRIPT_NAME 2>&1" || echo "FAILED")

if [[ "$TEST_OUTPUT" == *"FAILED"* ]] || [[ "$TEST_OUTPUT" == *"Error"* ]] || [[ "$TEST_OUTPUT" == *"Traceback"* ]]; then
    print_error "Script test failed:"
    echo "$TEST_OUTPUT"
    exit 1
fi

if [[ "$TEST_OUTPUT" == *"✓ Metrics published successfully"* ]]; then
    print_success "Script executed successfully"

    # Extract disk usage from output
    if [[ "$TEST_OUTPUT" =~ disk_used_percent\ =\ ([0-9.]+)% ]]; then
        DISK_USED="${BASH_REMATCH[1]}"
        DISK_FREE=$(echo "100 - $DISK_USED" | bc)
        print_info "Current disk usage: ${DISK_USED}% used, ${DISK_FREE}% free"
    fi
else
    print_warning "Script ran but output unexpected:"
    echo "$TEST_OUTPUT"
fi

# Step 10: Set up cron job
print_info "Setting up cron job (every 5 minutes)..."
ssh "$SSH_TARGET" "(crontab -l 2>/dev/null | grep -v '$SCRIPT_NAME'; echo '$CRON_INTERVAL * * * * /usr/bin/python3 $MONITORING_DIR/$SCRIPT_NAME >> $LOG_DIR/cloudwatch-metrics.log 2>&1') | crontab -" || {
    print_error "Failed to set up cron job"
    exit 1
}
print_success "Cron job configured"

# Step 11: Verify cron job
print_info "Verifying cron job..."
CRON_CHECK=$(ssh "$SSH_TARGET" "crontab -l | grep '$SCRIPT_NAME'" || echo "")
if [ -z "$CRON_CHECK" ]; then
    print_error "Cron job verification failed"
    exit 1
fi
print_success "Cron job verified: $CRON_CHECK"

# Step 12: Wait and verify metrics in CloudWatch
print_header "Deployment Complete"
print_success "Monitoring deployed successfully!"
echo ""
print_info "Instance: $SSH_TARGET"
print_info "Instance ID: $INSTANCE_ID"
print_info "IAM Role: $IAM_ROLE"
print_info "Script: $MONITORING_DIR/$SCRIPT_NAME"
print_info "Logs: $LOG_DIR/cloudwatch-metrics.log"
print_info "Cron: Every 5 minutes"
echo ""
print_info "Metrics will appear in CloudWatch within 2-3 minutes:"
echo "  - Namespace: CWAgent"
echo "  - Metric: disk_used_percent"
echo "  - Dimensions: InstanceId=$INSTANCE_ID, path=/"
echo ""
print_info "To verify metrics are being published:"
echo "  ssh $SSH_TARGET 'tail -f $LOG_DIR/cloudwatch-metrics.log'"
echo ""
print_info "To test CloudWatch query (from local machine):"
echo "  python3 test_single_instance.py  # (update instance_id to $INSTANCE_ID)"
echo ""
print_success "Deployment completed at $(date)"
