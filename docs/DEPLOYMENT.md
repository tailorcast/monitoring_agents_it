# Deployment Guide

Complete deployment guide for IT Infrastructure Monitoring System.

## Quick Start

### 1. Local Development Setup

```bash
# Clone repository
git clone <repository-url>
cd monitoring_agents

# Install dependencies
pip install -r deployment/requirements.txt

# Setup configuration
cp .env.example .env
cp config/config.example.yaml config/config.yaml

# Edit configuration files with your credentials
nano .env
nano config/config.yaml

# Run once to test
python -m src.main --run-once --dry-run
```

### 2. Docker Deployment (Recommended)

```bash
# Build image
docker build -t monitoring-agent -f deployment/Dockerfile .

# Run with docker-compose
docker-compose -f deployment/docker-compose.yml up -d

# View logs
docker logs -f monitoring-agent

# Stop
docker-compose -f deployment/docker-compose.yml down
```

### 3. EC2 Deployment

See detailed EC2 deployment instructions below.

---

## Detailed Deployment Options

### Option 1: Direct Python Execution

Best for: Development, testing, local execution

**Requirements**:
- Python 3.11+
- pip

**Steps**:

1. Install dependencies:
   ```bash
   pip install -r deployment/requirements.txt
   ```

2. Configure:
   ```bash
   cp .env.example .env
   cp config/config.example.yaml config/config.yaml
   # Edit both files with your settings
   ```

3. Run:
   ```bash
   # Test run (once, no Telegram)
   python -m src.main --run-once --dry-run

   # Single execution with Telegram
   python -m src.main --run-once

   # Start scheduler (runs continuously)
   python -m src.main
   ```

**Pros**: Simple, easy debugging
**Cons**: Requires manual process management, no isolation

---

### Option 2: Docker Container

Best for: Production, isolation, easy updates

**Requirements**:
- Docker 20.10+
- Docker Compose 2.0+

**Steps**:

1. Build image:
   ```bash
   docker build -t monitoring-agent:latest -f deployment/Dockerfile .
   ```

2. Create configuration:
   ```bash
   # Config and secrets should be outside container
   mkdir -p config secrets
   cp .env.example .env
   cp config/config.example.yaml config/config.yaml

   # Edit configuration
   nano .env
   nano config/config.yaml

   # Copy SSH keys to secrets/
   cp ~/.ssh/your_vps_key secrets/
   chmod 600 secrets/*
   ```

3. Run with docker-compose:
   ```bash
   cd deployment
   docker-compose up -d
   ```

4. Manage:
   ```bash
   # View logs
   docker logs -f monitoring-agent

   # Restart
   docker-compose restart

   # Stop
   docker-compose down

   # Update and restart
   docker-compose build
   docker-compose up -d
   ```

**Pros**: Isolated, reproducible, easy to update
**Cons**: Requires Docker knowledge

---

### Option 3: AWS EC2 Deployment

Best for: Production, integration with AWS services, IAM roles

**Requirements**:
- AWS account
- EC2 instance (t3.small recommended)
- IAM role with required permissions

**Setup Steps**:

#### 3.1 Launch EC2 Instance

1. Launch EC2 instance:
   - AMI: Amazon Linux 2023 or Ubuntu 22.04
   - Instance type: t3.small (2 vCPU, 2GB RAM)
   - Storage: 20GB gp3
   - Security group: Outbound HTTPS (443) allowed

2. Attach IAM role with policy:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "ec2:DescribeInstances",
           "cloudwatch:GetMetricStatistics",
           "s3:HeadBucket",
           "s3:ListBucket",
           "s3:GetBucketLocation",
           "bedrock:InvokeModel"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

#### 3.2 Install Docker on EC2

```bash
# SSH to EC2
ssh -i your-key.pem ec2-user@<ec2-public-ip>

# Install Docker (Amazon Linux 2023)
sudo yum update -y
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Log out and back in for group changes
exit
```

#### 3.3 Deploy Application

