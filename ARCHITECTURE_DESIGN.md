# Software Architecture Design
## IT Infrastructure Monitoring AI Agents

**Version**: 1.0
**Date**: 2025-12-27
**Architect**: Software Architect (Claude Code)

---

## 1. ARCHITECTURE OVERVIEW

### 1.1 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      Monitoring System (EC2/Docker)              │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Main Orchestrator                       │  │
│  │              (scheduler + LangGraph runner)               │  │
│  └──────────────┬───────────────────────────────────────────┘  │
│                 │                                                │
│  ┌──────────────▼───────────────────────────────────────────┐  │
│  │              LangGraph Workflow StateGraph                │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────────┐   │  │
│  │  │  Data Collection Phase (Parallel)                 │   │  │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐         │   │  │
│  │  │  │ EC2      │ │ VPS      │ │ Docker   │  ...    │   │  │
│  │  │  │ Collector│ │ Collector│ │ Collector│         │   │  │
│  │  │  └──────────┘ └──────────┘ └──────────┘         │   │  │
│  │  └──────────────────┬───────────────────────────────┘   │  │
│  │                     │                                     │  │
│  │  ┌──────────────────▼───────────────────────────────┐   │  │
│  │  │       Aggregation & Status Classification         │   │  │
│  │  │    (Determine red/yellow/green for each check)    │   │  │
│  │  └──────────────────┬───────────────────────────────┘   │  │
│  │                     │                                     │  │
│  │  ┌──────────────────▼───────────────────────────────┐   │  │
│  │  │  AI Analysis Agent (Bedrock Claude Haiku 4.5)    │   │  │
│  │  │  - Root cause analysis                            │   │  │
│  │  │  - Actionable recommendations                     │   │  │
│  │  └──────────────────┬───────────────────────────────┘   │  │
│  │                     │                                     │  │
│  │  ┌──────────────────▼───────────────────────────────┐   │  │
│  │  │    Report Generation Agent (Bedrock)              │   │  │
│  │  │    - Format Telegram message                      │   │  │
│  │  │    - Structure sections with emojis               │   │  │
│  │  └──────────────────┬───────────────────────────────┘   │  │
│  │                     │                                     │  │
│  │  ┌──────────────────▼───────────────────────────────┐   │  │
│  │  │       Telegram Delivery                           │   │  │
│  │  │       (Send formatted report)                     │   │  │
│  │  └───────────────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Supporting Components                                    │ │
│  │  - Config Loader (YAML validation)                       │ │
│  │  - Budget Tracker (LLM cost monitoring)                  │ │
│  │  - Logger (structured logging)                           │ │
│  │  - Retry Handler (exponential backoff)                   │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
         │                  │                    │
         ▼                  ▼                    ▼
    AWS Services      External Systems      Telegram API
    - Bedrock         - VPS (SSH)           - Bot API
    - CloudWatch      - PostgreSQL
    - S3              - API Endpoints
    - EC2 API         - Azure AI
