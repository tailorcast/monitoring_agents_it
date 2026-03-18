# Security Audit: Credentials & Secrets Leakage

**Date**: 2026-03-12
**Scope**: Full codebase review focused on credentials, secrets, and sensitive data leakage

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 1 | Error messages may leak database connection details to Telegram |
| High | 3 | SSH AutoAddPolicy, missing `.gitignore` entries, unraw exception forwarding |
| Medium | 4 | Sensitive data in logs, infrastructure topology in reports |
| Low | 2 | Minor info disclosure risks |

**Overall**: No secrets are committed to git. Credentials are loaded from environment variables. The main risk area is **exception messages flowing unfiltered into Telegram messages and AI analysis prompts**, which could expose connection strings, hostnames, or internal error details to external services.

---

## Critical

### C1. Unfiltered exception messages sent to Telegram and LLM

`CollectorResult.error` and `CollectorResult.message` fields store raw `str(e)` from caught exceptions. These flow through two external channels:

1. **Telegram** via `report_agent.py` (lines 178-206) — error messages rendered in the report
2. **Bedrock LLM** via `analysis_agent.py` — issues list sent as prompt context for AI analysis

**Affected collectors** (all use `str(e)` in error fields):

| File | Lines | Risk |
|------|-------|------|
| `src/collectors/database_collector.py` | 188-216 | `psycopg2.OperationalError` can include hostname, port, database name, and sometimes partial connection string |
| `src/collectors/ssh_helper.py` | 54-64 | SSH exceptions include hostname, username, key path |
| `src/collectors/api_collector.py` | 160-171 | HTTP errors may include full URL with query params |
| `src/collectors/llm_collector.py` | 143, 218, 320 | Bedrock/Azure errors may include endpoint details |
| `src/collectors/s3_collector.py` | 206, 229 | AWS errors may include bucket ARN, account ID |
| `src/collectors/docker_logs_collector.py` | 126-127 | SSH errors include host IP, compose file path |

**Example**: A PostgreSQL connection failure produces:
```
Connection failed: could not connect to server: Connection refused
    Is the server running on host "database-1.cli88ausay5k.us-west-2.rds.amazonaws.com" (10.0.1.45)
    and accepting TCP/IP connections on port 5432?
```
This full string gets sent to Telegram and to the Bedrock LLM.

**Recommendation**: Sanitize error messages before storing in `CollectorResult`. Create a helper that strips hostnames, IPs, and connection details, keeping only the error type and generic description.

---

## High

### H1. SSH `AutoAddPolicy` accepts any host key

**File**: `src/collectors/ssh_helper.py:37`
```python
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
```

This accepts any SSH host key without verification, making connections vulnerable to man-in-the-middle attacks. An attacker who can intercept network traffic could impersonate a target server and capture commands or their output.

**Recommendation**: Use `paramiko.RejectPolicy()` with a known_hosts file, or at minimum `paramiko.WarningPolicy()` with logged warnings.

### H2. `data/` directory not in `.gitignore`

**File**: `.gitignore` — missing entry

`data/metric_history.json` (configured in `config/config.yaml:10`) stores daily incident counts with metric keys that include collector names and target identifiers. If accidentally committed, it reveals which systems have recurring issues and when.

**Recommendation**: Add `data/` to `.gitignore`.

### H3. `send_error_notification` forwards raw exceptions to Telegram

**File**: `src/services/telegram_client.py:187-210`
```python
error_msg = str(error)
message = f"""**Error Type**: {error_type}
**Message**: {error_msg}"""
```

When the monitoring cycle itself fails, the full exception (which could contain credentials, connection strings, file paths) is sent to Telegram as a notification.

**Recommendation**: Send only the error type and a generic message. Log the full exception server-side only.

---

## Medium

### M1. Debug logs include SSH commands, hostnames, and usernames

**File**: `src/collectors/ssh_helper.py:40,51,89-90`
```python
logger.debug(f"Connecting to {config.host}:{config.port} as {config.username}")
logger.debug(f"Executing command: {command}")
```

At DEBUG level, every SSH command (including `docker compose -f <path> logs`) and connection detail is logged. If logs are shipped to an external service or stored in a shared location, this exposes infrastructure details.

