# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered IT infrastructure monitoring system that collects metrics from multiple sources (EC2, VPS, Docker, Docker logs, HTTP APIs, PostgreSQL, S3, LLM endpoints), uses Claude Haiku via Amazon Bedrock for root cause analysis, and sends Telegram reports on a cron schedule.

**Stack**: LangGraph + Amazon Bedrock + APScheduler + boto3 + paramiko + httpx + Pydantic

## Commands

```bash
# Install dependencies
pip install -r deployment/requirements.txt

# Run once (for testing)
python -m src.main --run-once

# Run once without sending Telegram messages
python -m src.main --run-once --dry-run

# Run with scheduler (production mode; also runs one cycle immediately at startup)
python -m src.main

# Custom config file
python -m src.main --config /path/to/config.yaml

# Same as above but exports .env first and fails fast on missing Telegram vars
./run_monitoring.sh config/config.yaml --run-once

# Run all tests (must be run from the repo root; there is no pytest.ini)
pytest

# Run a single test file
pytest tests/test_collectors/test_ec2_collector.py -v

# Coverage (pytest-cov is NOT in requirements.txt — install it first)
pip install pytest-cov && pytest --cov=src --cov-report=html

# Docker: build + run + verify the deployed revision, from the repo root
./deployment/rebuild.sh
./deployment/rebuild.sh --no-cache      # force clean rebuild
docker logs -f monitoring-agent          # container name is singular
docker compose -f deployment/docker-compose.yml down

# Visualize LangGraph workflow (needs pygraphviz or grandalf)
python scripts/visualize_workflow.py

# Project token cost / budget profiling
python scripts/profile_costs.py
```

Prefer `./deployment/rebuild.sh` over raw `docker compose` commands: the compose file lives in `deployment/` with `context: ..`, and the script stamps `GIT_SHA` into the image and then verifies the *running* container reports that SHA. Bare `docker build` + `docker compose up` has silently started stale code here before.

No linter or formatter is configured — match the style of surrounding code (Google-style docstrings on every public method, type hints throughout).

## Architecture

### Workflow (LangGraph StateGraph)

Sequential nodes in `src/workflow.py`: `aggregate` → `history_filter` → `analyze` → `generate_report` → `send_telegram`

- **aggregate**: All collectors run in parallel via `asyncio.gather(..., return_exceptions=True)`. Each returns a list of `CollectorResult` with status `GREEN/YELLOW/RED/UNKNOWN`. Failures are caught per-collector — partial failures never halt the workflow. SSH collectors (VPS, Docker, DockerLogs) serialize per target host via `collectors/host_lock.py`, so their own work is not measured as that host's load; different hosts still run concurrently.
- **history_filter**: Dampens first-occurrence threshold breaches from RED to YELLOW (appends `[first occurrence today]` to the message). Binary failures (connection errors, container down) pass through unchanged. Only metrics listed in `MetricHistoryStore.THRESHOLD_METRICS` are eligible — currently VPS load/RAM/disk, EC2 CPU/disk, and API response time. SSL certificate expiry is deliberately excluded: `days_until_expiry` is monotonic rather than a noisy sample, and since the store resets daily, listing it would downgrade the first report of *every* day — including the day a cert actually expires. See the comment in that dict.
- **analyze**: Budget-checked call to Bedrock (Claude Haiku). Skipped if there are no issues or the daily budget is exceeded. Returns structured root cause analysis and recommendations.
- **generate_report**: Formats collected results into a Telegram message.
- **send_telegram**: Delivers the message; falls back to plain text if Markdown parsing fails.

State is defined in `src/agents/state.py` as a `TypedDict`. Fields `token_usage` and `errors` use `operator.add` for automatic accumulation across nodes. Nodes return partial dicts, not the whole state.

`_aggregate_results` and `_history_filter` both recompute `issues` as "status in RED/YELLOW/UNKNOWN" — if you change that predicate, change both.

### Configuration System

Single YAML file (`config/config.yaml`, gitignored) with `${ENV_VAR}` substitution. Loaded via `src/config/loader.py` and validated through Pydantic models in `src/config/models.py`. Copy `config/config.example.yaml` and `.env.example` to get started.