```

### 1.2 Design Principles

1. **Modularity**: Each collector is independent and pluggable
2. **Fail-Safe**: Partial failures don't stop entire workflow
3. **Configuration-Driven**: All targets/thresholds in YAML
4. **Cost-Aware**: Token tracking at every LLM call
5. **Stateless**: No database, all state in LangGraph workflow
6. **Observable**: Structured logging for debugging

---

## 2. DIRECTORY STRUCTURE

```
monitoring_agents/
├── src/
│   ├── __init__.py
│   ├── main.py                      # Entry point + scheduler
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── models.py                # Pydantic models for config
│   │   ├── loader.py                # YAML loader + validation
│   │   └── settings.py              # Environment variable handler
│   │
│   ├── collectors/                  # Data collection modules
│   │   ├── __init__.py
│   │   ├── base.py                  # Abstract base collector
│   │   ├── ec2_collector.py         # EC2 metrics (CloudWatch)
│   │   ├── vps_collector.py         # VPS metrics (SSH)
│   │   ├── docker_collector.py      # Docker status
│   │   ├── api_collector.py         # API health checks
│   │   ├── database_collector.py    # PostgreSQL checks
│   │   ├── llm_collector.py         # LLM availability
│   │   └── s3_collector.py          # S3 statistics
│   │
│   ├── agents/                      # LangGraph agents
│   │   ├── __init__.py
│   │   ├── workflow.py              # LangGraph StateGraph definition
│   │   ├── state.py                 # Shared state schema
│   │   ├── analysis_agent.py        # Root cause analysis
│   │   └── report_agent.py          # Report generation
│   │
│   ├── services/                    # Supporting services
│   │   ├── __init__.py
│   │   ├── bedrock_client.py        # Bedrock wrapper with token tracking
│   │   ├── telegram_client.py       # Telegram bot wrapper
│   │   ├── budget_tracker.py        # Daily budget enforcement
│   │   └── retry_handler.py         # Exponential backoff logic
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py                # Structured logging setup
│       ├── status.py                # Status enum (red/yellow/green)
│       └── metrics.py               # Metric data classes
│
├── config/
│   ├── config.yaml                  # Main configuration file
│   └── config.example.yaml          # Example template
│
├── tests/
│   ├── __init__.py
│   ├── test_collectors/
│   ├── test_agents/
│   └── test_integration/
│
├── deployment/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── entrypoint.sh
│   └── requirements.txt
│
├── .env.example                     # Environment variable template
├── .gitignore
├── README.md
├── TECHNICAL_REQUIREMENTS.md
├── ARCHITECTURE_DESIGN.md           # This document
└── DEVELOPER_TASKS.md               # Implementation tasks
```

---

## 3. CORE COMPONENTS DESIGN

### 3.1 Configuration System

**File**: `src/config/models.py`

```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from enum import Enum

class EC2InstanceConfig(BaseModel):
    instance_id: str
    name: str
    region: Optional[str] = "us-east-1"

class VPSServerConfig(BaseModel):
    host: str
    name: str
    ssh_key_path: str
    port: int = 22
    username: str = "ubuntu"

class APIEndpointConfig(BaseModel):
    url: str
    name: str
    timeout_ms: Optional[int] = 5000

class DatabaseConfig(BaseModel):
    host: str
    port: int = 5432
    database: str
    table: Optional[str] = None
    ssl_mode: str = "require"

class LLMModelConfig(BaseModel):
    provider: str  # "azure" or "bedrock"
    endpoint: Optional[str] = None
    model_id: Optional[str] = None

class S3BucketConfig(BaseModel):
    bucket: str
    region: str = "us-east-1"

class ThresholdsConfig(BaseModel):
    cpu_red: int = 90
    cpu_yellow: int = 70
    ram_red: int = 90
    ram_yellow: int = 70
    disk_free_red: int = 10
    disk_free_yellow: int = 20
    api_timeout_ms: int = 5000
    api_slow_ms: int = 2000

class MonitoringConfig(BaseModel):
    schedule: str = "0 */6 * * *"  # Cron syntax

class TelegramConfig(BaseModel):
    bot_token: str
    chat_id: str

class LLMConfig(BaseModel):
    provider: str = "bedrock"
    model: str = "anthropic.claude-haiku-4-5"
    region: str = "us-east-1"
    max_tokens: int = 4096
    daily_budget_usd: float = 3.0

class MonitoringSystemConfig(BaseModel):
    monitoring: MonitoringConfig
    targets: dict
    thresholds: ThresholdsConfig
    telegram: TelegramConfig
    llm: LLMConfig
```

**File**: `src/config/loader.py`

```python
import yaml
import os
from pathlib import Path
from .models import MonitoringSystemConfig

class ConfigLoader:
    @staticmethod
    def load_from_file(config_path: str) -> MonitoringSystemConfig:
        """Load and validate YAML config with env var substitution"""
        with open(config_path, 'r') as f:
            raw_config = yaml.safe_load(f)

        # Substitute environment variables (${VAR_NAME})
        raw_config = ConfigLoader._substitute_env_vars(raw_config)

        # Validate with Pydantic
        return MonitoringSystemConfig(**raw_config)

    @staticmethod
    def _substitute_env_vars(config: dict) -> dict:
        """Recursively substitute ${ENV_VAR} with environment values"""
        # Implementation: recursively traverse dict/list and replace
        pass
