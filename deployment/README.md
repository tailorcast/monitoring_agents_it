# Deployment Scripts

This directory contains scripts for deploying CloudWatch monitoring to EC2 instances.

## Quick Start

To deploy disk monitoring to a new EC2 instance:

```bash
./deploy_ssh_monitoring.sh <instance_host>
```

## deploy_ssh_monitoring.sh

Automated deployment script for setting up CloudWatch disk monitoring on EC2 instances via SSH.

### Features

- ✅ Validates SSH connectivity
- ✅ Verifies instance is EC2 with metadata service access
- ✅ Checks IAM role is attached
- ✅ Installs Python dependencies if missing
- ✅ Deploys monitoring script
- ✅ Sets up cron job (every 5 minutes)
- ✅ Tests script execution
- ✅ Provides verification instructions

### Prerequisites

1. **SSH Access**: You must be able to SSH to the target instance
2. **IAM Role**: Instance must have an IAM role with `cloudwatch:PutMetricData` permission
3. **Python 3**: Instance must have Python 3 installed
4. **EC2 Instance**: Must be an AWS EC2 instance with metadata service enabled

### Usage

#### Basic usage (using SSH config host)
```bash
./deploy_ssh_monitoring.sh spim_vm3
```

#### With username
```bash
./deploy_ssh_monitoring.sh spim_vm3 ubuntu
```

#### Using IP address
```bash
./deploy_ssh_monitoring.sh 172.31.26.135 ubuntu
```

#### Using user@host format
```bash
./deploy_ssh_monitoring.sh ubuntu@spim_vm3
```

### What It Does

1. **Tests SSH connectivity** to the target instance
2. **Verifies EC2 instance** by checking metadata service
3. **Checks IAM role** is attached and accessible
4. **Installs dependencies** (boto3, requests) if missing
5. **Creates directory** `/opt/monitoring` for scripts
6. **Deploys script** `publish_metrics.py` to the instance
7. **Sets up cron job** to run every 5 minutes
8. **Tests execution** to ensure metrics publish successfully
9. **Provides verification** instructions and CloudWatch details

### Output Example

```
========================================
CloudWatch Disk Monitoring Deployment
========================================
ℹ Target: ubuntu@spim_vm3

ℹ Testing SSH connectivity...
✓ SSH connection successful
ℹ Checking local files...
✓ Found publish_metrics.py
ℹ Verifying instance is an EC2 instance...
✓ Verified EC2 instance: i-0404e6fa9c8d1f2e5
ℹ Checking IAM role...
✓ IAM role attached: EC2-CloudWatch-Role
ℹ Checking Python dependencies...
✓ All Python dependencies available
ℹ Creating monitoring directory...
✓ Created /opt/monitoring
ℹ Copying publish_metrics.py to instance...
✓ Script deployed to /opt/monitoring/publish_metrics.py
ℹ Creating log directory...
✓ Created ~/logs
ℹ Testing script execution...
✓ Script executed successfully
ℹ Current disk usage: 68.3% used, 31.7% free
ℹ Setting up cron job (every 5 minutes)...
✓ Cron job configured
ℹ Verifying cron job...
✓ Cron job verified: */5 * * * * /usr/bin/python3 /opt/monitoring/publish_metrics.py >> ~/logs/cloudwatch-metrics.log 2>&1

========================================
Deployment Complete
========================================
✓ Monitoring deployed successfully!

ℹ Instance: ubuntu@spim_vm3
ℹ Instance ID: i-0404e6fa9c8d1f2e5
ℹ IAM Role: EC2-CloudWatch-Role
ℹ Script: /opt/monitoring/publish_metrics.py
ℹ Logs: ~/logs/cloudwatch-metrics.log
ℹ Cron: Every 5 minutes

ℹ Metrics will appear in CloudWatch within 2-3 minutes:
  - Namespace: CWAgent
  - Metric: disk_used_percent
  - Dimensions: InstanceId=i-0404e6fa9c8d1f2e5, path=/

ℹ To verify metrics are being published:
  ssh ubuntu@spim_vm3 'tail -f ~/logs/cloudwatch-metrics.log'

ℹ To test CloudWatch query (from local machine):
  python3 test_single_instance.py  # (update instance_id to i-0404e6fa9c8d1f2e5)

✓ Deployment completed at Mon Feb  3 16:45:23 EET 2026
```

### Verification

After deployment, verify metrics are being published:

#### 1. Check logs on the instance
```bash
ssh <instance> 'tail -f ~/logs/cloudwatch-metrics.log'
```

Expected output every 5 minutes:
```
2026-02-03 13:24:07.048078+00:00: Publishing metrics for i-xxx
  disk_used_percent = 75.60%
✓ Metrics published successfully to CloudWatch
```

#### 2. Query CloudWatch from local machine
```bash
# Update test_single_instance.py with the new instance ID
python3 test_single_instance.py
```

#### 3. Check CloudWatch Console
- Navigate to CloudWatch Console
- Go to Metrics → All metrics
- Select namespace: `CWAgent`
- Look for metric: `disk_used_percent`
- Dimensions: `InstanceId` + `path`

#### 4. Test with monitoring system
```bash
# Update config/config.yaml to add the instance with monitor_disk: true
python3 -m src.main
```

### Troubleshooting

