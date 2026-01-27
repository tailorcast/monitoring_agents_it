# Technical Requirements Document
## IT Infrastructure Monitoring AI Agents

### 1. PROJECT OVERVIEW

**Purpose**: Automated IT infrastructure monitoring system using AI agents with LangGraph orchestration, delivering health summaries and root cause analysis via Telegram.

**Goals**:
1. Simplify infrastructure monitoring with intelligent analysis
2. Learn and implement LangGraph-based AI agent orchestration
3. Provide actionable insights through natural language reports

---

### 2. SYSTEM ARCHITECTURE

#### 2.1 Deployment
- **Platform**: AWS EC2 instance
- **Container**: Docker containerized application
- **Execution**: Scheduled task runner (cron or similar)
- **Configuration**: YAML/JSON config file for monitoring intervals

#### 2.2 Monitoring Schedule
- **Configurable Intervals**: Hourly to Daily (user-defined in config)
- **Report Delivery**: Scheduled reports only (no immediate alerts)
- **Data Persistence**: None - stateless current status reporting only

#### 2.3 AI Agent Framework
- **Orchestration**: LangGraph for agent workflow management
- **LLM Provider**: Anthropic Claude Haiku 4.5 via Amazon Bedrock
- **Agent Communication**: Independent agents (no inter-agent communication)
- **Agent Responsibilities**:
  - Root cause analysis when issues detected
  - Actionable recommendations for remediation
  - Health status summarization

#### 2.4 Budget Constraints
- **Daily LLM Cost Limit**: $3 USD/day maximum
- **Cost Management**: Token usage tracking and budget enforcement
- **Optimization**: Efficient prompting, no caching/deduplication at this stage

---

### 3. MONITORING TARGETS

#### 3.1 EC2 Instances (7 instances)
**Metrics**:
- CPU utilization (%)
- RAM usage (%)
- Available HDD space (GB/%)

**Access Method**: AWS IAM roles
**Thresholds** (default, user-tunable):
- 🔴 Red: CPU >90%, RAM >90%, HDD <10% free
- 🟡 Yellow: CPU >70%, RAM >70%, HDD <20% free
- 🟢 Green: Below yellow thresholds

#### 3.2 Virtual Servers (1 instance - Kazakhstan VPS)
**Metrics**: Same as EC2 (CPU, RAM, HDD)
**Access Method**: SSH key authentication
**Thresholds**: Same as EC2

#### 3.3 Docker Containers (~70 total, ~10 per server)
**Discovery**: Auto-discover via `docker ps -a` command
**Metrics**:
- Container status (running/stopped/exited)
- Recently stopped containers (detection window TBD)
- Health check status (if available in container config)

**Thresholds**:
- 🔴 Red: Container unexpectedly stopped, failed health check
- 🟡 Yellow: Container restarted recently
- 🟢 Green: Running with healthy status

#### 3.4 API Endpoints (50 endpoints)
**Check Method**: HTTP GET to `/health` or `/ping` endpoints
**Authentication**: None required
**Metrics**:
- Response status code (200 = healthy)
- Response time (ms)

**Thresholds**:
- 🔴 Red: Non-200 status code, timeout (>5s)
- 🟡 Yellow: Response time >2s
- 🟢 Green: 200 OK, response <2s

#### 3.5 PostgreSQL Database
**Metrics**:
- Connection availability (can connect: yes/no)
- Basic statistics from monitored table (table name TBD)

**Thresholds**:
- 🔴 Red: Connection failed
- 🟢 Green: Connection successful

#### 3.6 LLM Models Availability
**Providers**:
- Azure AI cloud
- Amazon Bedrock

**Check Method**: Simple inference request or health endpoint
**Metrics**: Availability (accessible: yes/no)

**Thresholds**:
- 🔴 Red: Model unavailable/unreachable
- 🟢 Green: Model accessible

#### 3.7 S3 Bucket Statistics
**Bucket**: `s3://product-gen-media-tailorcast` (us-east-1)
**Content Type**: Generated images and videos

**Metrics**:
- Files created today vs. yesterday (count & %)
- Files created this week vs. last week (count & %)
- Files created this month vs. last month (count & %)
- Total disk space usage (GB)

**Thresholds**:
- 🔴 Red: >50% decrease in file creation rate
- 🟡 Yellow: >25% decrease in file creation rate
- 🟢 Green: Stable or growing file creation rate

---

### 4. AI AGENT DESIGN

