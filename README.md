# IT Infrastructure Monitoring System

AI-powered monitoring system for cloud infrastructure and services with intelligent analysis and Telegram notifications.

## Features

- **Multi-platform monitoring**: EC2, VPS, Docker containers, databases, APIs, S3 buckets, LLM models
- **AI-powered analysis**: Claude Haiku 3.5 for intelligent health assessment and recommendations
- **Scheduled checks**: Configurable cron-based monitoring (default: every 6 hours)
- **Telegram notifications**: Instant alerts with detailed status reports
- **Budget control**: Daily LLM cost limits to prevent overspending
- **Concurrent collection**: Async design for fast parallel data gathering
- **Graceful degradation**: Partial failures don't stop the entire workflow

## Architecture

Built with:
- **LangGraph**: Workflow orchestration
- **Amazon Bedrock**: Claude 3.5 Haiku for AI analysis
- **APScheduler**: Cron-based job scheduling
- **Telegram Bot API**: Report delivery
- **boto3**: AWS service integration (EC2, S3, Bedrock)
- **paramiko**: SSH connections for VPS/Docker
- **psycopg2**: PostgreSQL database checks
- **httpx**: Async HTTP client for API checks

## Monitored Resources

| Resource Type | Metrics Collected | Status Logic |
|---------------|-------------------|--------------|
| **EC2 Instances** | CPU utilization, instance state | CloudWatch metrics + thresholds (15-min lookback) |
| **VPS Servers** | CPU, RAM, disk usage | SSH commands (top, free, df) |
| **Docker Containers** | Container status, health checks | docker ps parsing, exit 0 = healthy |
| **API Endpoints** | Response time, HTTP status | Timeout and latency thresholds |
| **PostgreSQL DBs** | Connectivity, version, table stats | Connection success/failure |
| **LLM Models** | Model availability | Minimal test invocations |
| **S3 Buckets** | Accessibility, permissions | head_bucket + list operations |

## Installation

### Prerequisites

- Python 3.11+
- AWS account with appropriate permissions
- Telegram bot token and chat ID
- SSH keys for VPS/Docker servers (optional)
- PostgreSQL credentials (optional)

### Step 1: Clone Repository

```bash
git clone <repository-url>
cd monitoring_agents
```

### Step 2: Install Dependencies

```bash
pip install -r deployment/requirements.txt
```

Required packages include:
- `python-dotenv>=1.0.0` - Loads environment variables from `.env` file
- `boto3>=1.34.0` - AWS SDK for EC2, CloudWatch, S3, and Bedrock
- `paramiko>=3.4.0` - SSH connections for VPS/Docker monitoring
- `python-telegram-bot>=20.8` - Telegram notifications
- `httpx>=0.26.0` - Async HTTP client for API checks
- `psycopg2-binary>=2.9.9` - PostgreSQL database checks
- `langgraph>=0.1.0` - Workflow orchestration
- `apscheduler>=3.10.0` - Cron-based scheduling

Optional packages for visualization:
- `pygraphviz` or `grandalf` - For workflow graph visualization
- `langsmith` - For real-time workflow tracing (separate signup required)

### Step 3: Configure Environment Variables

Create `.env` file from template:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

# Telegram Configuration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUVwxyz
TELEGRAM_CHAT_ID=123456789

# SSH Keys (if using VPS/Docker monitoring)
VPS_SSH_KEY_PATH=./secrets/

# Database Credentials (if using database monitoring)
POSTGRES_USER=monitoring_user
POSTGRES_PASSWORD=your_postgres_password_here

# Azure OpenAI (if using Azure LLM monitoring)
AZURE_OPENAI_KEY=your_azure_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com

# Logging
LOG_LEVEL=INFO
```

**Important**: The system uses `python-dotenv` to automatically load environment variables from the `.env` file. This is required for AWS credentials to be used by boto3 clients.

### Step 4: Configure Monitoring Targets

Create `config/config.yaml` from template:

```bash
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml` with your infrastructure:

```yaml
monitoring:
  schedule: "0 */6 * * *"  # Every 6 hours

