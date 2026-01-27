# Operations Runbook

Complete operations guide for IT Infrastructure Monitoring System.

## Table of Contents

- [Health Monitoring](#health-monitoring)
- [Troubleshooting](#troubleshooting)
- [Maintenance](#maintenance)
- [Budget Management](#budget-management)
- [Incident Response](#incident-response)
- [Performance Tuning](#performance-tuning)

---

## Health Monitoring

### Check System Status

```bash
# Docker deployment
docker ps | grep monitoring-agent
docker logs monitoring-agent --tail 50

# Check container health
docker inspect monitoring-agent | grep -A 10 Health

# View real-time logs
docker logs -f monitoring-agent
```

### Monitor Budget Usage

```bash
# Check current budget state
docker exec monitoring-agent cat /tmp/budget_state.json

# Or on host
cat /tmp/budget_state.json
```

Example output:
```json
{
  "date": "2026-01-16",
  "spent": 1.25,
  "budget": 3.0
}
```

### Verify Telegram Delivery

```bash
# Run health check test
python tests/test_telegram.py

# Check for Telegram errors in logs
docker logs monitoring-agent 2>&1 | grep -i telegram

# Test single cycle with dry-run
docker exec monitoring-agent python -m src.main --run-once --dry-run
```

### Check Collector Status

```bash
# View collector execution logs
docker logs monitoring-agent 2>&1 | grep "collector"

# Count successful collections
docker logs monitoring-agent 2>&1 | grep "Collection complete"
```

---

## Troubleshooting

### No Telegram Messages Received

**Symptoms**: Monitoring runs but no Telegram notifications

**Diagnosis**:
```bash
# 1. Check Telegram configuration
docker exec monitoring-agent cat /app/config/config.yaml | grep telegram

# 2. Verify bot token
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"

# 3. Check recent errors
docker logs monitoring-agent 2>&1 | grep -i "telegram.*error"

# 4. Test Telegram client
docker exec monitoring-agent python tests/test_telegram.py
```

**Solutions**:
- Verify `TELEGRAM_BOT_TOKEN` in `.env`
- Verify `TELEGRAM_CHAT_ID` in `.env`
- Check bot permissions (must be admin in group chats)
- Ensure bot hasn't been blocked
- Test with: `curl https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>&text=test`

### High Token Usage / Budget Exceeded

**Symptoms**: Budget alerts, analysis skipped, high costs

**Diagnosis**:
```bash
# 1. Profile current costs
python scripts/profile_costs.py

# 2. Check token usage history
docker logs monitoring-agent 2>&1 | grep "token"

# 3. View budget state
cat /tmp/budget_state.json
```

**Solutions**:

1. **Increase Budget** (if justified):
   ```yaml
   # config/config.yaml
   llm:
     daily_budget_usd: 5.0  # Increase from 3.0
   ```

2. **Reduce Check Frequency**:
   ```yaml
   # config/config.yaml
   monitoring:
     schedule: "0 */12 * * *"  # Change from 6 hours to 12 hours
   ```

3. **Optimize Prompts**:
   - Review `src/agents/analysis_agent.py`
   - Reduce metrics included in prompts
   - Limit `max_tokens` in config

4. **Filter Targets**:
   - Remove non-critical monitoring targets
   - Focus on production systems only

### Collection Failures

**Symptoms**: "Collection failed", UNKNOWN status, partial results

**Diagnosis**:
```bash
# Check for collection errors
docker logs monitoring-agent 2>&1 | grep "Collection failed"

# Check specific collector
docker logs monitoring-agent 2>&1 | grep "EC2Collector"
docker logs monitoring-agent 2>&1 | grep "VPSCollector"
```

**Common Issues**:

#### AWS/EC2 Collector
```bash
# Test AWS credentials
docker exec monitoring-agent aws ec2 describe-instances --region us-east-1

# Check IAM permissions
aws iam get-role-policy --role-name MonitoringAgentRole --policy-name MonitoringPolicy
```

**Solutions**:
- Verify AWS credentials in `.env` or IAM role attached
- Check IAM policy includes required permissions (see `deployment/iam-policy.json`)
- Verify EC2 instance IDs are correct in config

#### VPS/Docker Collector (SSH)
```bash
# Test SSH connection
ssh -i secrets/your_key user@host

# Check key permissions
ls -la secrets/
# Should be 600 (rw-------)

# Fix permissions
chmod 600 secrets/*
```

**Solutions**:
- Verify SSH key path in config
- Ensure key has correct permissions (600)
- Test SSH manually first
- Check firewall rules on target servers

#### API Collector
```bash
# Test API endpoint manually
curl -I https://api.example.com/health

# Check timeout settings
docker logs monitoring-agent 2>&1 | grep "timeout"
```

**Solutions**:
- Verify API URLs are accessible
- Check timeout thresholds (may need increase)
- Verify SSL certificates are valid
- Check API authentication if required

#### Database Collector
```bash
# Test database connection
docker exec monitoring-agent psql -h host -U user -d database -c "SELECT version();"

# Check credentials
echo $POSTGRES_USER
echo $POSTGRES_PASSWORD
```

**Solutions**:
- Verify database credentials in `.env`
- Check database firewall/security groups
- Verify SSL mode setting
- Test connection manually

### Container Won't Start

**Diagnosis**:
```bash
# Check container status
docker ps -a | grep monitoring-agent

# View container logs
docker logs monitoring-agent

# Check Docker daemon
systemctl status docker

# Verify image exists
docker images | grep monitoring-agent
```

**Solutions**:
- Check configuration file exists: `config/config.yaml`
- Verify `.env` file exists
- Check volume mounts in `docker-compose.yml`
- Review startup logs for errors
- Validate YAML syntax: `python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"`

---

## Maintenance

### Updating Configuration

```bash
# 1. Edit configuration
nano config/config.yaml

# 2. Validate configuration
python -c "from src.config.loader import ConfigLoader; ConfigLoader.load_from_file('config/config.yaml')"

# 3. Restart container (Docker)
docker-compose restart

# 4. Verify
docker logs -f monitoring-agent
```

### Updating Code

```bash
# 1. Pull latest changes
git pull

# 2. Rebuild image
docker-compose build

# 3. Deploy
docker-compose up -d

# 4. Verify
docker-compose ps
docker logs -f monitoring-agent --tail 50
```

### Rotating Credentials

#### AWS Credentials
```bash
# 1. Generate new AWS access key in IAM console

# 2. Update .env
nano .env
# Update AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

# 3. Restart
docker-compose restart

# 4. Test
docker exec monitoring-agent python -m src.main --run-once --dry-run
```

#### Telegram Bot Token
```bash
# 1. Create new bot via @BotFather if needed

# 2. Update .env
nano .env
# Update TELEGRAM_BOT_TOKEN

# 3. Restart
docker-compose restart

# 4. Test
docker exec monitoring-agent python tests/test_telegram.py
```

#### SSH Keys
```bash
# 1. Copy new key
cp /path/to/new_key secrets/

# 2. Set permissions
chmod 600 secrets/new_key

# 3. Update config.yaml
nano config/config.yaml
# Update ssh_key_path for affected servers

# 4. Restart
docker-compose restart
```

### Log Management

```bash
# View logs
docker logs monitoring-agent

# Rotate logs (Docker handles this via logging driver)
# Configure in docker-compose.yml:
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"

# Export logs
docker logs monitoring-agent > /tmp/monitoring-$(date +%Y%m%d).log

# Search logs
docker logs monitoring-agent 2>&1 | grep "ERROR"
docker logs monitoring-agent 2>&1 | grep "issue"
```

---

## Budget Management

### Monitor Daily Budget

```bash
# Check current spending
cat /tmp/budget_state.json

# Profile costs
python scripts/profile_costs.py

# View budget alerts in logs
docker logs monitoring-agent 2>&1 | grep -i budget
```

### Budget Alerts

The system automatically:
- Tracks daily spending
- Blocks requests when budget exceeded
- Resets at midnight UTC
- Logs warnings at 80% utilization

### Cost Optimization

**1. Reduce Check Frequency**:
```yaml
# From 4 checks/day to 2 checks/day
schedule: "0 */12 * * *"
# Saves ~50% on LLM costs
```

**2. Limit Analysis Scope**:
```yaml
# Reduce max tokens
llm:
  max_tokens: 2048  # Down from 4096
# Saves ~$0.02-0.04 per cycle
```

**3. Filter Monitoring Targets**:
- Monitor only production systems
- Remove redundant API endpoints
- Combine similar checks

**4. Use Spot Instances** (EC2):
- ~70% savings on compute costs
- Acceptable for monitoring workload

---

## Incident Response

### System Down / Not Running

**Immediate Actions**:
```bash
# 1. Check if container is running
docker ps | grep monitoring-agent

# 2. Start if stopped
docker-compose up -d

# 3. Check logs
docker logs monitoring-agent --tail 100

# 4. Test manually
docker exec monitoring-agent python -m src.main --run-once --dry-run
```

### False Positives / Alert Fatigue

**Actions**:
```bash
# 1. Review thresholds
cat config/config.yaml | grep -A 10 thresholds

# 2. Adjust as needed
nano config/config.yaml

# 3. Restart
docker-compose restart
```

**Common Adjustments**:
```yaml
thresholds:
  # Increase if getting too many alerts
  cpu_yellow: 80  # Up from 70
  ram_yellow: 80  # Up from 70

  # Decrease for tighter monitoring
  disk_free_red: 5  # Down from 10
```

### Critical Infrastructure Issues Detected

**Response Workflow**:

1. **Acknowledge**: Review Telegram alert
2. **Verify**: Check if issue is real or false positive
3. **Investigate**: SSH to affected systems, check logs
4. **Remediate**: Follow AI recommendations or apply fix
5. **Monitor**: Watch for resolution
6. **Document**: Update runbook if new issue type

---

## Performance Tuning

### Optimize Collection Speed

```bash
# Collections run in parallel by default via asyncio.gather()
# To verify parallelism:
docker logs monitoring-agent 2>&1 | grep "parallel collection"
```

### Reduce Execution Time

**Current Design**:
- Collectors run in parallel (async)
- Typical cycle: 30-60 seconds for 70 targets

**If slow**:
1. Check network latency to targets
2. Increase timeouts for slow endpoints
3. Remove unresponsive targets
4. Check for SSH connection delays

### Memory Usage

```bash
# Check container memory
docker stats monitoring-agent --no-stream

# Typical usage: 200-500MB
```

**If high memory**:
- Review collector results caching
- Check for memory leaks in custom code
- Restart container daily via cron

---

## Useful Commands Reference

### Quick Health Check
```bash
docker ps && \
docker logs monitoring-agent --tail 10 && \
cat /tmp/budget_state.json
```

### Force Immediate Check
```bash
docker exec monitoring-agent python -m src.main --run-once
```

### View Configuration
```bash
docker exec monitoring-agent cat /app/config/config.yaml
```

### Test Components
```bash
# Test collectors
python -m pytest tests/test_collectors/ -v

# Test services
python -m pytest tests/test_services/ -v

# Test Telegram
python tests/test_telegram.py

# Profile costs
python scripts/profile_costs.py
```

### Emergency Stop
```bash
# Stop monitoring
docker-compose down

# Or just pause
docker-compose stop
```

### Full System Reset
```bash
# Stop and remove container
docker-compose down

# Clear budget state
rm -f /tmp/budget_state.json

# Restart fresh
docker-compose up -d
```

---

## Escalation

### When to Escalate

- Repeated collector failures (>24 hours)
- Budget consistently exceeded despite optimizations
- Critical infrastructure issues requiring immediate attention
- System completely unresponsive

### Support Contacts

- **Technical Issues**: [Your team's contact]
- **AWS Issues**: AWS Support
- **Infrastructure Alerts**: On-call engineer

---

## Monitoring the Monitor

### Healthcheck Cron

Add to crontab to ensure monitoring system is running:

```bash
# Check every 30 minutes
*/30 * * * * docker ps | grep -q monitoring-agent || docker-compose -f /path/to/docker-compose.yml up -d
```

### External Monitoring

Consider monitoring the monitoring system with:
- UptimeRobot / Pingdom (check if Telegram messages arrive)
- CloudWatch Alarms on EC2 instance
- Secondary monitoring system

---

## Appendix

### Log Levels

- `DEBUG`: Detailed diagnostic information
- `INFO`: General informational messages (default)
- `WARNING`: Warning messages (e.g., budget thresholds)
- `ERROR`: Error events that might still allow the app to continue

Change in `.env`:
```bash
LOG_LEVEL=DEBUG
```

### Exit Codes

- `0`: Success
- `1`: General error
- `2`: Budget exceeded (profile_costs.py)
- `130`: Interrupted by user

### File Locations

- Configuration: `/app/config/config.yaml`
- Budget State: `/tmp/budget_state.json`
- Secrets: `/app/secrets/`
- Logs: `docker logs monitoring-agent`

---

**Document Version**: 1.0
**Last Updated**: 2026-01-16
**Maintainer**: DevOps Team
