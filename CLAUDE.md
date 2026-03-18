# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered IT infrastructure monitoring system that collects metrics from multiple sources (EC2, VPS, Docker, APIs, PostgreSQL, S3, LLM models), uses Claude Haiku via Amazon Bedrock for root cause analysis, and sends Telegram reports on a cron schedule.

**Stack**: LangGraph + Amazon Bedrock + APScheduler + boto3 + paramiko + httpx

## Commands

```bash
# Install dependencies
pip install -r deployment/requirements.txt

# Run once (for testing)
python -m src.main --run-once

# Run once without sending Telegram messages
python -m src.main --run-once --dry-run

# Run with scheduler (production mode)
python -m src.main

# Custom config file
python -m src.main --config /path/to/config.yaml

# Run all tests
pytest

# Run a single test file
pytest tests/test_collectors/test_ec2_collector.py -v

# Run with coverage
pytest --cov=src --cov-report=html

# Docker
docker-compose up -d
docker logs -f monitoring-agents

# Visualize LangGraph workflow
python scripts/visualize_workflow.py
```

## Architecture

### Workflow (LangGraph StateGraph)

Sequential nodes: `aggregate` → `history_filter` → `analyze` → `generate_report` → `send_telegram`

- **aggregate**: All collectors run in parallel via `asyncio.gather()`. Each returns a `CollectorResult` with status `GREEN/YELLOW/RED/UNKNOWN`. Failures are caught per-collector — partial failures never halt the workflow.
- **history_filter**: Dampens first-occurrence threshold breaches from RED to YELLOW. Binary failures (connection errors, container down) pass through unchanged. Only numeric threshold metrics (CPU, RAM, disk, API response time) are eligible for dampening.
- **analyze**: Budget-checked call to Bedrock (Claude Haiku). Skipped if no issues or daily budget exceeded. Returns structured root cause analysis and recommendations.
- **generate_report**: Formats collected results into a Telegram message.
- **send_telegram**: Delivers the message; falls back to plain text if Markdown parsing fails.

State is defined in `src/agents/state.py` as a `TypedDict`. Fields `token_usage` and `errors` use `operator.add` for automatic accumulation across nodes.

### Configuration System

Single YAML file (`config/config.yaml`) with `${ENV_VAR}` substitution. Loaded via `src/config/loader.py` and validated through Pydantic models in `src/config/models.py`. Copy `config/config.example.yaml` and `.env.example` to get started.

### Collectors (`src/collectors/`)

All extend `BaseCollector` in `base.py`, which provides the `@safe_collect` decorator for error isolation. SSH-based collectors (VPS, Docker) use `ssh_helper.py` for connection management. Each collector maps its raw metrics to `HealthStatus` using threshold values from config.

Collectors are only instantiated if the corresponding targets section is non-empty in config. Docker uses the same VPS server configs as the VPS collector.

### Services (`src/services/`)

- `bedrock_client.py` — wraps Bedrock `invoke_model`, tracks token counts
- `budget_tracker.py` — enforces daily USD cap; call `can_make_request()` before LLM calls
- `metric_history.py` — persists daily per-metric incident counts to `data/metric_history.json` for alert dampening; resets automatically on date change
- `telegram_client.py` — sends messages with Markdown; auto-retries with plain text on parse errors
- `retry_handler.py` — exponential backoff for transient failures

### Shared Utilities (`src/utils/`)

- `metrics.py` — `CollectorResult` dataclass (the universal return type of all collectors)
- `status.py` — `HealthStatus` enum (`GREEN/YELLOW/RED/UNKNOWN`)

### Key Files

| File | Role |
|------|------|
| `src/main.py` | Entry point, CLI args, APScheduler setup |
| `src/workflow.py` | LangGraph graph definition and node implementations |
| `src/agents/state.py` | `MonitoringState` TypedDict |
| `src/agents/analysis_agent.py` | Bedrock prompt + response parsing |
| `src/agents/report_agent.py` | Telegram message formatting |
| `src/config/models.py` | All Pydantic config models |
| `deployment/requirements.txt` | Python dependencies |
| `config/config.example.yaml` | Config template |
| `.env.example` | Environment variables template |

## Tests

Tests in `tests/conftest.py` load `config/config.yaml` and provide fixtures per target type. Tests that require a target (e.g. `ec2_configs`) auto-skip when that target is absent from config — no mocking of infrastructure is done; tests hit real targets.

## Environment Variables

Required in `.env`:
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or use IAM role)
- `AWS_DEFAULT_REGION`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- Database credentials as referenced in config YAML

## LangSmith Tracing (Optional)

Set `LANGCHAIN_API_KEY` and `LANGCHAIN_TRACING_V2=true` in `.env`. See `docs/LangSmith.md`.

## Cron Schedule Format

Config `schedule` field uses standard 5-field cron syntax parsed by APScheduler:
```
"0 */6 * * *"   # Every 6 hours
"*/30 * * * *"  # Every 30 minutes
```