Every collector is only instantiated if its `targets.*` list is non-empty, so adding a target type means: Pydantic model in `config/models.py` → entry in `TargetsConfig` → gated block in `MonitoringWorkflow.__init__` → example in `config.example.yaml`.

Thresholds are passed to collectors as a plain dict (`config.thresholds.__dict__`), and `BaseCollector._determine_status(metric_name, value, higher_is_worse)` looks up `{metric_name}_red` / `{metric_name}_yellow` by naming convention. A threshold whose name doesn't follow that pattern silently yields `UNKNOWN`.

`api_endpoints` distinguishes three separate numbers that are easy to conflate: `timeout_ms` is the request deadline handed to httpx, while `slow_ms` (YELLOW) and `red_ms` (RED) are *response-time* thresholds that each fall back to the global `api_slow_ms` / `api_timeout_ms` when unset. Full HTML pages need looser response thresholds than `/health` endpoints, otherwise one global value either flaps on the pages or hides real slowdowns on the health checks.

### Collectors (`src/collectors/`)

| Collector | Config key | Notes |
|-----------|------------|-------|
| `ec2_collector` | `targets.ec2_instances` | CloudWatch averages; disk is opt-in via `monitor_disk: true` and requires the CloudWatch Agent publishing `disk_used_percent` |
| `vps_collector` | `targets.vps_servers` | SSH |
| `docker_collector` | `targets.vps_servers` | reuses the VPS server configs |
| `docker_logs_collector` | `targets.docker_logs` | configured separately per host, with its own `compose_file` and `error_patterns` |
| `api_collector` | `targets.api_endpoints` | |
| `database_collector` | `targets.databases` | PostgreSQL |
| `llm_collector` | `targets.llm_models` | `provider: azure` or `bedrock` |
| `s3_collector` | `targets.s3_buckets` | |
| `ssl_collector` | `targets.ssl_certificates` | TLS expiry lead-time warning. Verifies against `certifi`, **not** the system trust store — see below |

All extend `BaseCollector` in `base.py`. Decorate `collect()` with `@safe_collect`, which both isolates errors (returning a single `UNKNOWN` result instead of raising) and wraps the call in LangSmith `@traceable`. SSH-based collectors use `ssh_helper.py` for connection management and `host_lock.py` to serialize per host.

Three deliberate, non-obvious status rules:

- **VPS CPU is judged on 5-minute load average per core** (`load_red`/`load_yellow`, where 1.0 means the CPUs are exactly saturated), not a CPU percentage. A percentage sampled over a few seconds cannot distinguish a saturated host from a brief burst, which produced persistent false RED alarms. The instantaneous sample is still reported as `cpu_sample_pct` for context but is never alarmed on. EC2 CPU still uses `cpu_red`/`cpu_yellow` since it comes from CloudWatch averages.
- **A Docker container that exited with code 0 is GREEN**, not RED — these hosts run cron/one-shot containers. Non-zero exit is RED, restarting is YELLOW, unhealthy is RED.
- **The SSL collector verifies against `certifi`, never the system trust store.** A bare `ssl.create_default_context()` has *no usable CA file* on python.org macOS builds (`get_default_verify_paths()` points at a nonexistent `cert.pem`), so every host — including valid ones — fails with verify code 20, while the same code works in the `python:3.13-slim` container. Explicit `cafile=certifi.where()` makes dev and prod agree and matches what httpx (hence `api_collector`) already does. Also: classification is **date-first**, because OpenSSL reports only its first verify error — an expired cert behind a chain problem surfaces as code 20, not 10. And connection *refused* / DNS failure are RED (the remote definitively said no) while timeouts are UNKNOWN (indistinguishable from a blip on the monitoring host itself).

### Services (`src/services/`)