#### 4.1 Agent Types (LangGraph Nodes)
1. **Data Collection Agents** (parallel execution):
   - EC2 Metrics Collector
   - VPS Metrics Collector
   - Docker Status Collector
   - API Health Checker
   - Database Health Checker
   - LLM Availability Checker
   - S3 Statistics Collector

2. **Analysis Agent**:
   - Aggregates data from collectors
   - Identifies issues (red/yellow status)
   - Performs root cause analysis
   - Generates actionable recommendations

3. **Report Generation Agent**:
   - Formats health summary with status indicators
   - Includes drill-down details for issues
   - Structures message for Telegram delivery

#### 4.2 LangGraph Workflow
```
Start → [Parallel Data Collection] → Analysis Agent → Report Generator → Telegram Delivery → End
```

#### 4.3 Root Cause Analysis Requirements
When issues detected, AI should:
- Correlate metrics (e.g., high CPU + stopped container)
- Identify likely root causes based on patterns
- Suggest specific remediation steps
- Prioritize actions by severity

---

### 5. REPORTING & NOTIFICATIONS

#### 5.1 Telegram Integration
**Delivery Method**: Telegram Bot API
**Report Format**:
- Executive summary with overall health status
- Section-by-section breakdown:
  - 🟢/🟡/🔴 Status indicator
  - Key metrics
  - Issues (if any)
- Drill-down details for failures:
  - Root cause analysis
  - Recommended actions
  - Affected resources

**Example Report Structure**:
```
🟢 Infrastructure Health Report - [Timestamp]

📊 Overall Status: Healthy (47/50 checks passed)

━━━━━━━━━━━━━━━━━━━━━━━━
🟢 EC2 Instances: 7/7 healthy
   CPU: 45-65%, RAM: 50-70%, HDD: 40-60% free

🔴 Docker Containers: 3 issues detected
   ⚠️ prod-api-1 (stopped unexpectedly)
   Root Cause: OOM killed due to memory leak
   Recommendation: Restart container with increased memory limit (4GB→8GB), investigate memory leak in app logs

🟢 API Endpoints: 48/50 responding
...
```

---

### 6. CONFIGURATION MANAGEMENT

#### 6.1 Configuration File Structure (YAML)
```yaml
monitoring:
  schedule: "0 */6 * * *"  # Every 6 hours (cron syntax)

targets:
  ec2_instances:
    - instance_id: "i-xxxxx"
      name: "prod-api-server"
    # ... 6 more instances

  vps_servers:
    - host: "192.168.1.100"
      name: "kz-vps-01"
      ssh_key_path: "/secrets/kz_vps_key"

  api_endpoints:
    - url: "https://api.example.com/health"
      name: "Main API"
    # ... 49 more endpoints

  databases:
    - host: "prod-db.example.com"
      port: 5432
      database: "main_db"
      table: "health_metrics"

  llm_models:
    - provider: "azure"
      endpoint: "https://xxxx.openai.azure.com"
    - provider: "bedrock"
      model_id: "anthropic.claude-v2"

  s3_buckets:
    - bucket: "product-gen-media-tailorcast"
      region: "us-east-1"

thresholds:
  cpu_red: 90
  cpu_yellow: 70
  ram_red: 90
  ram_yellow: 70
  disk_free_red: 10
  disk_free_yellow: 20
  api_timeout: 5000  # ms
  api_slow: 2000     # ms

telegram:
  bot_token: "${TELEGRAM_BOT_TOKEN}"
  chat_id: "${TELEGRAM_CHAT_ID}"

llm:
  provider: "bedrock"
  model: "anthropic.claude-haiku-4-5"
  region: "us-east-1"
  max_tokens: 4096
  daily_budget_usd: 3.0
```

#### 6.2 Environment Variables
```bash
# AWS Credentials (for IAM role access)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx

# Telegram
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx

# VPS SSH
VPS_SSH_KEY_PATH=/app/secrets/kz_vps_key

# PostgreSQL
POSTGRES_USER=monitoring_user
POSTGRES_PASSWORD=xxx

# LLM Azure (if needed)
AZURE_OPENAI_KEY=xxx
AZURE_OPENAI_ENDPOINT=xxx
```

---

### 7. TECHNICAL STACK

#### 7.1 Core Technologies
- **Language**: Python 3.11+
- **Agent Framework**: LangGraph
- **LLM SDK**: boto3 (Amazon Bedrock)
- **Container**: Docker + docker-compose

#### 7.2 Python Libraries
```
langgraph>=0.1.0
langchain>=0.1.0
boto3>=1.34.0           # AWS SDK (Bedrock, S3, EC2)
paramiko>=3.4.0         # SSH for VPS access
psycopg2-binary>=2.9.0  # PostgreSQL
httpx>=0.26.0           # Async HTTP for API checks
python-telegram-bot>=20.0
pyyaml>=6.0
pydantic>=2.5.0         # Configuration validation
schedule>=1.2.0         # Task scheduling
```