```bash
# SSH back in
ssh -i your-key.pem ec2-user@<ec2-public-ip>

# Create application directory
mkdir -p ~/monitoring_agents
cd ~/monitoring_agents

# Option A: Clone repository (if using Git)
git clone <repository-url> .

# Option B: Copy files from local machine
# (On your local machine)
scp -i your-key.pem -r . ec2-user@<ec2-public-ip>:~/monitoring_agents/

# Setup configuration
cd ~/monitoring_agents
cp .env.example .env
cp config/config.example.yaml config/config.yaml

# Edit configuration
nano .env
nano config/config.yaml

# Copy SSH keys if needed
mkdir -p secrets
# Copy your SSH keys to secrets/

# Build and start
cd deployment
docker-compose up -d

# Check logs
docker logs -f monitoring-agent
```

#### 3.4 Setup Automatic Restart

Create systemd service for auto-restart on reboot:

```bash
sudo nano /etc/systemd/system/monitoring-agent.service
```

Content:
```ini
[Unit]
Description=Monitoring Agent Docker Container
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ec2-user/monitoring_agents/deployment
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
User=ec2-user

[Install]
WantedBy=multi-user.target
```

Enable service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable monitoring-agent.service
sudo systemctl start monitoring-agent.service
```

**Pros**: Production-ready, AWS integration, IAM roles
**Cons**: AWS costs, more setup

---

## Configuration

### Environment Variables (.env)

Required variables:

```bash
# AWS (required for EC2, S3, Bedrock collectors)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your-key>      # Or use IAM role on EC2
AWS_SECRET_ACCESS_KEY=<your-secret>

# Telegram (required for notifications)
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>

# Optional: SSH keys
VPS_SSH_KEY_PATH=/app/secrets/your_key

# Database (required if monitoring PostgreSQL databases)
POSTGRES_USER=monitoring_user
POSTGRES_PASSWORD=<your-password>

# Optional: Azure
AZURE_OPENAI_KEY=<your-key>
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com

# Optional: Logging
LOG_LEVEL=INFO
```

### Monitoring Targets (config.yaml)

Edit `config/config.yaml` to specify what to monitor:

```yaml
monitoring:
  schedule: "0 */6 * * *"  # Every 6 hours

targets:
  ec2_instances:
    - instance_id: "i-xxx"
      name: "prod-server"
      region: "us-east-1"

  vps_servers:
    - host: "192.168.1.100"
      name: "vps-01"
      ssh_key_path: "/app/secrets/key"
      port: 22
      username: "ubuntu"

  api_endpoints:
    - url: "https://api.example.com/health"
      name: "API Health"
      timeout_ms: 5000

  databases:
    - host: "your-db-host.rds.amazonaws.com"
      port: 5432
      database: "your_database"
      table: "your_table"  # Optional: query specific table
      ssl_mode: "require"
      sslrootcert: "deployment/rds-ca-2019-root.pem"  # AWS RDS CA certificate

  # ... other targets
```

**Note**: For PostgreSQL databases with SSL:
- The RDS CA certificate is automatically downloaded during Docker build
- Create a dedicated monitoring user with read-only permissions:
  ```sql
  CREATE USER monitoring_user WITH PASSWORD 'your_password';
  GRANT CONNECT ON DATABASE your_database TO monitoring_user;
  GRANT USAGE ON SCHEMA public TO monitoring_user;
  GRANT SELECT ON table_name TO monitoring_user;  -- Optional
  ```
- Set `POSTGRES_USER` and `POSTGRES_PASSWORD` in `.env`

---

## Verification

### Test Configuration

```bash
# Dry run (no Telegram)
python -m src.main --run-once --dry-run

# Or with Docker
docker run --rm -v $(pwd)/config:/app/config:ro \
  --env-file .env \
  monitoring-agent:latest \
  --run-once --dry-run
```

### Test Telegram

```bash
# Single run with Telegram
python -m src.main --run-once
```

### Check Logs

```bash
# Docker
docker logs monitoring-agent

