# CloudWatch Agent Quick Start

## 🚀 5-Minute Setup

### Step 0: Verify IAM Role (CRITICAL!)

**BEFORE installing, verify IAM role is attached:**

```bash
# SSH into instance
ssh -i /path/to/key.pem ubuntu@YOUR-IP

# Check for IAM role (supports both IMDSv1 and IMDSv2)
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null)
if [ -n "$TOKEN" ]; then
  curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/security-credentials/
else
  curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/
fi

# Expected: Role name (e.g., "EC2-CloudWatch-Role")
# NOT expected: "404", "401", or HTML error page
```

**If no role attached or you see an error**: See [IAM Role Setup](#-iam-role-setup-required---do-this-first) section above!

### Step 1: Copy and Run Installation Script

```bash
# Copy to EC2 instance
scp -i /path/to/key.pem deployment/cloudwatch-agent-setup.sh ubuntu@YOUR-IP:~/

# SSH into instance (if not already)
ssh -i /path/to/key.pem ubuntu@YOUR-IP

# Run installation
chmod +x cloudwatch-agent-setup.sh
sudo ./cloudwatch-agent-setup.sh
```

**The script will**:
- ✅ Check if IAM role is attached (warns if missing)
- ✅ Install CloudWatch Agent
- ✅ Create configuration file at correct location
- ✅ Start the agent
- ✅ Check logs for permission errors

### 2. Verify Installation

```bash
# Method 1: Check systemd service (most reliable)
sudo systemctl status amazon-cloudwatch-agent

# Expected: Active: active (running)

# Method 2: Check process
ps aux | grep cloudwatch-agent | grep -v grep

# Method 3: View logs for confirmation
sudo tail -20 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log

# Look for: "Successfully published metrics"
```

### 3. Wait for Metrics

⏱️ **Wait 15-20 minutes** for first metrics to appear in CloudWatch

### 4. Enable in Monitoring Config

```yaml
ec2_instances:
  - instance_id: "i-1234567890abcdef0"
    name: "prod-server"
    region: "us-east-1"
    monitor_disk: true  # ← Add this line
```

### 5. Test

```bash
python -m src.main --config config/config.yaml
```

Expected output:
```
✓ prod-server: Running, CPU: 25.5%, Disk free: 35.2%
```

---

## 📋 Prerequisites Checklist

- [ ] EC2 instance running (Amazon Linux 2, Ubuntu, RHEL, or CentOS)
- [ ] SSH access to instance
- [ ] **IAM role attached with CloudWatch permissions** (CRITICAL - see below)
- [ ] Internet access from instance (to download agent)

### ⚠️ CRITICAL: IAM Role Must Be Attached BEFORE Installation

**The CloudWatch Agent CANNOT publish metrics without an IAM role with proper permissions!**

If you skip this step, you'll get errors like:
```
E! AccessDenied: User is not authorized to perform: cloudwatch:PutMetricData
E! NoCredentialProviders: no EC2 instance role found
```

---

## 🔑 IAM Role Setup (REQUIRED - Do This First!)

### ⚠️ YOU MUST DO THIS BEFORE RUNNING THE INSTALLATION SCRIPT

Without proper IAM permissions, the agent will install but **FAIL to publish metrics**.

### Option A: Use AWS Managed Policy (Easiest)

1. **Go to IAM Console**: https://console.aws.amazon.com/iam/

2. **Create Role**:
   - Click **Roles** → **Create role**
   - Select **AWS service** → **EC2** → **Next**

3. **Attach AWS Managed Policy**:
   - Search for: `CloudWatchAgentServerPolicy`
   - ✅ Check the box next to it
   - Click **Next**

4. **Name the Role**:
   - Role name: `EC2-CloudWatch-Role`
   - Click **Create role**

5. **Attach to EC2 Instance**:
   - Go to EC2 Console: https://console.aws.amazon.com/ec2/
   - Select your instance
   - **Actions** → **Security** → **Modify IAM role**
   - Select `EC2-CloudWatch-Role`
   - Click **Update IAM role**

### Option B: Create Custom Policy (More Control)

If the AWS managed policy doesn't exist, create your own:

1. **Go to IAM Console** → **Policies** → **Create policy**

2. **Click JSON tab** and paste:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
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
    }
  ]
}
```

3. **Name policy**: `CloudWatchAgentServerPolicy`

4. **Create role** and attach this policy (follow Option A steps 2-5)

### ✅ Verify IAM Role is Attached

Before installing, verify the role is attached:

```bash
# SSH into your instance first
ssh -i /path/to/key.pem ubuntu@YOUR-INSTANCE-IP

# Check if IAM role is attached (supports both IMDSv1 and IMDSv2)
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null)
if [ -n "$TOKEN" ]; then
  # IMDSv2 (newer instances)
  curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/security-credentials/
else
  # IMDSv1 (older instances)
  curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/
fi