- `bedrock_client.py` — wraps Bedrock `invoke_model`, tracks token counts
- `budget_tracker.py` — enforces daily USD cap; call `can_make_request()` before LLM calls
- `metric_history.py` — persists daily per-metric incident counts to `data/metric_history.json` (gitignored) for alert dampening; resets automatically on date change
- `telegram_client.py` — sends messages with Markdown; auto-retries with plain text on parse errors; also `send_error_notification()` used by `main.py` when a whole cycle fails
- `retry_handler.py` — exponential backoff for transient failures

### Shared Utilities (`src/utils/`)

- `metrics.py` — `CollectorResult` dataclass (the universal return type of all collectors). It's a frozen-style dataclass mutated via `dataclasses.replace` in `history_filter`.
- `status.py` — `HealthStatus` enum (`GREEN/YELLOW/RED/UNKNOWN`)
- `sanitize.py` — `sanitize_error(exc)` strips IPs, hostnames, ports, paths, connection strings, ARNs, and AWS account IDs. **Every error string that can reach Telegram or the LLM prompt must go through it** — all eight collectors and `safe_collect` already do. See `docs/SECURITY_AUDIT.md`.
- `logger.py` — `setup_logger(name, level="INFO")` builds a JSON logger with `propagate=False`. Because of that, `--log-level DEBUG` / `LOG_LEVEL=DEBUG` only changes the root logger and does **not** turn on DEBUG output for module loggers; pass the level into `setup_logger` if you need it.

### Key Files

| File | Role |
|------|------|
| `src/main.py` | Entry point, CLI args, APScheduler setup, graceful shutdown |
| `src/workflow.py` | LangGraph graph definition, node implementations, collector wiring |
| `src/agents/state.py` | `MonitoringState` TypedDict |
| `src/agents/analysis_agent.py` | Bedrock prompt + response parsing |
| `src/agents/report_agent.py` | Telegram message formatting |
| `src/config/models.py` | All Pydantic config models and threshold defaults |
| `deployment/rebuild.sh` | Canonical local build/run/verify path |
| `deployment/requirements.txt` | Python dependencies |
| `config/config.example.yaml` | Config template |
| `.env.example` | Environment variables template |

## Tests

`tests/conftest.py` loads the real `config/config.yaml` and provides one fixture per target type. Tests that need a target (e.g. `ec2_configs`) **auto-skip** when that target is absent from config — so an empty or missing config silently skips most of the suite rather than failing. Tests hit real infrastructure; there is no wholesale mocking of targets. Async tests are explicitly marked `@pytest.mark.asyncio` (pytest-asyncio strict mode, no ini file). See `tests/README.md`.

## Environment Variables

Required in `.env`:
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or use IAM role)
- `AWS_DEFAULT_REGION`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- Database credentials and SSH key paths as referenced in the config YAML

`config/config*.yaml` (every variant except the tracked `config.example.yaml`), `.env`, `secrets/`, and `data/` are all gitignored — real config holds live hostnames and credentials. SSH private keys belong in `secrets/` (mounted read-only into the container); `chmod 600` them.

## LangSmith Tracing (Optional)

Set `LANGCHAIN_API_KEY` and `LANGCHAIN_TRACING_V2=true` in `.env` (optional `LANGCHAIN_PROJECT`, default `monitoring-agents`). See `docs/LangSmith.md`.

## Cron Schedule Format

Config `monitoring.schedule` uses standard 5-field cron syntax parsed by APScheduler:
```
"0 */6 * * *"   # Every 6 hours
"*/30 * * * *"  # Every 30 minutes
```
The scheduler uses `max_instances=1`, `coalesce=True`, and a 300s misfire grace, so cycles never overlap and a missed run collapses into one.

## Further Docs

`docs/OPERATIONS.md` (runbook), `docs/DEPLOYMENT.md`, `docs/EC2_DISK_MONITORING.md` + `docs/CLOUDWATCH_AGENT_SETUP_GUIDE.md` (CloudWatch Agent for EC2 disk metrics), `docs/SECURITY_AUDIT.md` (the error-sanitization requirement), `docs/ARCHITECTURE_DESIGN.md`, `deployment/MONITORING_USER_SETUP.md` (least-privilege SSH user on monitored hosts).