# Follow logs
docker logs -f monitoring-agent

# Filter errors
docker logs monitoring-agent 2>&1 | grep ERROR
```

---

## Troubleshooting

### Issue: "Configuration file not found"

**Solution**:
- Ensure `config/config.yaml` exists
- Check volume mount in docker-compose.yml
- Verify file permissions

### Issue: "boto3 library not installed"

**Solution**:
```bash
pip install boto3>=1.34.0
```

### Issue: "Telegram authentication failed"

**Solution**:
- Verify TELEGRAM_BOT_TOKEN in .env
- Verify TELEGRAM_CHAT_ID in .env
- Test bot with: `curl https://api.telegram.org/bot<TOKEN>/getMe`

### Issue: SSH connection failures

**Solution**:
- Check SSH key permissions: `chmod 600 secrets/your_key`
- Test manually: `ssh -i secrets/your_key user@host`
- Verify ssh_key_path in config.yaml

### Issue: AWS permissions denied

**Solution**:
- Verify IAM permissions
- If using EC2, attach IAM role
- If using access keys, verify AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

---

## Monitoring the Monitor

### Health Checks

```bash
# Check if container is running
docker ps | grep monitoring-agent

# Check container health
docker inspect monitoring-agent | grep -A 10 Health

# View recent logs
docker logs --tail 100 monitoring-agent
```

### Budget Tracking

Budget state is persisted in `/tmp/budget_state.json`:

```bash
# View current budget usage
docker exec monitoring-agent cat /tmp/budget_state.json
```

### Metrics

Key metrics in logs:
- `Duration`: Cycle execution time
- `Checks`: Number of checks performed
- `Tokens`: LLM tokens used
- `Telegram sent`: Delivery status

---

## Updates and Maintenance

### Update Application

```bash
# Pull latest code
git pull

# Rebuild and restart
cd deployment
docker-compose build
docker-compose up -d

# Verify
docker logs -f monitoring-agent
```

### Update Configuration

```bash
# Edit config
nano config/config.yaml

# Restart to apply changes
docker-compose restart
```

### Backup Configuration

```bash
# Backup config and secrets
tar -czf monitoring-backup-$(date +%Y%m%d).tar.gz \
  config/config.yaml \
  .env \
  secrets/

# Restore
tar -xzf monitoring-backup-20240101.tar.gz
```

---

## Security Best Practices

1. **Never commit secrets**:
   - `.env` and `config.yaml` are in .gitignore
   - Use environment variables for sensitive data

2. **SSH key permissions**:
   ```bash
   chmod 600 secrets/*
   ```

3. **Use IAM roles on EC2**:
   - Prefer IAM roles over access keys
   - Apply least privilege principle

4. **Rotate credentials regularly**:
   - Database passwords
   - API keys
   - SSH keys

5. **Secure Telegram bot**:
   - Don't share bot token
   - Verify chat ID to prevent unauthorized access

6. **Network security**:
   - Use security groups on EC2
   - Restrict SSH access to monitoring system

---

## Cost Estimation

### AWS Costs

**EC2** (t3.small):
- On-demand: ~$15/month
- Reserved (1 year): ~$10/month

**Bedrock LLM** (Claude Haiku):
- 4 checks/day × $0.12/check = ~$15/month
- Well within $3/day budget

**CloudWatch/S3 API calls**:
- Negligible (<$1/month)

**Total**: ~$25-30/month

### Optimization Tips

1. Use spot instances for EC2 (~70% savings)
2. Reduce check frequency (12 hours instead of 6)
3. Use reserved instances for long-term
4. Monitor only critical resources

---

## Support

For issues:
- Check logs first: `docker logs monitoring-agent`
- Review troubleshooting section
- Check GitHub issues
- Review README.md and this guide

---

## Next Steps

After deployment:
1. Monitor first few cycles in logs
2. Verify Telegram messages received
3. Review budget usage
4. Tune thresholds as needed
5. Add more monitoring targets gradually