#### 7.3 AWS Services
- **Amazon Bedrock**: Claude Haiku 4.5 inference
- **EC2**: Monitoring target + application host
- **S3**: Statistics monitoring
- **IAM**: Role-based access for EC2 metrics

---

### 8. DEVELOPMENT PHASES

#### Phase 1: Core Infrastructure (Week 1)
- [ ] Project setup (Docker, dependencies)
- [ ] Configuration file parser with validation
- [ ] Environment variable management
- [ ] Basic LangGraph workflow skeleton

#### Phase 2: Data Collectors (Week 2)
- [ ] EC2 metrics collector (boto3 CloudWatch)
- [ ] VPS metrics collector (SSH + system commands)
- [ ] Docker container discovery and status
- [ ] API endpoint health checker
- [ ] PostgreSQL availability checker
- [ ] LLM availability checker
- [ ] S3 statistics collector

#### Phase 3: AI Agents (Week 3)
- [ ] Bedrock integration (Claude Haiku 4.5)
- [ ] Analysis agent with root cause analysis
- [ ] Report generation agent
- [ ] Token usage tracking and budget enforcement

#### Phase 4: Integration & Delivery (Week 4)
- [ ] Telegram bot integration
- [ ] Report formatting and message delivery
- [ ] Scheduling system (cron or APScheduler)
- [ ] Error handling and retry logic

#### Phase 5: Testing & Deployment (Week 5)
- [ ] Unit tests for collectors
- [ ] Integration tests for LangGraph workflow
- [ ] Docker image build and optimization
- [ ] EC2 deployment and monitoring
- [ ] Documentation (README, runbook)

---

### 9. NON-FUNCTIONAL REQUIREMENTS

#### 9.1 Performance
- Complete monitoring cycle in <10 minutes
- Parallel data collection where possible
- Efficient LLM token usage (<50k tokens per report)

#### 9.2 Reliability
- Graceful degradation (partial results if some checks fail)
- Retry logic for transient failures (3 attempts with exponential backoff)
- Comprehensive error logging

#### 9.3 Security
- No hardcoded credentials (environment variables only)
- SSH keys stored securely with restricted permissions
- IAM roles with minimal required permissions
- No sensitive data in logs

#### 9.4 Maintainability
- Modular collector design (easy to add new targets)
- Clear separation of concerns (collectors, agents, delivery)
- Configuration-driven behavior (no code changes for new targets)
- Comprehensive logging with structured format

---

### 10. OUT OF SCOPE (Current Phase)

- ❌ Historical data storage and trending
- ❌ Alert deduplication and caching
- ❌ Auto-remediation actions
- ❌ Web dashboard/UI
- ❌ Multi-user support
- ❌ Real-time alerts (only scheduled reports)
- ❌ Advanced anomaly detection (ML models)
- ❌ Integration with incident management tools
- ❌ Compliance certifications
- ❌ High availability/failover setup

---

### 11. SUCCESS CRITERIA

✅ System successfully monitors all 7 targets
✅ AI agents provide accurate root cause analysis
✅ Telegram reports are clear and actionable
✅ Daily LLM costs stay under $3
✅ Monitoring completes within 10 minutes
✅ Configuration changes don't require code deployment
✅ Zero false positives in test period (2 weeks)

---

### 12. RISKS & MITIGATIONS

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM costs exceed budget | High | Token counting, request throttling, prompt optimization |
| AWS API rate limiting | Medium | Exponential backoff, request batching |
| SSH connection failures | Medium | Timeout handling, fallback to last known state |
| Docker API issues | Low | Error handling, skip failed containers |
| Telegram delivery failure | High | Retry queue, local log backup |

---

### 13. NEXT STEPS FOR DEVELOPMENT TEAM

1. **Architecture Review**: Validate LangGraph workflow design
2. **Tech Spike**: Test Claude Haiku 4.5 on Bedrock for analysis quality
3. **Prototype**: Build minimal viable workflow (1 EC2 + 1 API endpoint)
4. **Cost Testing**: Measure actual LLM token usage per monitoring cycle
5. **Infrastructure Setup**: Prepare EC2 instance, IAM roles, Telegram bot

---

**Document Version**: 1.0
**Date**: 2025-12-26
**Author**: Business Analyst (Claude Code)
**Reviewers**: Software Architect, Development Team, Product Owner