targets:
  ec2_instances:
    - instance_id: "i-1234567890abcdef0"
      name: "prod-api-server-1"
      region: "us-east-1"

  vps_servers:
    - host: "192.168.1.100"
      name: "kz-vps-01"
      ssh_key_path: "/app/secrets/kz_vps_key"
      port: 22
      username: "ubuntu"

  api_endpoints:
    - url: "https://api.example.com/health"
      name: "Main API Health"
      timeout_ms: 5000

  databases:
    - host: "prod-db.example.com"
      port: 5432
      database: "main_db"
      ssl_mode: "require"

  llm_models:
    - provider: "bedrock"
      model_id: "us.anthropic.claude-3-5-haiku-20241022-v1:0"

  s3_buckets:
    - bucket: "my-production-bucket"
      region: "us-east-1"

thresholds:
  cpu_red: 90
  cpu_yellow: 70
  ram_red: 90
  ram_yellow: 70
  disk_free_red: 10
  disk_free_yellow: 20
  api_timeout_ms: 5000
  api_slow_ms: 2000

telegram:
  bot_token: "${TELEGRAM_BOT_TOKEN}"
  chat_id: "${TELEGRAM_CHAT_ID}"

llm:
  provider: "bedrock"
  model: "us.anthropic.claude-3-5-haiku-20241022-v1:0"
  region: "us-east-1"
  max_tokens: 4096
  daily_budget_usd: 3.0
```

### Step 5: Setup SSH Keys (Optional)

If monitoring VPS servers or Docker containers:

```bash
mkdir -p secrets
chmod 700 secrets

# Copy your SSH private key
cp /path/to/your/key secrets/kz_vps_key
chmod 600 secrets/kz_vps_key
```

### Step 6: Run Monitoring System

```bash
python -m src.main
```

The system will:
1. Start the scheduler
2. Run first check immediately
3. Continue on cron schedule
4. Send reports via Telegram

## Docker Deployment

### Build Image

```bash
docker build -t monitoring-agents -f deployment/Dockerfile .
```

### Run Container

```bash
docker run -d \
  --name monitoring-agents \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/secrets:/app/secrets \
  --env-file .env \
  monitoring-agents
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  monitoring-agents:
    build:
      context: .
      dockerfile: deployment/Dockerfile
    container_name: monitoring-agents
    volumes:
      - ./config:/app/config:ro
      - ./secrets:/app/secrets:ro
    env_file:
      - .env
    restart: unless-stopped
```

Run with:

```bash
docker-compose up -d
```

## AWS IAM Permissions

Required AWS permissions for the monitoring user/role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics",
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "s3:GetBucketVersioning",
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    }
  ]
}
```

**Note**:
- `cloudwatch:GetMetricStatistics` is required to retrieve CPU metrics from EC2 instances
- `cloudwatch:ListMetrics` is required to list available metrics
- The EC2 collector looks back 15 minutes for CloudWatch metrics to account for basic monitoring delays

## Telegram Bot Setup

