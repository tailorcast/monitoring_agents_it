# CloudWatch Agent Installation and Configuration Guide

This guide walks you through installing and configuring the CloudWatch Agent on EC2 instances to publish disk metrics for monitoring.

## ⚠️ IMPORTANT: Read This First

**The #1 cause of CloudWatch Agent failures is missing or incorrect IAM permissions!**

Before installing, ensure:
1. ✅ IAM role is attached to your EC2 instance
2. ✅ Role has `cloudwatch:PutMetricData` permission
3. ✅ You can verify the role: `curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/`

**If you skip the IAM setup, the agent will install but FAIL to publish metrics.**

See [Common Issues & Solutions](CLOUDWATCH_AGENT_TROUBLESHOOTING.md) for detailed troubleshooting.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [IAM Permissions Setup](#iam-permissions-setup) ⭐ **Start Here!**
3. [Automated Installation](#automated-installation-recommended)
4. [Manual Installation](#manual-installation)
5. [Configuration](#configuration)
6. [Starting the Agent](#starting-the-agent)
7. [Verification](#verification)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **EC2 Instance**: Running Amazon Linux 2, Ubuntu, RHEL, or CentOS
- **SSH Access**: Ability to SSH into the instance
- **Root/Sudo Access**: Required for installation
- **IAM Role**: Instance MUST have IAM role with CloudWatch permissions (CRITICAL - see below)

---

## IAM Permissions Setup

### Option 1: Using AWS Console

1. **Navigate to IAM Console**: https://console.aws.amazon.com/iam/

2. **Create Policy**:
   - Click "Policies" → "Create policy"
   - Click "JSON" tab
   - Paste the policy from `docs/cloudwatch-agent-iam-policy.json`:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "CloudWatchAgentServerPolicy",
         "Effect": "Allow",
         "Action": [
           "cloudwatch:PutMetricData",
           "ec2:DescribeVolumes",
           "ec2:DescribeTags",
           "logs:PutLogEvents",
           "logs:DescribeLogStreams",
           "logs:DescribeLogGroups",
           "logs:CreateLogStream",
           "logs:CreateLogGroup"
         ],
         "Resource": "*"
       },
       {
         "Sid": "CloudWatchAgentSSMAccess",
         "Effect": "Allow",
         "Action": [
           "ssm:GetParameter"
         ],
         "Resource": "arn:aws:ssm:*:*:parameter/AmazonCloudWatch-*"
       }
     ]
   }
   ```

   - Name: `CloudWatchAgentServerPolicy`
   - Click "Create policy"

3. **Create or Update IAM Role**:
   - Click "Roles" → "Create role" (or edit existing role)
   - Select "AWS service" → "EC2"
   - Attach policies:
     - `CloudWatchAgentServerPolicy` (created above)
     - `CloudWatchAgentAdminPolicy` (AWS managed, optional)
   - Name: `EC2-CloudWatch-Agent-Role`
   - Click "Create role"

4. **Attach Role to EC2 Instance**:
   - Navigate to EC2 Console
   - Select your instance
   - Actions → Security → Modify IAM role
   - Select `EC2-CloudWatch-Agent-Role`
   - Click "Update IAM role"

### Option 2: Using AWS CLI

```bash
# Create the policy
aws iam create-policy \
    --policy-name CloudWatchAgentServerPolicy \
    --policy-document file://docs/cloudwatch-agent-iam-policy.json

# Create the role
aws iam create-role \
    --role-name EC2-CloudWatch-Agent-Role \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "ec2.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }'

# Attach policy to role (replace ACCOUNT_ID)
aws iam attach-role-policy \
    --role-name EC2-CloudWatch-Agent-Role \
    --policy-arn arn:aws:iam::ACCOUNT_ID:policy/CloudWatchAgentServerPolicy

# Create instance profile
aws iam create-instance-profile \
    --instance-profile-name EC2-CloudWatch-Agent-Profile

# Add role to instance profile
aws iam add-role-to-instance-profile \
    --instance-profile-name EC2-CloudWatch-Agent-Profile \
    --role-name EC2-CloudWatch-Agent-Role

# Attach to EC2 instance (replace INSTANCE_ID)
aws ec2 associate-iam-instance-profile \
    --instance-id i-1234567890abcdef0 \
    --iam-instance-profile Name=EC2-CloudWatch-Agent-Profile
```

---

## Automated Installation (Recommended)

Use the provided installation script for quick setup:

### 1. Copy Script to EC2 Instance

```bash
# From your local machine
scp -i /path/to/key.pem docs/cloudwatch-agent-setup.sh ubuntu@your-instance-ip:~/
```

### 2. Run the Script

```bash
# SSH into instance
ssh -i /path/to/key.pem ubuntu@your-instance-ip

# Make script executable
chmod +x cloudwatch-agent-setup.sh

# Run the script
sudo ./cloudwatch-agent-setup.sh
```

The script will:
- ✅ Detect your OS automatically
- ✅ Download and install CloudWatch Agent
- ✅ Create configuration file
- ✅ Start the agent
- ✅ Verify installation

**That's it!** Skip to [Verification](#verification) section.

---

## Manual Installation

If you prefer manual installation or the script fails:

### Step 1: SSH into Your EC2 Instance

```bash
ssh -i /path/to/your-key.pem ubuntu@your-instance-public-ip
```

### Step 2: Download CloudWatch Agent

#### Amazon Linux 2 / RHEL / CentOS

```bash
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
sudo rpm -U ./amazon-cloudwatch-agent.rpm
```

#### Ubuntu / Debian

```bash
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i -E ./amazon-cloudwatch-agent.deb
```

#### Other Distributions

Visit: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/download-cloudwatch-agent-commandline.html

### Step 3: Verify Installation

```bash
# Check if installed
which /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl

# Check version
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent --version
```

---

## Configuration

### Step 1: Create Configuration Directory

```bash
sudo mkdir -p /opt/aws/amazon-cloudwatch-agent/etc/
```

### Step 2: Create Configuration File

Create `/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json`:

#### Basic Configuration (Root Filesystem Only)

```bash
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
          "/"
        ]
      }
    }
  }
}
EOF
```

#### Advanced Configuration (All Filesystems + Memory)

```bash
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
          },
          {
            "name": "free",
            "rename": "disk_free",
            "unit": "Gigabytes"
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
          "tmpfs",
          "overlay"
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
```

### Configuration Options Explained

| Option | Description | Recommended Value |
|--------|-------------|-------------------|
| `metrics_collection_interval` | How often metrics are collected (seconds) | `300` (5 minutes) |
| `namespace` | CloudWatch namespace for metrics | `"CWAgent"` (required for monitoring) |
| `resources` | Filesystems to monitor | `["/"]` (root only) or `["*"]` (all) |
| `drop_device` | Whether to include device dimension | `true` (simpler metrics) |
| `ignore_file_system_types` | Exclude temporary filesystems | See example above |

### Step 3: Validate Configuration

```bash
# Check JSON syntax
cat /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json | python3 -m json.tool

# Or use jq if available
jq '.' /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
```

---

## Starting the Agent

### Start CloudWatch Agent

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -s \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
```

**Options explained**:
- `-a fetch-config`: Fetch and apply configuration
- `-m ec2`: Mode is EC2
- `-s`: Start the agent
- `-c file:...`: Path to configuration file

### Check Agent Status

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a query -m ec2 -c default
```

**Expected output**:
```json
{
  "status": "running",
  "starttime": "2024-01-15T10:30:00",
  "configstatus": "configured",
  "version": "1.x.x"
}
```

### Enable Agent on Boot

The agent automatically starts on boot once configured. To verify:

```bash
# Check systemd service
sudo systemctl status amazon-cloudwatch-agent

# Enable if not enabled
sudo systemctl enable amazon-cloudwatch-agent
```

---

## Verification

### 1. Check Agent Logs

```bash
# View recent logs
sudo tail -f /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log

# Check for errors
sudo grep -i error /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
```

**Healthy log output**:
```
[INFO] Configuration file fetched and validated successfully
[INFO] Starting amazon-cloudwatch-agent
[INFO] Successfully published metrics to CloudWatch
```

### 2. Check Local Metrics

```bash
# See what disk metrics are being collected
df -h

# Check memory metrics
free -h
```

### 3. Verify Metrics in CloudWatch Console

1. **Open CloudWatch Console**: https://console.aws.amazon.com/cloudwatch/

2. **Navigate to Metrics**:
   - Click "Metrics" in left sidebar
   - Click "All metrics" tab

3. **Find CWAgent Namespace**:
   - Look for "CWAgent" in the list
   - Click on it

4. **View Disk Metrics**:
   - You should see metrics with dimensions:
     - `InstanceId`: Your instance ID
     - `path`: Mount point (e.g., `/`)
     - `device`: Device name (e.g., `nvme0n1p1`)
     - `fstype`: Filesystem type (e.g., `ext4`)

5. **Graph the Metric**:
   - Select `disk_used_percent`
   - Click "Add to graph"
   - View the graph (may take 5-10 minutes for first datapoint)

### 4. Test with AWS CLI

```bash
# From your local machine (requires AWS CLI configured)

# List metrics
aws cloudwatch list-metrics \
    --namespace CWAgent \
    --metric-name disk_used_percent \
    --dimensions Name=InstanceId,Value=i-1234567890abcdef0

# Get metric data
aws cloudwatch get-metric-statistics \
    --namespace CWAgent \
    --metric-name disk_used_percent \
    --dimensions Name=InstanceId,Value=i-1234567890abcdef0 Name=path,Value=/ \
    --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 300 \
    --statistics Average
```

---

## Troubleshooting

### Issue: Agent Status Shows "stopped"

```bash
# Check status
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a query -m ec2 -c default
```

**Solution**:
```bash
# Restart the agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a stop -m ec2

sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -s \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
```

### Issue: No Metrics in CloudWatch

**Possible causes**:

1. **IAM Permissions Missing**
   ```bash
   # Check instance IAM role
   aws ec2 describe-instances --instance-ids i-YOUR-INSTANCE-ID \
       --query 'Reservations[0].Instances[0].IamInstanceProfile'
   ```
   - Ensure role has `cloudwatch:PutMetricData` permission

2. **Wrong Namespace**
   ```bash
   # Verify config has correct namespace
   grep -A5 '"namespace"' /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
   ```
   - Must be `"namespace": "CWAgent"`

3. **Agent Not Running**
   ```bash
   # Check process
   ps aux | grep cloudwatch-agent
   ```

4. **Configuration Errors**
   ```bash
   # Check for JSON syntax errors
   sudo tail -100 /opt/aws/amazon-cloudwatch-agent/logs/configuration-validation.log
   ```

### Issue: Metrics Delayed

**This is normal!** CloudWatch metrics have a 5-15 minute delay.

- Standard resolution metrics: Published every 5 minutes
- CloudWatch processing: Additional 5-10 minutes
- **Wait 15-20 minutes** after starting agent before expecting metrics

### Issue: Wrong Filesystem Monitored

```bash
# Check what filesystems exist
df -h

# Update config to monitor specific filesystem
sudo nano /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
```

Change:
```json
"resources": ["/"]          // Only root
"resources": ["/data"]      // Only /data
"resources": ["*"]          // All filesystems
```

Then restart agent.

### Issue: Permission Denied Errors

```bash
# Check log ownership
ls -la /opt/aws/amazon-cloudwatch-agent/logs/

# Fix permissions
sudo chown -R root:root /opt/aws/amazon-cloudwatch-agent/
```

### Issue: High Costs

If you're concerned about CloudWatch costs:

1. **Reduce collection interval**:
   ```json
   "metrics_collection_interval": 300  // 5 minutes (recommended)
   // vs
   "metrics_collection_interval": 60   // 1 minute (10x cost)
   ```

2. **Monitor fewer filesystems**:
   ```json
   "resources": ["/"]  // Only root, not all mounts
   ```

3. **Remove unused metrics**:
   - Remove `mem` section if not needed
   - Remove `disk_free` if only using `disk_used_percent`

---

## Agent Management Commands

### Start Agent
```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config -m ec2 -s \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
```

### Stop Agent
```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a stop -m ec2
```

### Query Status
```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a query -m ec2 -c default
```

### Restart Agent
```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a stop -m ec2

sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config -m ec2 -s \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
```

### View Logs
```bash
# Tail logs in real-time
sudo tail -f /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log

# Check configuration validation
sudo cat /opt/aws/amazon-cloudwatch-agent/logs/configuration-validation.log

# Check all logs
sudo ls -lh /opt/aws/amazon-cloudwatch-agent/logs/
```

---

## Uninstalling CloudWatch Agent

If you need to uninstall:

### Amazon Linux / RHEL / CentOS
```bash
sudo rpm -e amazon-cloudwatch-agent
```

### Ubuntu / Debian
```bash
sudo dpkg -r amazon-cloudwatch-agent
```

### Remove Configuration
```bash
sudo rm -rf /opt/aws/amazon-cloudwatch-agent/
```

---

## Multiple Instances Setup

To set up CloudWatch Agent on multiple instances:

### Option 1: Manual SSH (Small Scale)
```bash
# Loop through instances
for ip in 10.0.1.10 10.0.1.11 10.0.1.12; do
  echo "Setting up $ip..."
  scp -i key.pem cloudwatch-agent-setup.sh ubuntu@$ip:~/
  ssh -i key.pem ubuntu@$ip 'sudo ~/cloudwatch-agent-setup.sh'
done
```

### Option 2: AWS Systems Manager (Recommended for Scale)

Use AWS Systems Manager Run Command to deploy to multiple instances at once.

1. **Create SSM Document** with agent installation script
2. **Target instances** by tag or instance ID
3. **Execute** across all instances simultaneously

See: https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-rc-setting-up.html

### Option 3: User Data (New Instances)

For new EC2 instances, add to User Data:
```bash
#!/bin/bash
wget https://your-s3-bucket.s3.amazonaws.com/cloudwatch-agent-setup.sh
chmod +x cloudwatch-agent-setup.sh
./cloudwatch-agent-setup.sh
```

---

## Next Steps

After installing CloudWatch Agent:

1. **Wait 15-20 minutes** for first metrics to appear in CloudWatch

2. **Enable disk monitoring** in your monitoring config:
   ```yaml
   ec2_instances:
     - instance_id: "i-1234567890abcdef0"
       name: "prod-server"
       region: "us-east-1"
       monitor_disk: true  # Enable disk monitoring
   ```

3. **Run your monitoring system**:
   ```bash
   python -m src.main --config config/config.yaml
   ```

4. **Verify disk metrics appear** in output:
   ```
   Running, CPU: 25.5%, Disk free: 35.2%
   ```

5. **Set up alerts** for low disk space (RED status)

---

## Additional Resources

- [AWS CloudWatch Agent Documentation](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Install-CloudWatch-Agent.html)
- [CloudWatch Agent Configuration Reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Agent-Configuration-File-Details.html)
- [CloudWatch Metrics Pricing](https://aws.amazon.com/cloudwatch/pricing/)
- [Troubleshooting CloudWatch Agent](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/troubleshooting-CloudWatch-Agent.html)

---

## Support

For issues with this setup:

1. Check [Troubleshooting](#troubleshooting) section above
2. Review agent logs: `/opt/aws/amazon-cloudwatch-agent/logs/`
3. See full documentation: `docs/EC2_DISK_MONITORING.md`
4. File an issue in the project repository