# Should return role name (e.g., "EC2-CloudWatch-Role")
# If you see "404", "401", or HTML error, IAM role is NOT attached!
```

**Or use this simpler one-liner:**
```bash
# This works with both IMDSv1 and IMDSv2
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null) && curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null || curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null
```

### 🚨 Common Mistakes

❌ **WRONG**: Creating policy but not attaching it to a role
❌ **WRONG**: Creating role but not attaching it to the EC2 instance
❌ **WRONG**: Attaching role with `ec2:*` permissions but missing `cloudwatch:PutMetricData`

✅ **CORRECT**: Role attached to instance + Policy with `cloudwatch:PutMetricData` permission

---

## 🔧 Common Commands

### Check Status
```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a query -m ec2 -c default
```

### View Logs
```bash
sudo tail -f /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
```

### Restart Agent
```bash
sudo systemctl restart amazon-cloudwatch-agent
```

### Stop Agent
```bash
sudo systemctl stop amazon-cloudwatch-agent
```

---

## 🐛 Troubleshooting

### ❌ Error: "AccessDenied" or "not authorized to perform: cloudwatch:PutMetricData"

**This is the #1 most common issue!**

Check logs:
```bash
sudo tail -50 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log | grep -i error
```

If you see:
```
E! cloudwatch: code: AccessDenied, message: User: arn:aws:sts::...:assumed-role/EC2-CloudWatch-Role/...
   is not authorized to perform: cloudwatch:PutMetricData
```

**Fix**:
1. Go to IAM Console → Roles → Find `EC2-CloudWatch-Role`
2. Click **Add permissions** → **Attach policies**
3. Search and attach: `CloudWatchAgentServerPolicy` (AWS managed)
4. OR create inline policy with `cloudwatch:PutMetricData` permission
5. Wait 10 seconds, then:
   ```bash
   sudo systemctl restart amazon-cloudwatch-agent
   ```
6. Verify in logs:
   ```bash
   sudo tail -50 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
   # Should see: "Successfully published metrics"
   ```

### ❌ Error: "NoCredentialProviders" or "no EC2 instance role found"

Check logs:
```bash
sudo tail -50 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log | grep -i error
```

If you see:
```
E! cloudwatch: code: NoCredentialProviders, message: no valid providers in chain
EC2RoleRequestError: no EC2 instance role found
```

**Fix**:
1. **No IAM role attached to instance!**
2. See [IAM Role Setup](#-iam-role-setup-required---do-this-first) section
3. Attach IAM role to your EC2 instance
4. Restart agent:
   ```bash
   sudo systemctl restart amazon-cloudwatch-agent
   ```

### ❌ Configuration file not found

If installation script fails or config is missing:

```bash
# Recreate configuration file
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
        "resources": ["/"]
      }
    }
  }
}
EOF

# Restart agent with new config
sudo systemctl stop amazon-cloudwatch-agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config -m ec2 \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s
```

### ❌ Agent shows "stopped"
```bash
sudo systemctl restart amazon-cloudwatch-agent
sudo systemctl status amazon-cloudwatch-agent
```

### ❌ No metrics in CloudWatch after 20 minutes
1. Wait 15-20 minutes (normal delay)
2. Check IAM permissions (see above)
3. Verify namespace is `CWAgent` in config:
   ```bash
   grep namespace /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
   # Should show: "namespace": "CWAgent"
   ```
4. Check logs for errors:
   ```bash
   sudo tail -100 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
   ```

### ❌ File permission errors
```bash
sudo chown -R root:root /opt/aws/amazon-cloudwatch-agent/
sudo systemctl restart amazon-cloudwatch-agent
```

---

## 📖 Full Documentation

- **Complete Setup Guide**: `docs/CLOUDWATCH_AGENT_SETUP_GUIDE.md`
- **EC2 Monitoring**: `docs/EC2_DISK_MONITORING.md`
- **Installation Script**: `docs/cloudwatch-agent-setup.sh`
- **IAM Policy**: `docs/cloudwatch-agent-iam-policy.json`

---

## 💡 Pro Tips

1. **Test with one instance first** before rolling out to all
2. **Use the automated script** for consistency
3. **Wait 15-20 minutes** after setup before expecting metrics
4. **Monitor only root filesystem** (`/`) to reduce costs
5. **Check agent logs** if issues occur

---

## ✅ Success Checklist

After setup, verify:

- [ ] Agent status shows "running"
- [ ] No errors in agent logs
- [ ] Metrics appear in CloudWatch Console (CWAgent namespace)
- [ ] Monitoring system shows disk metrics
- [ ] LOW disk space triggers RED alert (test if needed)

---

## 🆘 Need Help?

1. Check logs: `sudo tail -100 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log`
2. Review full guide: `docs/CLOUDWATCH_AGENT_SETUP_GUIDE.md`
3. Common issues: See troubleshooting section in full guide
4. Still stuck? File an issue with log excerpts