1. **Create bot**: Message [@BotFather](https://t.me/BotFather) on Telegram
   - Send `/newbot`
   - Choose name and username
   - Save the bot token

2. **Get chat ID**:
   - Start conversation with your bot
   - Send any message
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find `"chat":{"id":123456789}` in response

3. **Add to .env**:
   ```bash
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_CHAT_ID=123456789
   ```

## Configuration Reference

### Monitoring Schedule

Cron format: `minute hour day month weekday`

Examples:
- `"0 */6 * * *"` - Every 6 hours
- `"0 */1 * * *"` - Every hour
- `"*/30 * * * *"` - Every 30 minutes
- `"0 0 * * *"` - Daily at midnight
- `"0 9,17 * * 1-5"` - 9 AM and 5 PM on weekdays

### Health Status Logic

| Status | Color | Description |
|--------|-------|-------------|
| 🟢 GREEN | Green | All metrics within normal range |
| 🟡 YELLOW | Yellow | Warning threshold exceeded |
| 🔴 RED | Red | Critical threshold exceeded or failure |
| ⚪ UNKNOWN | White | Unable to collect metrics |

**Docker Container Status**:
- Exit code 0 (clean exit) = 🟢 GREEN - suitable for cron jobs and scheduled tasks
- Exit code != 0 = 🔴 RED - container crashed or failed
- Restarting = 🟡 YELLOW
- Running = 🟢 GREEN
- Unhealthy = 🔴 RED

### Threshold Configuration

**CPU and RAM** (higher is worse):
- `cpu_red: 90` - RED when CPU > 90%
- `cpu_yellow: 70` - YELLOW when CPU > 70%
- `ram_red: 90` - RED when RAM > 90%
- `ram_yellow: 70` - YELLOW when RAM > 70%

**Disk space** (lower is worse):
- `disk_free_red: 10` - RED when < 10% free
- `disk_free_yellow: 20` - YELLOW when < 20% free

**API response time**:
- `api_timeout_ms: 5000` - RED when timeout (5 seconds)
- `api_slow_ms: 2000` - YELLOW when > 2 seconds

### Budget Control

Daily LLM cost limit:
```yaml
llm:
  daily_budget_usd: 3.0  # Maximum $3/day
```

Cost calculation:
- Input tokens: $0.003 per 1K tokens
- Output tokens: $0.015 per 1K tokens

Estimated costs per check (70 targets):
- ~$0.10-0.15 per full monitoring cycle
- 4 checks/day = ~$0.40-0.60/day
- Well within $3/day budget

## Troubleshooting

### Common Issues

**1. "paramiko library not installed"**
```bash
pip install paramiko>=3.4.0
```

**2. "boto3 library not installed"**
```bash
pip install boto3>=1.34.0
```

**3. SSH connection failures**
- Verify SSH key permissions: `chmod 600 secrets/your_key`
- Test SSH manually: `ssh -i secrets/your_key ubuntu@host`
- Check firewall rules on target servers

**4. "No CPU metrics available" for EC2 instances**
- Verify IAM user has `cloudwatch:GetMetricStatistics` and `cloudwatch:ListMetrics` permissions
- Ensure `.env` file has correct `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
- Check that environment variables are loaded (requires `python-dotenv`)
- Verify boto3 is using the correct AWS credentials:
  ```python
  import boto3
  sts = boto3.client('sts')
  print(sts.get_caller_identity())  # Should show your monitoring user
  ```
- EC2 instances need to be running for 5-15 minutes for CloudWatch metrics to be available

**5. AWS permissions denied**
- Verify IAM permissions (see AWS IAM Permissions section)
- Check AWS credentials in `.env`
- Test with AWS CLI: `aws ec2 describe-instances`

**6. Telegram "Can't parse entities" error**
- System automatically retries with plain text formatting if Markdown parsing fails
- This is handled gracefully - messages will be delivered without formatting
- Check logs for "Telegram message sent successfully (plain text)"

**7. Telegram not receiving messages**
- Verify bot token and chat ID
- Start conversation with bot first
- Check bot wasn't blocked

**8. Database connection failures**
- Verify PostgreSQL credentials in `.env`
- Check database firewall/security groups
- Test connection: `psql -h host -U user -d database`

### Logging

Logs are output to stdout in JSON format:

```bash
# View logs (Docker)
docker logs monitoring-agents

# Follow logs
docker logs -f monitoring-agents

# Filter for errors
docker logs monitoring-agents 2>&1 | grep ERROR
```

Set log level in `.env`:
```bash
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

### Testing Individual Collectors

```python
# Test API collector
python -c "
from src.collectors.api_collector import APICollector
from src.config.loader import ConfigLoader
import asyncio
import logging

config = ConfigLoader.load_from_file('config/config.yaml')
logger = logging.getLogger('test')
collector = APICollector(
    config.targets.api_endpoints,
    config.thresholds.__dict__,
    logger
)
results = asyncio.run(collector.collect())
for r in results:
    print(f'{r.target_name}: {r.status.value} - {r.message}')
"
```

## Workflow Visualization

### Generate Graph Diagram

Visualize the LangGraph workflow structure:

```bash
# Install visualization dependencies
pip install pygraphviz
# or
pip install grandalf

# Generate graph
python scripts/visualize_workflow.py workflow_graph.png
```

This creates a visual diagram showing the workflow:
- **aggregate**: Parallel data collection from all collectors
- **analyze**: AI-powered root cause analysis
- **generate_report**: Format results for Telegram
- **send_telegram**: Deliver report to Telegram

### LangSmith Integration

Enable real-time workflow monitoring with LangSmith (optional):

**1. Sign up for LangSmith**
- Visit https://smith.langchain.com
- Create free account
- Get your API key

**2. Configure environment**

Add to `.env`:
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__your_api_key_here
LANGCHAIN_PROJECT=monitoring-agents
```

**3. Run monitoring**
```bash
python -m src.main --run-once
```

**4. View traces**
- Open https://smith.langchain.com
- Navigate to your project: `monitoring-agents`
- View execution traces with:
  - Node-by-node execution timing
  - Token usage per LLM call
  - Input/output for each step
  - Error details if failures occur
  - Historical run comparison

**Benefits**:
- Debug workflow issues visually
- Optimize performance bottlenecks
- Track LLM costs over time
- Share traces with team

## Development

### Project Structure

```
monitoring_agents/
├── src/
│   ├── agents/          # AI agents (analysis, reporting)
│   ├── collectors/      # Data collectors for each resource type
│   ├── config/          # Configuration models and loader
│   ├── llm/            # LLM client and budget tracker
│   ├── notification/   # Telegram client
│   ├── utils/          # Shared utilities (logging, status, metrics)
│   ├── workflow.py     # LangGraph workflow definition
│   └── main.py         # Application entry point
├── config/
│   ├── config.yaml           # Main configuration (user-created)
│   └── config.example.yaml   # Configuration template
├── deployment/
│   ├── Dockerfile            # Container definition
│   └── requirements.txt      # Python dependencies
├── tests/              # Unit and integration tests
├── .env                # Environment variables (user-created)
├── .env.example        # Environment template
└── README.md          # This file
```

### Running Tests

```bash
# Install dev dependencies
pip install pytest pytest-asyncio moto

# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/test_api_collector.py
```

### Adding New Collectors

1. Create `src/collectors/new_collector.py`:
```python
from .base import BaseCollector, safe_collect

class NewCollector(BaseCollector):
    @safe_collect
    async def collect(self) -> List[CollectorResult]:
        # Implementation
        pass
```

2. Add configuration model in `src/config/models.py`
3. Update `config.example.yaml` with example
4. Update workflow in `src/workflow.py` to include new collector
5. Add tests in `tests/test_new_collector.py`

## Cost Optimization

**Tips to reduce costs**:

1. **Adjust schedule**: Change from 6-hour to 12-hour checks
   ```yaml
   schedule: "0 */12 * * *"  # Every 12 hours
   ```

2. **Reduce max_tokens**: Lower token limit for AI analysis
   ```yaml
   llm:
     max_tokens: 2048  # Reduced from 4096
   ```

3. **Filter targets**: Only monitor critical resources
   - Remove non-essential API endpoints
   - Monitor only production servers

4. **Use shorter lookback**: EC2 metrics from 5 minutes vs 15 minutes
   - Already optimized in implementation

5. **Disable AI analysis**: Comment out analysis agent for simple alerts
   - Requires code modification in workflow.py

## Security Best Practices

1. **Never commit secrets**:
   - Keep `.env` and `config/config.yaml` out of git
   - Use `.gitignore` (already configured)

2. **Restrict SSH keys**:
   - Use dedicated monitoring keys with read-only access
   - Set proper permissions: `chmod 600`

3. **Use IAM roles** (AWS):
   - Prefer IAM roles over access keys when running on EC2
   - Apply principle of least privilege

4. **Secure Telegram bot**:
   - Don't share bot token
   - Verify chat ID to prevent unauthorized access

5. **Database credentials**:
   - Use read-only database user
   - Rotate passwords regularly

6. **SSL/TLS**:
   - Use `ssl_mode: "require"` for PostgreSQL
   - Verify API endpoints use HTTPS

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- GitHub Issues: [repository-url]/issues
- Documentation: [repository-url]/wiki

## Recent Updates

### v1.2.0 (2026-01-22)
- ✅ Added workflow graph visualization with `scripts/visualize_workflow.py`
- ✅ Integrated LangSmith tracing for real-time workflow monitoring and debugging
- ✅ Added `visualize_graph()` method to MonitoringWorkflow class

### v1.1.0 (2026-01-22)
- ✅ Added `python-dotenv` support for automatic `.env` file loading
- ✅ Fixed CloudWatch permissions - added `cloudwatch:ListMetrics` to IAM requirements
- ✅ Increased EC2 metrics lookback from 5 to 15 minutes to handle CloudWatch delays
- ✅ Changed Docker exit 0 status from YELLOW to GREEN (supports cron jobs)
- ✅ Added Telegram markdown fallback - auto-retries as plain text on parsing errors

## Roadmap

Future enhancements:
- [ ] Web dashboard for historical metrics
- [ ] Prometheus metrics export
- [ ] Kubernetes pod monitoring
- [ ] MySQL/MongoDB support
- [ ] Slack/Discord notifications
- [ ] Multi-region support
- [ ] Alert aggregation and deduplication
- [ ] Custom alerting rules DSL