```

---

### 3.2 Collector Architecture

**File**: `src/collectors/base.py`

```python
from abc import ABC, abstractmethod
from typing import List, Any
from dataclasses import dataclass
from enum import Enum
import logging

class HealthStatus(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    UNKNOWN = "unknown"

@dataclass
class CollectorResult:
    """Standard result format from all collectors"""
    collector_name: str
    target_name: str
    status: HealthStatus
    metrics: dict  # Raw metric values
    message: str   # Human-readable summary
    error: Optional[str] = None
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

class BaseCollector(ABC):
    """Abstract base class for all collectors"""

    def __init__(self, config: Any, thresholds: dict, logger: logging.Logger):
        self.config = config
        self.thresholds = thresholds
        self.logger = logger

    @abstractmethod
    async def collect(self) -> List[CollectorResult]:
        """Collect metrics and return results"""
        pass

    def _determine_status(self, metric_name: str, value: float) -> HealthStatus:
        """Helper to determine status based on thresholds"""
        # Implementation: check against self.thresholds
        pass
```

**Example Implementation**: `src/collectors/ec2_collector.py`

```python
import boto3
from datetime import datetime, timedelta
from .base import BaseCollector, CollectorResult, HealthStatus

class EC2Collector(BaseCollector):
    """Collects CPU, RAM, disk metrics from EC2 via CloudWatch"""

    def __init__(self, config: List[EC2InstanceConfig], thresholds: dict, logger):
        super().__init__(config, thresholds, logger)
        self.cloudwatch = boto3.client('cloudwatch')
        self.ec2 = boto3.client('ec2')

    async def collect(self) -> List[CollectorResult]:
        results = []
        for instance_config in self.config:
            try:
                result = await self._collect_instance(instance_config)
                results.append(result)
            except Exception as e:
                self.logger.error(f"EC2 collection failed for {instance_config.name}: {e}")
                results.append(CollectorResult(
                    collector_name="ec2",
                    target_name=instance_config.name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message=f"Collection failed: {str(e)}",
                    error=str(e)
                ))
        return results

    async def _collect_instance(self, config: EC2InstanceConfig) -> CollectorResult:
        # Get metrics from CloudWatch
        cpu = self._get_cloudwatch_metric(config.instance_id, 'CPUUtilization')
        # Memory requires CloudWatch agent - handle if not available
        # Disk - EBS volume metrics

        # Determine status
        status = self._determine_overall_status(cpu, memory, disk)

        return CollectorResult(
            collector_name="ec2",
            target_name=config.name,
            status=status,
            metrics={"cpu": cpu, "ram": memory, "disk": disk},
            message=f"CPU: {cpu:.1f}%, RAM: {memory:.1f}%, Disk: {disk:.1f}% free"
        )

    def _get_cloudwatch_metric(self, instance_id: str, metric_name: str) -> float:
        """Fetch latest metric from CloudWatch"""
        # Implementation with boto3 get_metric_statistics
        pass
```

**Key Design Decisions**:
- All collectors return `List[CollectorResult]` for consistency
- Collectors handle their own errors and return UNKNOWN status
- Async/await for concurrent execution in LangGraph
- Each collector independently determines red/yellow/green status

---

### 3.3 LangGraph Workflow

**File**: `src/agents/state.py`

```python
from typing import TypedDict, List, Annotated
from src.collectors.base import CollectorResult
import operator

class MonitoringState(TypedDict):
    """Shared state across LangGraph workflow"""

    # Collection phase outputs
    ec2_results: List[CollectorResult]
    vps_results: List[CollectorResult]
    docker_results: List[CollectorResult]
    api_results: List[CollectorResult]
    database_results: List[CollectorResult]
    llm_results: List[CollectorResult]
    s3_results: List[CollectorResult]

    # Aggregated results
    all_results: List[CollectorResult]
    issues: List[CollectorResult]  # Only red/yellow items

    # AI analysis outputs
    root_cause_analysis: str
    recommendations: str

    # Final report
    telegram_message: str

    # Metadata
    execution_start: float
    token_usage: Annotated[int, operator.add]  # Cumulative
    errors: Annotated[List[str], operator.add]
```

**File**: `src/agents/workflow.py`

```python
from langgraph.graph import StateGraph, END
from .state import MonitoringState
from src.collectors import *
from src.services.bedrock_client import BedrockClient
from src.services.budget_tracker import BudgetTracker

class MonitoringWorkflow:
    """LangGraph workflow orchestrator"""

    def __init__(self, config: MonitoringSystemConfig):
        self.config = config
        self.bedrock = BedrockClient(config.llm)
        self.budget_tracker = BudgetTracker(config.llm.daily_budget_usd)

        # Initialize collectors
        self.collectors = {
            "ec2": EC2Collector(config.targets.ec2_instances, config.thresholds, logger),
            "vps": VPSCollector(config.targets.vps_servers, config.thresholds, logger),
            # ... other collectors
        }

        # Build graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Construct LangGraph workflow"""

        workflow = StateGraph(MonitoringState)

        # Add collection nodes (will run in parallel)
        workflow.add_node("collect_ec2", self._collect_ec2)
        workflow.add_node("collect_vps", self._collect_vps)
        workflow.add_node("collect_docker", self._collect_docker)
        workflow.add_node("collect_api", self._collect_api)
        workflow.add_node("collect_database", self._collect_database)
        workflow.add_node("collect_llm", self._collect_llm)
        workflow.add_node("collect_s3", self._collect_s3)

        # Add processing nodes
        workflow.add_node("aggregate", self._aggregate_results)
        workflow.add_node("analyze", self._ai_analysis)
        workflow.add_node("generate_report", self._generate_report)
        workflow.add_node("send_telegram", self._send_telegram)

        # Define edges - parallel collection
        workflow.set_entry_point("collect_ec2")
        # All collectors run in parallel, then converge at aggregate
        for collector in ["collect_ec2", "collect_vps", "collect_docker",
                          "collect_api", "collect_database", "collect_llm", "collect_s3"]:
            workflow.add_edge(collector, "aggregate")

        # Sequential processing after aggregation
        workflow.add_edge("aggregate", "analyze")
        workflow.add_edge("analyze", "generate_report")
        workflow.add_edge("generate_report", "send_telegram")
        workflow.add_edge("send_telegram", END)

        return workflow.compile()

    async def _collect_ec2(self, state: MonitoringState) -> dict:
        """Collection node for EC2"""
        results = await self.collectors["ec2"].collect()
        return {"ec2_results": results}

    # Similar methods for other collectors...

    async def _aggregate_results(self, state: MonitoringState) -> dict:
        """Combine all collector results"""
        all_results = (
            state.get("ec2_results", []) +
            state.get("vps_results", []) +
            # ... other results
        )

        # Filter issues (red or yellow status)
        issues = [r for r in all_results if r.status in [HealthStatus.RED, HealthStatus.YELLOW]]

        return {
            "all_results": all_results,
            "issues": issues
        }

    async def _ai_analysis(self, state: MonitoringState) -> dict:
        """Root cause analysis using Bedrock"""
        if not state["issues"]:
            return {
                "root_cause_analysis": "No issues detected",
                "recommendations": "All systems healthy"
            }

        # Check budget before calling LLM
        if not self.budget_tracker.can_make_request():
            return {
                "root_cause_analysis": "Budget exceeded",
                "recommendations": "Manual review required",
                "errors": ["Daily LLM budget exceeded"]
            }

        # Prepare prompt for Claude
        prompt = self._build_analysis_prompt(state["issues"])

        # Call Bedrock
        response, tokens = await self.bedrock.invoke(prompt)
        self.budget_tracker.record_usage(tokens)

        # Parse response (assuming structured output)
        analysis = self._parse_analysis_response(response)

        return {
            "root_cause_analysis": analysis["root_cause"],
            "recommendations": analysis["recommendations"],
            "token_usage": tokens
        }

    def _build_analysis_prompt(self, issues: List[CollectorResult]) -> str:
        """Construct analysis prompt for Claude"""
        prompt = """You are an expert SRE analyzing infrastructure issues.

Issues detected:
"""
        for issue in issues:
            prompt += f"\n- {issue.target_name} ({issue.collector_name}): {issue.message}"
            prompt += f"\n  Metrics: {issue.metrics}"

        prompt += """

Analyze these issues:
1. Identify root causes (correlate related issues)
2. Prioritize by severity
3. Provide specific remediation steps

Format your response as JSON:
{
  "root_cause": "Brief explanation of underlying cause",
  "recommendations": [
    {"priority": "high", "action": "Specific step 1"},
    {"priority": "medium", "action": "Specific step 2"}
  ]
}
"""
        return prompt

    async def _generate_report(self, state: MonitoringState) -> dict:
        """Generate Telegram message using LLM"""
        # Similar LLM call to format the final report
        pass

    async def _send_telegram(self, state: MonitoringState) -> dict:
        """Send report via Telegram"""
        from src.services.telegram_client import TelegramClient

        telegram = TelegramClient(self.config.telegram)
        await telegram.send_message(state["telegram_message"])

        return {}

    async def run(self) -> MonitoringState:
        """Execute the workflow"""
        initial_state = MonitoringState(
            execution_start=time.time(),
            token_usage=0,
            errors=[]
        )

        final_state = await self.graph.ainvoke(initial_state)
        return final_state
```

---

### 3.4 Bedrock Client with Budget Tracking

**File**: `src/services/bedrock_client.py`

```python
import boto3
import json
from typing import Tuple

class BedrockClient:
    """Wrapper for Amazon Bedrock with token tracking"""

    def __init__(self, llm_config: LLMConfig):
        self.config = llm_config
        self.client = boto3.client('bedrock-runtime', region_name=llm_config.region)
        self.model_id = f"anthropic.{llm_config.model}"

    async def invoke(self, prompt: str, system_prompt: str = None) -> Tuple[str, int]:
        """
        Invoke Claude Haiku and return (response, token_count)
        """
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.config.max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        if system_prompt:
            request_body["system"] = system_prompt

        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())

        # Extract token usage
        input_tokens = response_body['usage']['input_tokens']
        output_tokens = response_body['usage']['output_tokens']
        total_tokens = input_tokens + output_tokens

        # Extract text
        content = response_body['content'][0]['text']

        return content, total_tokens