#### "Cannot connect to host"
- Verify SSH key is configured: `ssh <host>`
- Check security group allows SSH (port 22)
- Verify hostname/IP is correct

#### "Cannot retrieve instance metadata"
- Ensure target is an EC2 instance (not VPS or on-premise)
- Check metadata service is enabled (IMDSv2)
- Verify network configuration allows metadata access

#### "No IAM role attached"
- Attach an IAM role to the EC2 instance
- Role must include `CloudWatchAgentServerPolicy` or equivalent
- Minimum permissions: `cloudwatch:PutMetricData`

#### "Failed to install dependencies"

**Common Issue**: The deployment script attempts to install boto3 and requests using pip, but some Linux distributions don't have pip installed by default.

**Solution**: Install dependencies using the system package manager instead.

##### Amazon Linux 2023 (AL2023)
Amazon Linux 2023 doesn't include pip by default. Use dnf:

```bash
ssh <host> 'sudo dnf install -y python3-boto3 python3-requests'
```

**Example** (tcper instance):
```bash
$ ssh tcper 'python3 -m pip install --user boto3 requests'
/usr/bin/python3: No module named pip

# Solution:
$ ssh tcper 'sudo dnf install -y python3-boto3 python3-requests'
Last metadata expiration check: 22:51:05 ago
Package python3-requests-2.25.1-1.amzn2023.0.5.noarch is already installed.
Installing:
 python3-boto3         noarch    1.33.6-1.amzn2023.0.1
...
Complete!

# Then re-run deployment:
$ ./deploy_ssh_monitoring.sh tcper
✓ All Python dependencies available
```

##### Amazon Linux 2 (AL2)
```bash
ssh <host> 'sudo yum install -y python3-boto3 python3-requests'
```

##### Ubuntu/Debian
```bash
ssh <host> 'sudo apt-get update && sudo apt-get install -y python3-boto3 python3-requests'
```

##### RHEL/CentOS 7/8
```bash
ssh <host> 'sudo yum install -y python3-boto3 python3-requests'
```

##### RHEL/CentOS 9+ / Fedora
```bash
ssh <host> 'sudo dnf install -y python3-boto3 python3-requests'
```

##### Alternative: Install pip first, then use pip
If you prefer using pip (not recommended for system-wide installs):

```bash
# Amazon Linux 2023
ssh <host> 'sudo dnf install -y python3-pip'

# Amazon Linux 2 / CentOS / RHEL
ssh <host> 'sudo yum install -y python3-pip'

# Ubuntu / Debian
ssh <host> 'sudo apt-get install -y python3-pip'

# Then install packages with pip
ssh <host> 'python3 -m pip install --user boto3 requests'
```

**Note**: System packages (dnf/yum/apt) are preferred over pip for production servers because:
- They're tested with your OS version
- They receive security updates via system updates
- They don't interfere with system Python packages
- No need to manage pip/virtualenv on production servers

##### Verify Installation
After installing, verify the packages work:

```bash
ssh <host> 'python3 -c "import boto3, requests; print(\"✓ boto3:\", boto3.__version__); print(\"✓ requests:\", requests.__version__)"'
```

Expected output:
```
✓ boto3: 1.33.6
✓ requests: 2.25.1
```

Then re-run the deployment script.

#### "Script test failed"
- Check IAM permissions: `aws sts get-caller-identity`
- Verify CloudWatch API access: `aws cloudwatch list-metrics --namespace CWAgent`
- Check logs: `ssh <host> 'cat ~/logs/cloudwatch-metrics.log'`

### Files Deployed

After successful deployment, these files will exist on the target instance:

```
/opt/monitoring/
  └── publish_metrics.py          # Metrics publisher script

~/logs/
  └── cloudwatch-metrics.log      # Execution logs

Cron job: */5 * * * * /usr/bin/python3 /opt/monitoring/publish_metrics.py >> ~/logs/cloudwatch-metrics.log 2>&1
```

### Uninstalling

To remove monitoring from an instance:

```bash
ssh <instance> 'crontab -l | grep -v publish_metrics | crontab -'
ssh <instance> 'rm -rf /opt/monitoring ~/logs/cloudwatch-metrics.log'
```

## Other Files

### publish_metrics.py

Python script that publishes disk metrics to CloudWatch. This is the script that gets deployed to EC2 instances.

**What it does**:
- Retrieves instance ID from EC2 metadata service
- Collects disk usage statistics for root filesystem (`/`)
- Publishes to CloudWatch namespace `CWAgent`
- Includes dimensions: `InstanceId` and `path`

**Execution**:
```bash
python3 publish_metrics.py
```

**Output**:
```
2026-02-03 13:24:07.048078+00:00: Publishing metrics for i-0cb02c48bb5346606
  disk_used_percent = 75.60%
✓ Metrics published successfully to CloudWatch
```

### cloudwatch-agent-setup.sh

Original CloudWatch Agent installation script. This is an alternative approach that installs the full CloudWatch Agent instead of using the Python script approach.

**Note**: The Python script approach (`publish_metrics.py`) is now preferred because it's simpler, easier to maintain, and sufficient for disk monitoring.

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs: `~/logs/cloudwatch-metrics.log` on the instance
3. Verify IAM permissions and network connectivity
4. See `docs/PYTHON_DEPENDENCIES.md` for Python package installation on different Linux distributions
5. See `docs/CW_AGENT_ISSUE.md` for detailed troubleshooting history