**Recommendation**: Acceptable at DEBUG level for local development. Ensure production runs at INFO or higher. Consider redacting hostnames in structured log fields.

### M2. Full infrastructure topology in Telegram reports

**File**: `src/agents/report_agent.py:178-206`

Reports include target names (server names, database hostnames, API URLs, container names) that map out the entire infrastructure. Anyone with access to the Telegram chat sees the full topology.

**Recommendation**: Acceptable trade-off for operational monitoring. Ensure the Telegram chat is private and restricted to authorized personnel only.

### M3. `exc_info=True` logs full stack traces

**Files**: `src/main.py:94,161,191`, `src/collectors/base.py:113`, `src/workflow.py:423,495`, `src/agents/analysis_agent.py:102`

Full stack traces may include local variable values in frames, which could contain credentials if they were in scope at the time of the exception.

**Recommendation**: Review log shipping configuration. If logs go to an external service, ensure it's access-controlled. Consider using `exc_info=True` only at DEBUG level.

### M4. Database collector logs table query errors with potential SQL details

**File**: `src/collectors/database_collector.py:170-171`
```python
self.logger.warning(f"Failed to query table {config.table}: {e}")
metrics["table_query_error"] = str(e)
```

SQL errors stored in metrics and logged. The `table_query_error` metric value flows into the Telegram report and LLM prompt.

**Recommendation**: Log the error but don't include raw SQL error in `metrics` dict.

---

## Low

### L1. RDS CA certificate bundled in deployment

**File**: `deployment/rds-ca-2019-root.pem` (untracked)

This is a **public** AWS RDS root CA certificate, not a secret. However, it signals the use of RDS and its region, which is minor info disclosure.

**Status**: Acceptable. Public CA certs are not sensitive.

### L2. Budget tracker logs cost details

**File**: `src/services/budget_tracker.py`

Logs daily LLM spending amounts. Not directly a secret, but reveals usage patterns and cost structure.

**Status**: Acceptable for operational monitoring.

---

## Positive Findings

The following security practices are correctly implemented:

| Practice | Location | Status |
|----------|----------|--------|
| `.env` excluded from git | `.gitignore:7` | OK |
| `config/config.yaml` excluded from git | `.gitignore:10` | OK |
| SSH keys excluded from git | `.gitignore:13` (`/secrets/`) | OK |
| No secrets ever committed in git history | `git log --all --diff-filter=A` | OK |
| Credentials loaded from env vars, not hardcoded | `database_collector.py:116-117` | OK |
| SSH key permissions set to 600 in Docker | `deployment/entrypoint.sh:29-32` | OK |
| Docker container runs as non-root | `deployment/Dockerfile:44-46` | OK |
| Database connections use SSL/TLS | `config.yaml` — `ssl_mode: "require"` | OK |
| SQL injection prevented with `quote_ident` | `database_collector.py:164` | OK |
| Telegram token masked in test output | `test_telegram.py:45` | OK |
| Example configs use placeholders, not real values | `config.example.yaml`, `.env.example` | OK |

---

## Remediation Applied (2026-03-13)

The following fixes were implemented:

1. **Created `src/utils/sanitize.py`** — strips IPs, hostnames, ports, file paths, connection strings, and AWS ARNs from error messages before they reach `CollectorResult`
2. **All collectors updated** — every `except` block that sets `CollectorResult.error` or `.message` now uses `sanitize_error(e)` instead of `str(e)`. Full exception details are still logged server-side via `self.logger.error()`
3. **`send_error_notification` in `telegram_client.py`** — no longer sends raw exception message to Telegram; sends only the error type
4. **`database_collector.py`** — `table_query_error` metric now stores only exception class name, not full message
5. **`analysis_agent.py`** — analysis error fallback dict uses sanitized error
6. **Sensitive metrics removed from error paths** — `metrics={"host": ...}` replaced with `metrics={}` in all error-handling branches across collectors
7. **Added `data/` to `.gitignore`**

## Remaining Recommendations

### Short-term

1. **Replace `AutoAddPolicy`** with `WarningPolicy` or a known_hosts file in `ssh_helper.py`

### Medium-term

2. **Ensure production log level is INFO or higher** — document this in deployment guide
3. **Audit Telegram chat access** — ensure only authorized team members have access to the monitoring chat