```

**File**: `src/services/budget_tracker.py`

```python
import json
from pathlib import Path
from datetime import date

class BudgetTracker:
    """Track daily LLM costs and enforce budget"""

    # Claude Haiku 4.5 pricing (as of Dec 2024)
    INPUT_PRICE_PER_1M = 0.80   # $0.80 per 1M input tokens
    OUTPUT_PRICE_PER_1M = 4.00  # $4.00 per 1M output tokens

    def __init__(self, daily_budget_usd: float):
        self.daily_budget = daily_budget_usd
        self.state_file = Path("/tmp/budget_state.json")
        self._load_state()

    def can_make_request(self, estimated_tokens: int = 10000) -> bool:
        """Check if request is within budget"""
        estimated_cost = self._calculate_cost(estimated_tokens)
        return (self.today_spent + estimated_cost) < self.daily_budget

    def record_usage(self, input_tokens: int, output_tokens: int):
        """Record token usage and update costs"""
        cost = (
            (input_tokens / 1_000_000) * self.INPUT_PRICE_PER_1M +
            (output_tokens / 1_000_000) * self.OUTPUT_PRICE_PER_1M
        )

        self.today_spent += cost
        self._save_state()

    def _load_state(self):
        """Load daily spending from file"""
        if self.state_file.exists():
            with open(self.state_file) as f:
                state = json.load(f)

            # Reset if new day
            if state['date'] != str(date.today()):
                self.today_spent = 0.0
            else:
                self.today_spent = state['spent']
        else:
            self.today_spent = 0.0

    def _save_state(self):
        """Persist daily spending"""
        with open(self.state_file, 'w') as f:
            json.dump({
                'date': str(date.today()),
                'spent': self.today_spent
            }, f)
```

---

### 3.5 Main Entry Point

**File**: `src/main.py`

```python
import asyncio
import schedule
import time
from src.config.loader import ConfigLoader
from src.agents.workflow import MonitoringWorkflow
from src.utils.logger import setup_logger

logger = setup_logger()

class MonitoringApp:
    """Main application orchestrator"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = ConfigLoader.load_from_file(config_path)
        self.workflow = MonitoringWorkflow(self.config)

    async def run_monitoring_cycle(self):
        """Execute one monitoring cycle"""
        try:
            logger.info("Starting monitoring cycle")
            start_time = time.time()

            final_state = await self.workflow.run()

            duration = time.time() - start_time
            logger.info(f"Monitoring cycle completed in {duration:.1f}s")
            logger.info(f"Token usage: {final_state['token_usage']}")

            if final_state.get('errors'):
                logger.warning(f"Errors encountered: {final_state['errors']}")

        except Exception as e:
            logger.error(f"Monitoring cycle failed: {e}", exc_info=True)

    def start_scheduler(self):
        """Start scheduled monitoring"""
        cron = self.config.monitoring.schedule

        # Convert cron to schedule library format (simplified)
        # For production, use APScheduler with cron support
        schedule.every(6).hours.do(lambda: asyncio.run(self.run_monitoring_cycle()))

        logger.info(f"Scheduler started with cron: {cron}")

        while True:
            schedule.run_pending()
            time.sleep(60)

def main():
    """Entry point"""
    app = MonitoringApp()

    # Run once immediately, then start scheduler
    asyncio.run(app.run_monitoring_cycle())
    app.start_scheduler()

if __name__ == "__main__":
    main()
```

---

## 4. DEPLOYMENT ARCHITECTURE

### 4.1 Docker Setup

**File**: `deployment/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY deployment/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Create secrets directory
RUN mkdir -p /app/secrets

# Set Python path
ENV PYTHONPATH=/app

# Entry point
CMD ["python", "-m", "src.main"]
```

**File**: `deployment/docker-compose.yml`

```yaml
version: '3.8'

services:
  monitoring-agent:
    build:
      context: ..
      dockerfile: deployment/Dockerfile
    container_name: infra-monitoring-agent
    restart: unless-stopped

    environment:
      - AWS_REGION=${AWS_REGION}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

    volumes:
      - ../config/config.yaml:/app/config/config.yaml:ro
      - ./secrets:/app/secrets:ro
      - budget-state:/tmp

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  budget-state:
```

---

## 5. ERROR HANDLING & RETRY STRATEGY

**File**: `src/services/retry_handler.py`

```python
import asyncio
from typing import Callable, Any
from functools import wraps

class RetryHandler:
    """Exponential backoff retry logic"""

    @staticmethod
    async def with_retry(
        func: Callable,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exceptions: tuple = (Exception,)
    ) -> Any:
        """
        Retry async function with exponential backoff
        """
        for attempt in range(max_attempts):
            try:
                return await func()
            except exceptions as e:
                if attempt == max_attempts - 1:
                    raise

                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s")
                await asyncio.sleep(delay)
```

**Usage in Collectors**:

```python
async def collect(self) -> List[CollectorResult]:
    results = []
    for target in self.config:
        result = await RetryHandler.with_retry(
            lambda: self._collect_target(target),
            max_attempts=3,
            exceptions=(ConnectionError, TimeoutError)
        )
        results.append(result)
    return results
```

---

## 6. LOGGING STRATEGY

**File**: `src/utils/logger.py`

```python
import logging
import sys
from pythonjsonlogger import jsonlogger

def setup_logger() -> logging.Logger:
    """Configure structured JSON logging"""

    logger = logging.getLogger("monitoring_agent")
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s',
        timestamp=True
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
```

---

## 7. SECURITY CONSIDERATIONS

1. **Credential Management**:
   - All secrets in environment variables
   - SSH keys mounted as read-only volumes
   - No secrets in logs (use redaction for error messages)

2. **IAM Roles** (preferred for EC2 deployment):
   - Minimal permissions: CloudWatch read, EC2 describe, S3 list/get
   - No write permissions except Bedrock invoke

3. **Network Security**:
   - Outbound-only connections
   - No exposed ports (Telegram uses webhook or polling)

4. **Budget Protection**:
   - Hard stop at daily budget limit
   - Alert when 80% budget consumed

---

## 8. TESTING STRATEGY

### 8.1 Unit Tests
- Mock AWS services with `moto`
- Test each collector independently
- Validate status determination logic

### 8.2 Integration Tests
- Test LangGraph workflow with minimal config
- Mock Bedrock responses
- Verify Telegram message formatting

### 8.3 Cost Testing
- Run with actual Bedrock calls
- Measure token usage per cycle
- Validate budget tracking accuracy

---

## 9. MONITORING & OBSERVABILITY

1. **Application Logs**:
   - Structured JSON logs to stdout
   - Collected by Docker logging driver
   - Can forward to CloudWatch Logs

2. **Metrics to Track**:
   - Monitoring cycle duration
   - Token usage per cycle
   - Error count by collector
   - Budget utilization

3. **Alerting** (future enhancement):
   - Alert if monitoring cycle fails
   - Alert if budget exceeded
   - Alert if Telegram delivery fails

---

## 10. PERFORMANCE OPTIMIZATION

1. **Parallel Collection**: All collectors run concurrently via LangGraph
2. **Connection Pooling**: Reuse boto3 clients across runs
3. **Prompt Optimization**: Minimize token usage in LLM prompts
4. **Lazy Initialization**: Only initialize collectors for enabled targets

---

## 11. FUTURE ENHANCEMENTS (Post-MVP)

1. **Historical Tracking**: Add TimescaleDB for trend analysis
2. **Auto-Remediation**: Execute predefined remediation scripts
3. **Web Dashboard**: Real-time status view
4. **Alert Deduplication**: Suppress repeat alerts
5. **Anomaly Detection**: ML-based threshold adaptation
6. **Multi-Tenant**: Support multiple teams/environments

---

## 12. TECHNOLOGY JUSTIFICATION

| Technology | Reason |
|------------|--------|
| **LangGraph** | Declarative workflow orchestration, built-in state management, easy debugging |
| **Pydantic** | Runtime config validation, clear error messages, type safety |
| **asyncio** | Concurrent data collection, efficient I/O operations |
| **boto3** | Official AWS SDK, comprehensive Bedrock support |
| **paramiko** | Mature SSH library, good error handling |
| **httpx** | Async HTTP client, better than requests for concurrent API checks |
| **Docker** | Consistent deployment, easy EC2 setup, isolation |

---

## 13. DESIGN TRADE-OFFS

| Decision | Trade-off | Rationale |
|----------|-----------|-----------|
| Stateless design | No historical data | Simpler implementation, faster MVP |
| Single LLM provider | Less redundancy | Cost control, learning focus |
| Scheduled reports only | No real-time alerts | Simpler architecture, budget friendly |
| YAML config | Limited validation | User-friendly, easy to edit |
| No caching | Higher LLM costs | Avoid stale data, simpler logic |

---

## 14. ROLLOUT PLAN

### Phase 1: Local Development (Week 1-2)
- Implement core framework
- Test with 1-2 collectors
- Validate LangGraph workflow

### Phase 2: Full Implementation (Week 3-4)
- Complete all 7 collectors
- Integrate AI agents
- Test end-to-end

### Phase 3: EC2 Deployment (Week 5)
- Build Docker image
- Deploy to EC2
- Run test cycles

### Phase 4: Production (Week 6)
- Monitor for 1 week
- Tune thresholds
- Optimize prompts for cost

---

**Next Step**: See `DEVELOPER_TASKS.md` for detailed implementation tasks.
