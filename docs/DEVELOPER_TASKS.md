# Developer Implementation Tasks
## IT Infrastructure Monitoring AI Agents

**Based on**: ARCHITECTURE_DESIGN.md v1.0
**Target Completion**: 5 weeks
**Developer**: TBD

---

## TASK BREAKDOWN BY SPRINT

---

## SPRINT 1: Core Infrastructure (Week 1)

### Task 1.1: Project Setup
**Priority**: Critical
**Estimated Time**: 2 hours

**Subtasks**:
1. Initialize git repository structure per ARCHITECTURE_DESIGN.md section 2
2. Create directory structure:
   ```bash
   mkdir -p src/{config,collectors,agents,services,utils}
   mkdir -p tests/{test_collectors,test_agents,test_integration}
   mkdir -p deployment config
   ```
3. Create `deployment/requirements.txt`:
   ```
   langgraph>=0.2.0
   langchain>=0.1.0
   langchain-aws>=0.1.0
   boto3>=1.34.0
   paramiko>=3.4.0
   psycopg2-binary>=2.9.0
   httpx>=0.26.0
   python-telegram-bot>=20.8
   pyyaml>=6.0
   pydantic>=2.5.0
   apscheduler>=3.10.0
   python-json-logger>=2.0.7
   pytest>=7.4.0
   pytest-asyncio>=0.21.0
   moto>=4.2.0
   ```
4. Create `.gitignore`:
   ```
   __pycache__/
   *.py[cod]
   .env
   config/config.yaml
   /secrets/
   /tmp/
   .pytest_cache/
   .idea/
   .vscode/
   ```
5. Create `.env.example` with all environment variables from TECHNICAL_REQUIREMENTS.md section 6.2

**Acceptance Criteria**:
- [ ] Directory structure matches architecture design
- [ ] All dependencies install without errors
- [ ] Git repository initialized with proper .gitignore

---

### Task 1.2: Configuration System
**Priority**: Critical
**Estimated Time**: 6 hours

**Subtasks**:
1. Implement `src/config/models.py`:
   - Copy all Pydantic models from ARCHITECTURE_DESIGN.md section 3.1
   - Add validators for:
     - Valid cron syntax in MonitoringConfig
     - Valid URLs in APIEndpointConfig
     - Valid S3 bucket names
     - Positive thresholds

2. Implement `src/config/loader.py`:
   - `ConfigLoader.load_from_file()` method
   - Environment variable substitution logic:
     ```python
     def _substitute_env_vars(self, obj):
         if isinstance(obj, str):
             # Replace ${VAR_NAME} with os.getenv('VAR_NAME')
             import re, os
             pattern = r'\$\{(\w+)\}'
             return re.sub(pattern, lambda m: os.getenv(m.group(1), ''), obj)
         elif isinstance(obj, dict):
             return {k: self._substitute_env_vars(v) for k, v in obj.items()}
         elif isinstance(obj, list):
             return [self._substitute_env_vars(item) for item in obj]
         return obj
     ```
   - YAML loading with error handling

3. Implement `src/config/settings.py`:
   - Load environment variables with defaults
   - Validate required variables are present

4. Create `config/config.example.yaml`:
   - Copy YAML structure from TECHNICAL_REQUIREMENTS.md section 6.1
   - Add comments explaining each section

**Test Cases**:
- Valid config loads successfully
- Missing required field raises ValidationError
- Environment variable substitution works
- Invalid cron syntax rejected

**Acceptance Criteria**:
- [ ] Config loads and validates successfully
- [ ] Environment variables substituted correctly
- [ ] Pydantic validation catches invalid configs
- [ ] Example config file created

---

### Task 1.3: Logging & Utilities
**Priority**: High
**Estimated Time**: 3 hours

**Subtasks**:
1. Implement `src/utils/logger.py`:
   - JSON structured logging setup
   - Per-module logger creation
   - Log level configuration from environment

2. Implement `src/utils/status.py`:
   ```python
   from enum import Enum

   class HealthStatus(Enum):
       GREEN = "green"
       YELLOW = "yellow"
       RED = "red"
       UNKNOWN = "unknown"

       def to_emoji(self) -> str:
           return {
               HealthStatus.GREEN: "🟢",
               HealthStatus.YELLOW: "🟡",
               HealthStatus.RED: "🔴",
               HealthStatus.UNKNOWN: "⚪"
           }[self]
   ```

3. Implement `src/utils/metrics.py`:
   ```python
   from dataclasses import dataclass
   from typing import Optional
   import time

   @dataclass
   class CollectorResult:
       collector_name: str
       target_name: str
       status: HealthStatus
       metrics: dict
       message: str
       error: Optional[str] = None
       timestamp: float = None

       def __post_init__(self):
           if self.timestamp is None:
               self.timestamp = time.time()
   ```

**Acceptance Criteria**:
- [ ] Logger outputs valid JSON to stdout
- [ ] HealthStatus enum with emoji conversion works
- [ ] CollectorResult dataclass defined with proper types

---

### Task 1.4: LangGraph State Definition
**Priority**: High
**Estimated Time**: 2 hours

**Subtasks**:
1. Implement `src/agents/state.py`:
   - Copy `MonitoringState` TypedDict from ARCHITECTURE_DESIGN.md section 3.3
   - Add type annotations for all fields
   - Use `Annotated[int, operator.add]` for cumulative fields

2. Add helper methods:
   ```python
   def get_issue_count(state: MonitoringState) -> dict:
       """Count issues by severity"""
       red = len([r for r in state.get('issues', []) if r.status == HealthStatus.RED])
       yellow = len([r for r in state.get('issues', []) if r.status == HealthStatus.YELLOW])
       return {"red": red, "yellow": yellow}
   ```

**Acceptance Criteria**:
- [ ] MonitoringState TypedDict defined with all required fields
- [ ] Type annotations compatible with LangGraph
- [ ] Helper functions for state queries work

---

## SPRINT 2: Data Collectors (Week 2)

### Task 2.1: Base Collector
**Priority**: Critical
**Estimated Time**: 4 hours

**Subtasks**:
1. Implement `src/collectors/base.py`:
   - Copy `BaseCollector` abstract class from ARCHITECTURE_DESIGN.md section 3.2
   - Implement `_determine_status()` helper:
     ```python
     def _determine_status(self, metric_type: str, value: float,
                           higher_is_worse: bool = True) -> HealthStatus:
         """
         Determine status based on thresholds

         Args:
             metric_type: "cpu", "ram", "disk_free", etc.
             value: Current metric value
             higher_is_worse: True for CPU/RAM, False for disk_free
         """
         red_threshold = self.thresholds.get(f"{metric_type}_red")
         yellow_threshold = self.thresholds.get(f"{metric_type}_yellow")

         if higher_is_worse:
             if value >= red_threshold:
                 return HealthStatus.RED
             elif value >= yellow_threshold:
                 return HealthStatus.YELLOW
             return HealthStatus.GREEN
         else:  # Lower is worse (e.g., disk_free)
             if value <= red_threshold:
                 return HealthStatus.RED
             elif value <= yellow_threshold:
                 return HealthStatus.YELLOW
             return HealthStatus.GREEN
     ```

2. Add error handling decorator:
   ```python
   def safe_collect(func):
       """Decorator to handle collector exceptions"""
       @wraps(func)
       async def wrapper(self, *args, **kwargs):
           try:
               return await func(self, *args, **kwargs)
           except Exception as e:
               self.logger.error(f"Collection failed: {e}", exc_info=True)
               return CollectorResult(
                   collector_name=self.__class__.__name__.lower().replace('collector', ''),
                   target_name="unknown",
                   status=HealthStatus.UNKNOWN,
                   metrics={},
                   message=f"Collection error: {str(e)}",
                   error=str(e)
               )
       return wrapper
   ```

**Acceptance Criteria**:
- [ ] BaseCollector abstract class defined
- [ ] _determine_status() works for all threshold types
- [ ] safe_collect decorator handles errors gracefully

---

### Task 2.2: EC2 Collector
**Priority**: High
**Estimated Time**: 8 hours

**Subtasks**:
1. Implement `src/collectors/ec2_collector.py`:
   - Initialize boto3 CloudWatch and EC2 clients
   - Implement `collect()` method to iterate instances
   - Implement `_collect_instance()` for single instance

2. Implement CloudWatch metric retrieval:
   ```python
   def _get_cloudwatch_metric(self, instance_id: str, metric_name: str,
                               namespace: str = "AWS/EC2",
                               statistic: str = "Average",
                               period: int = 300) -> float:
       """Get latest CloudWatch metric value"""
       from datetime import datetime, timedelta

       response = self.cloudwatch.get_metric_statistics(
           Namespace=namespace,
           MetricName=metric_name,
           Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
           StartTime=datetime.utcnow() - timedelta(minutes=10),
           EndTime=datetime.utcnow(),
           Period=period,
           Statistics=[statistic]
       )

       datapoints = response.get('Datapoints', [])
       if not datapoints:
           raise ValueError(f"No data for {metric_name}")

       # Get most recent datapoint
       latest = sorted(datapoints, key=lambda x: x['Timestamp'])[-1]
       return latest[statistic]
   ```

3. Handle metrics:
   - CPU: `CPUUtilization` (AWS/EC2)
   - Memory: Requires CloudWatch agent - handle gracefully if missing
   - Disk: Query EBS volumes or use CloudWatch agent

4. Implement status determination:
   ```python
   def _determine_overall_status(self, cpu: float, ram: float, disk_free: float) -> HealthStatus:
       """Worst status wins"""
       statuses = [
           self._determine_status("cpu", cpu),
           self._determine_status("ram", ram),
           self._determine_status("disk_free", disk_free, higher_is_worse=False)
       ]

       if HealthStatus.RED in statuses:
           return HealthStatus.RED
       elif HealthStatus.YELLOW in statuses:
           return HealthStatus.YELLOW
       return HealthStatus.GREEN
   ```

**Test Cases**:
- Mock CloudWatch responses with `moto`
- Test missing metrics (no CloudWatch agent)
- Test threshold determination
- Test multiple instances

**Acceptance Criteria**:
- [ ] Collects CPU, RAM, disk for all configured EC2 instances
- [ ] Handles missing CloudWatch agent metrics gracefully
- [ ] Returns proper CollectorResult for each instance
- [ ] Unit tests pass with mocked AWS

---

### Task 2.3: VPS Collector (SSH)
**Priority**: High
**Estimated Time**: 6 hours

**Subtasks**:
1. Implement `src/collectors/vps_collector.py`:
   - Use paramiko for SSH connections
   - Execute commands: `top -bn1`, `df -h`, `free -m`
   - Parse command outputs

2. Implement SSH connection helper:
   ```python
   def _create_ssh_client(self, config: VPSServerConfig) -> paramiko.SSHClient:
       """Create SSH client with key authentication"""
       client = paramiko.SSHClient()
       client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

       client.connect(
           hostname=config.host,
           port=config.port,
           username=config.username,
           key_filename=config.ssh_key_path,
           timeout=10
       )
       return client

   def _exec_command(self, client: paramiko.SSHClient, command: str) -> str:
       """Execute command and return stdout"""
       stdin, stdout, stderr = client.exec_command(command)
       exit_code = stdout.channel.recv_exit_status()

       if exit_code != 0:
           raise RuntimeError(f"Command failed: {stderr.read().decode()}")

       return stdout.read().decode()
   ```

3. Implement output parsers:
   ```python
   def _parse_cpu(self, top_output: str) -> float:
       """Parse CPU from top command"""
       # Example: %Cpu(s):  5.2 us,  2.1 sy
       import re
       match = re.search(r'%Cpu\(s\):\s+(\d+\.?\d*)\s+us', top_output)
       if match:
           return float(match.group(1))
       raise ValueError("Cannot parse CPU")

   def _parse_memory(self, free_output: str) -> float:
       """Parse memory usage percentage from free -m"""
       lines = free_output.strip().split('\n')
       mem_line = lines[1]  # Second line is memory
       parts = mem_line.split()
       total = float(parts[1])
       used = float(parts[2])
       return (used / total) * 100

   def _parse_disk(self, df_output: str) -> float:
       """Parse root partition free space percentage"""
       lines = df_output.strip().split('\n')[1:]  # Skip header
       for line in lines:
           if line.endswith('/'):  # Root partition
               parts = line.split()
               use_percent = parts[4].rstrip('%')
               return 100 - float(use_percent)
       raise ValueError("Cannot find root partition")
   ```

**Test Cases**:
- Mock SSH command outputs
- Test parser functions with real command outputs
- Test SSH connection failure handling
- Test command timeout

**Acceptance Criteria**:
- [ ] SSH connection established with key auth
- [ ] CPU, RAM, disk metrics extracted correctly
- [ ] Handles SSH failures gracefully
- [ ] Unit tests with mocked paramiko

---

### Task 2.4: Docker Collector
**Priority**: High
**Estimated Time**: 6 hours

**Subtasks**:
1. Implement `src/collectors/docker_collector.py`:
   - Use SSH to connect to servers (reuse VPS logic)
   - Execute `docker ps -a --format json`
   - Parse container statuses

2. Implement container discovery:
   ```python
   async def _discover_containers(self, ssh_client: paramiko.SSHClient) -> List[dict]:
       """Get all containers from docker ps -a"""
       output = self._exec_command(ssh_client, 'docker ps -a --format "{{json .}}"')

       containers = []
       for line in output.strip().split('\n'):
           if line:
               containers.append(json.loads(line))
       return containers
   ```

3. Implement status determination:
   ```python
   def _determine_container_status(self, container: dict) -> tuple[HealthStatus, str]:
       """
       Determine health status from container info

       Container dict keys: ID, Image, Command, CreatedAt, Status, Names, State
       """
       state = container['State']
       status = container['Status']

       if state == 'running':
           # Check if health check is available
           if 'healthy' in status.lower():
               return HealthStatus.GREEN, f"Running (healthy)"
           elif 'unhealthy' in status.lower():
               return HealthStatus.RED, f"Running but unhealthy"
           else:
               return HealthStatus.GREEN, f"Running"

       elif state in ['exited', 'dead']:
           # Check exit code in status
           if 'Exited (0)' in status:
               return HealthStatus.YELLOW, f"Stopped cleanly"
           else:
               return HealthStatus.RED, f"Stopped with error: {status}"

       elif state == 'restarting':
           return HealthStatus.YELLOW, f"Restarting"

       else:
           return HealthStatus.UNKNOWN, f"Unknown state: {state}"
   ```

4. Group results by server:
   ```python
   async def collect(self) -> List[CollectorResult]:
       """Collect from all configured servers"""
       results = []

       for server_config in self.config:
           ssh_client = self._create_ssh_client(server_config)
           containers = await self._discover_containers(ssh_client)

           for container in containers:
               status, message = self._determine_container_status(container)

               results.append(CollectorResult(
                   collector_name="docker",
                   target_name=f"{server_config.name}/{container['Names']}",
                   status=status,
                   metrics={
                       "state": container['State'],
                       "image": container['Image'],
                       "created": container['CreatedAt']
                   },
                   message=message
               ))

           ssh_client.close()

       return results
   ```

**Acceptance Criteria**:
- [ ] Discovers all containers on configured servers
- [ ] Correctly identifies running/stopped/unhealthy containers
- [ ] Handles servers without Docker gracefully
- [ ] Returns one CollectorResult per container

---

### Task 2.5: API Collector
**Priority**: High
**Estimated Time**: 4 hours

**Subtasks**:
1. Implement `src/collectors/api_collector.py`:
   - Use `httpx.AsyncClient` for concurrent checks
   - Measure response time
   - Handle timeouts

2. Implement API check:
   ```python
   async def _check_endpoint(self, config: APIEndpointConfig) -> CollectorResult:
       """Check single API endpoint"""
       import httpx
       import time

       start_time = time.time()

       try:
           async with httpx.AsyncClient() as client:
               response = await client.get(
                   config.url,
                   timeout=config.timeout_ms / 1000.0,
                   follow_redirects=True
               )

           response_time_ms = (time.time() - start_time) * 1000

           # Determine status
           if response.status_code != 200:
               status = HealthStatus.RED
               message = f"HTTP {response.status_code}"
           elif response_time_ms > self.thresholds.api_timeout_ms:
               status = HealthStatus.RED
               message = f"Timeout ({response_time_ms:.0f}ms)"
           elif response_time_ms > self.thresholds.api_slow_ms:
               status = HealthStatus.YELLOW
               message = f"Slow ({response_time_ms:.0f}ms)"
           else:
               status = HealthStatus.GREEN
               message = f"OK ({response_time_ms:.0f}ms)"

           return CollectorResult(
               collector_name="api",
               target_name=config.name,
               status=status,
               metrics={
                   "status_code": response.status_code,
                   "response_time_ms": response_time_ms,
                   "url": config.url
               },
               message=message
           )

       except httpx.TimeoutException:
           return CollectorResult(
               collector_name="api",
               target_name=config.name,
               status=HealthStatus.RED,
               metrics={"url": config.url},
               message="Request timeout",
               error="TimeoutException"
           )
   ```

3. Implement concurrent collection:
   ```python
   async def collect(self) -> List[CollectorResult]:
       """Check all endpoints concurrently"""
       tasks = [self._check_endpoint(config) for config in self.config]
       results = await asyncio.gather(*tasks, return_exceptions=True)

       # Handle exceptions
       final_results = []
       for result in results:
           if isinstance(result, Exception):
               # Create error result
               final_results.append(CollectorResult(
                   collector_name="api",
                   target_name="unknown",
                   status=HealthStatus.UNKNOWN,
                   metrics={},
                   message=str(result),
                   error=str(result)
               ))
           else:
               final_results.append(result)

       return final_results
   ```

**Acceptance Criteria**:
- [ ] Checks all 50 endpoints concurrently
- [ ] Measures response time accurately
- [ ] Handles timeouts and non-200 responses
- [ ] Returns proper status based on thresholds

---

### Task 2.6: Database Collector
**Priority**: Medium
**Estimated Time**: 3 hours

**Subtasks**:
1. Implement `src/collectors/database_collector.py`:
   - Use `psycopg2` to connect
   - Test connection
   - Optional: query table stats

2. Implement connection check:
   ```python
   async def _check_database(self, config: DatabaseConfig) -> CollectorResult:
       """Check PostgreSQL connectivity"""
       import psycopg2

       try:
           conn = psycopg2.connect(
               host=config.host,
               port=config.port,
               database=config.database,
               user=os.getenv('POSTGRES_USER'),
               password=os.getenv('POSTGRES_PASSWORD'),
               sslmode=config.ssl_mode,
               connect_timeout=10
           )

           cursor = conn.cursor()
           cursor.execute("SELECT version();")
           version = cursor.fetchone()[0]

           # Optional: query table if specified
           metrics = {"version": version}
           if config.table:
               cursor.execute(f"SELECT COUNT(*) FROM {config.table};")
               count = cursor.fetchone()[0]
               metrics["row_count"] = count

           cursor.close()
           conn.close()

           return CollectorResult(
               collector_name="database",
               target_name=f"{config.host}/{config.database}",
               status=HealthStatus.GREEN,
               metrics=metrics,
               message="Connected successfully"
           )

       except Exception as e:
           return CollectorResult(
               collector_name="database",
               target_name=f"{config.host}/{config.database}",
               status=HealthStatus.RED,
               metrics={},
               message=f"Connection failed: {str(e)}",
               error=str(e)
           )
   ```

**Acceptance Criteria**:
- [ ] Connects to PostgreSQL successfully
- [ ] Handles connection failures
- [ ] Queries table stats if configured
- [ ] Returns GREEN/RED status

---

### Task 2.7: LLM Collector
**Priority**: Medium
**Estimated Time**: 4 hours

**Subtasks**:
1. Implement `src/collectors/llm_collector.py`:
   - Check Azure OpenAI availability
   - Check Amazon Bedrock availability
   - Use minimal inference request

2. Implement Bedrock check:
   ```python
   async def _check_bedrock(self, config: LLMModelConfig) -> CollectorResult:
       """Check Bedrock model availability"""
       import boto3
       import json

       try:
           client = boto3.client('bedrock-runtime', region_name='us-east-1')

           # Minimal test request
           response = client.invoke_model(
               modelId=config.model_id,
               body=json.dumps({
                   "anthropic_version": "bedrock-2023-05-31",
                   "max_tokens": 10,
                   "messages": [{"role": "user", "content": "test"}]
               })
           )

           return CollectorResult(
               collector_name="llm",
               target_name=f"Bedrock/{config.model_id}",
               status=HealthStatus.GREEN,
               metrics={"model_id": config.model_id},
               message="Model accessible"
           )

       except Exception as e:
           return CollectorResult(
               collector_name="llm",
               target_name=f"Bedrock/{config.model_id}",
               status=HealthStatus.RED,
               metrics={},
               message=f"Unavailable: {str(e)}",
               error=str(e)
           )
   ```

3. Implement Azure check (similar pattern)

**Acceptance Criteria**:
- [ ] Checks Bedrock model availability
- [ ] Checks Azure model availability
- [ ] Minimal token usage (<100 tokens)
- [ ] Returns GREEN/RED status

---

### Task 2.8: S3 Collector
**Priority**: Medium
**Estimated Time**: 6 hours

**Subtasks**:
1. Implement `src/collectors/s3_collector.py`:
   - List objects in bucket
   - Group by creation date (today, this week, this month)
   - Compare with previous periods

2. Implement S3 statistics:
   ```python
   async def _collect_bucket_stats(self, config: S3BucketConfig) -> CollectorResult:
       """Collect S3 bucket statistics"""
       import boto3
       from datetime import datetime, timedelta

       s3 = boto3.client('s3', region_name=config.region)

       now = datetime.utcnow()
       today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
       yesterday_start = today_start - timedelta(days=1)
       week_start = today_start - timedelta(days=7)
       last_week_start = week_start - timedelta(days=7)
       month_start = today_start - timedelta(days=30)
       last_month_start = month_start - timedelta(days=30)

       # List all objects (paginate if needed)
       paginator = s3.get_paginator('list_objects_v2')
       pages = paginator.paginate(Bucket=config.bucket)

       counts = {
           'today': 0, 'yesterday': 0,
           'this_week': 0, 'last_week': 0,
           'this_month': 0, 'last_month': 0
       }
       total_size = 0

       for page in pages:
           for obj in page.get('Contents', []):
               last_modified = obj['LastModified']
               size = obj['Size']
               total_size += size

               if last_modified >= today_start:
                   counts['today'] += 1
               elif last_modified >= yesterday_start:
                   counts['yesterday'] += 1

               if last_modified >= week_start:
                   counts['this_week'] += 1
               elif last_modified >= last_week_start:
                   counts['last_week'] += 1

               if last_modified >= month_start:
                   counts['this_month'] += 1
               elif last_modified >= last_month_start:
                   counts['last_month'] += 1

       # Calculate trends
       daily_change = self._calculate_change_percent(counts['today'], counts['yesterday'])
       weekly_change = self._calculate_change_percent(counts['this_week'], counts['last_week'])
       monthly_change = self._calculate_change_percent(counts['this_month'], counts['last_month'])

       # Determine status
       worst_change = min(daily_change, weekly_change, monthly_change)
       if worst_change < -50:
           status = HealthStatus.RED
       elif worst_change < -25:
           status = HealthStatus.YELLOW
       else:
           status = HealthStatus.GREEN

       return CollectorResult(
           collector_name="s3",
           target_name=config.bucket,
           status=status,
           metrics={
               'total_size_gb': total_size / (1024**3),
               'files_today': counts['today'],
               'files_yesterday': counts['yesterday'],
               'daily_change_pct': daily_change,
               'weekly_change_pct': weekly_change,
               'monthly_change_pct': monthly_change
           },
           message=f"Total: {total_size/(1024**3):.2f} GB, Daily change: {daily_change:+.1f}%"
       )

   def _calculate_change_percent(self, current: int, previous: int) -> float:
       """Calculate percentage change"""
       if previous == 0:
           return 0.0 if current == 0 else 100.0
       return ((current - previous) / previous) * 100
   ```

**Acceptance Criteria**:
- [ ] Lists all objects in bucket
- [ ] Calculates daily/weekly/monthly trends
- [ ] Determines status based on change thresholds
- [ ] Handles large buckets with pagination

---

## SPRINT 3: AI Agents & LangGraph (Week 3)

### Task 3.1: Bedrock Client
**Priority**: Critical
**Estimated Time**: 4 hours

**Subtasks**:
1. Implement `src/services/bedrock_client.py`:
   - Copy implementation from ARCHITECTURE_DESIGN.md section 3.4
   - Add error handling for throttling
   - Support streaming (optional for future)

2. Add token counting:
   ```python
   async def invoke(self, prompt: str, system_prompt: str = None) -> Tuple[str, dict]:
       """
       Invoke Claude and return (response, token_usage_dict)

       Returns:
           response: String response from model
           usage: {"input_tokens": int, "output_tokens": int, "total_tokens": int}
       """
       # Implementation from architecture doc
       pass
   ```

**Test Cases**:
- Mock Bedrock API responses
- Test token counting accuracy
- Test error handling (throttling, invalid requests)

**Acceptance Criteria**:
- [ ] Invokes Bedrock successfully
- [ ] Returns token usage accurately
- [ ] Handles API errors gracefully

---

### Task 3.2: Budget Tracker
**Priority**: Critical
**Estimated Time**: 3 hours

**Subtasks**:
1. Implement `src/services/budget_tracker.py`:
   - Copy implementation from ARCHITECTURE_DESIGN.md section 3.4
   - Persist state to file
   - Reset daily

2. Add budget alerts:
   ```python
   def get_budget_status(self) -> dict:
       """Return budget utilization info"""
       return {
           "daily_limit": self.daily_budget,
           "spent_today": self.today_spent,
           "remaining": self.daily_budget - self.today_spent,
           "utilization_pct": (self.today_spent / self.daily_budget) * 100
       }

   def should_alert_budget(self, threshold: float = 0.8) -> bool:
       """Alert if budget utilization exceeds threshold"""
       return self.today_spent >= (self.daily_budget * threshold)
   ```

**Acceptance Criteria**:
- [ ] Tracks token costs accurately
- [ ] Blocks requests when budget exceeded
- [ ] Resets daily at midnight
- [ ] Persists state across restarts

---

### Task 3.3: Retry Handler
**Priority**: High
**Estimated Time**: 2 hours

**Subtasks**:
1. Implement `src/services/retry_handler.py`:
   - Copy implementation from ARCHITECTURE_DESIGN.md section 5
   - Add jitter to backoff
   - Support max attempts configuration

2. Add retry decorator:
   ```python
   def with_retry(max_attempts=3, base_delay=1.0, exceptions=(Exception,)):
       """Decorator for automatic retry with exponential backoff"""
       def decorator(func):
           @wraps(func)
           async def wrapper(*args, **kwargs):
               return await RetryHandler.with_retry(
                   lambda: func(*args, **kwargs),
                   max_attempts=max_attempts,
                   base_delay=base_delay,
                   exceptions=exceptions
               )
           return wrapper
       return decorator
   ```

**Acceptance Criteria**:
- [ ] Retries failed operations up to max_attempts
- [ ] Uses exponential backoff with jitter
- [ ] Only retries specified exception types

---

### Task 3.4: Analysis Agent
**Priority**: Critical
**Estimated Time**: 8 hours

**Subtasks**:
1. Implement `src/agents/analysis_agent.py`:
   - Root cause analysis logic
   - Issue correlation
   - Recommendation generation

2. Implement analysis prompt builder:
   ```python
   class AnalysisAgent:
       def __init__(self, bedrock_client: BedrockClient, budget_tracker: BudgetTracker):
           self.bedrock = bedrock_client
           self.budget = budget_tracker

       async def analyze(self, issues: List[CollectorResult]) -> dict:
           """Perform root cause analysis"""

           if not issues:
               return {
                   "root_cause": "No issues detected",
                   "recommendations": [],
                   "token_usage": {}
               }

           # Check budget
           if not self.budget.can_make_request():
               return {
                   "root_cause": "Budget exceeded - analysis skipped",
                   "recommendations": ["Increase daily budget or optimize prompts"],
                   "token_usage": {}
               }

           # Build prompt
           prompt = self._build_analysis_prompt(issues)
           system_prompt = """You are an expert Site Reliability Engineer analyzing infrastructure issues.
Your job is to:
1. Identify root causes by correlating related issues
2. Prioritize issues by severity and impact
3. Provide specific, actionable remediation steps

Be concise and practical. Output valid JSON only."""

           # Call LLM
           response, usage = await self.bedrock.invoke(prompt, system_prompt)
           self.budget.record_usage(usage['input_tokens'], usage['output_tokens'])

           # Parse response
           analysis = self._parse_analysis_response(response)
           analysis['token_usage'] = usage

           return analysis

       def _build_analysis_prompt(self, issues: List[CollectorResult]) -> str:
           """Build structured prompt from issues"""

           prompt = "Infrastructure issues detected:\n\n"

           # Group by collector type
           by_type = {}
           for issue in issues:
               by_type.setdefault(issue.collector_name, []).append(issue)

           # Format each group
           for collector, items in by_type.items():
               prompt += f"## {collector.upper()}\n"
               for item in items:
                   prompt += f"- **{item.target_name}** [{item.status.value}]: {item.message}\n"
                   if item.metrics:
                       prompt += f"  Metrics: {json.dumps(item.metrics, indent=2)}\n"
               prompt += "\n"

           prompt += """
Analyze and respond in JSON format:
{
  "root_cause": "Brief description of underlying cause (correlate related issues)",
  "severity": "critical|high|medium|low",
  "affected_systems": ["system1", "system2"],
  "recommendations": [
    {
      "priority": "immediate|high|medium|low",
      "action": "Specific remediation step",
      "rationale": "Why this will help"
    }
  ]
}
"""
           return prompt

       def _parse_analysis_response(self, response: str) -> dict:
           """Parse LLM JSON response"""
           try:
               # Extract JSON from response (may have markdown code blocks)
               import re
               json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
               if json_match:
                   json_str = json_match.group(1)
               else:
                   json_str = response

               return json.loads(json_str)
           except Exception as e:
               logger.error(f"Failed to parse analysis response: {e}")
               return {
                   "root_cause": "Analysis parsing failed",
                   "recommendations": [{"priority": "high", "action": "Manual investigation required"}]
               }
   ```

**Test Cases**:
- Mock Bedrock responses
- Test issue correlation logic
- Test budget check before analysis
- Test JSON parsing with various formats

**Acceptance Criteria**:
- [ ] Generates structured analysis from issues
- [ ] Correlates related issues
- [ ] Checks budget before LLM call
- [ ] Parses LLM response reliably

---

### Task 3.5: Report Generation Agent
**Priority**: High
**Estimated Time**: 6 hours

**Subtasks**:
1. Implement `src/agents/report_agent.py`:
   - Format Telegram message
   - Add emojis and structure
   - Include analysis results

2. Implement report formatter:
   ```python
   class ReportAgent:
       def __init__(self, bedrock_client: BedrockClient):
           self.bedrock = bedrock_client

       async def generate_report(self, state: MonitoringState) -> str:
           """Generate formatted Telegram report"""

           all_results = state['all_results']
           issues = state['issues']
           analysis = state.get('root_cause_analysis', 'No analysis available')
           recommendations = state.get('recommendations', [])

           # Build report sections
           report = self._build_header(all_results, issues)
           report += "\n" + self._build_summary_section(all_results)

           if issues:
               report += "\n" + self._build_issues_section(issues)
               report += "\n" + self._build_analysis_section(analysis, recommendations)

           report += "\n" + self._build_footer(state)

           return report

       def _build_header(self, all_results: List[CollectorResult], issues: List[CollectorResult]) -> str:
           """Build report header with overall status"""
           from datetime import datetime

           total = len(all_results)
           passed = total - len(issues)
           red_count = len([i for i in issues if i.status == HealthStatus.RED])
           yellow_count = len([i for i in issues if i.status == HealthStatus.YELLOW])

           if red_count > 0:
               overall_emoji = "🔴"
               overall_status = "Critical Issues"
           elif yellow_count > 0:
               overall_emoji = "🟡"
               overall_status = "Warnings"
           else:
               overall_emoji = "🟢"
               overall_status = "Healthy"

           header = f"""{overall_emoji} **Infrastructure Health Report**
{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

📊 **Overall Status**: {overall_status}
✅ {passed}/{total} checks passed
"""
           if red_count > 0:
               header += f"🔴 {red_count} critical issue(s)\n"
           if yellow_count > 0:
               header += f"🟡 {yellow_count} warning(s)\n"

           header += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
           return header

       def _build_summary_section(self, all_results: List[CollectorResult]) -> str:
           """Build summary by collector type"""
           by_type = {}
           for result in all_results:
               by_type.setdefault(result.collector_name, []).append(result)

           summary = ""
           for collector, results in sorted(by_type.items()):
               issues = [r for r in results if r.status != HealthStatus.GREEN]
               passed = len(results) - len(issues)

               if issues:
                   status_emoji = min(issues, key=lambda x: ['green', 'yellow', 'red'].index(x.status.value)).status.to_emoji()
               else:
                   status_emoji = "🟢"

               summary += f"{status_emoji} **{collector.upper()}**: {passed}/{len(results)} healthy\n"

           return summary

       def _build_issues_section(self, issues: List[CollectorResult]) -> str:
           """Build detailed issues section"""
           section = "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
           section += "## 🚨 Issues Detected\n\n"

           # Group by severity
           red_issues = [i for i in issues if i.status == HealthStatus.RED]
           yellow_issues = [i for i in issues if i.status == HealthStatus.YELLOW]

           if red_issues:
               section += "### 🔴 Critical\n"
               for issue in red_issues:
                   section += f"**{issue.target_name}** ({issue.collector_name})\n"
                   section += f"└─ {issue.message}\n"
                   if issue.metrics:
                       section += f"   Metrics: {self._format_metrics(issue.metrics)}\n"
                   section += "\n"

           if yellow_issues:
               section += "### 🟡 Warnings\n"
               for issue in yellow_issues:
                   section += f"**{issue.target_name}** ({issue.collector_name})\n"
                   section += f"└─ {issue.message}\n\n"

           return section

       def _build_analysis_section(self, analysis: str, recommendations: list) -> str:
           """Build AI analysis section"""
           section = "━━━━━━━━━━━━━━━━━━━━━━━━\n"
           section += "## 🤖 AI Analysis\n\n"

           if isinstance(analysis, dict):
               section += f"**Root Cause**: {analysis.get('root_cause', 'Unknown')}\n\n"

               if recommendations := analysis.get('recommendations', []):
                   section += "**Recommended Actions**:\n"
                   for i, rec in enumerate(recommendations, 1):
                       priority = rec.get('priority', 'medium')
                       action = rec.get('action', 'No action specified')
                       section += f"{i}. [{priority.upper()}] {action}\n"
           else:
               section += f"{analysis}\n"

           return section

       def _build_footer(self, state: MonitoringState) -> str:
           """Build footer with metadata"""
           duration = time.time() - state.get('execution_start', time.time())
           tokens = state.get('token_usage', 0)

           footer = f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
           footer += f"⏱ Execution time: {duration:.1f}s\n"
           footer += f"🔤 LLM tokens used: {tokens}\n"

           return footer

       def _format_metrics(self, metrics: dict) -> str:
           """Format metrics dict for display"""
           items = [f"{k}={v}" for k, v in metrics.items()]
           return ", ".join(items[:3])  # Limit to 3 metrics
   ```

**Acceptance Criteria**:
- [ ] Generates well-formatted Telegram message
- [ ] Includes all sections (header, summary, issues, analysis)
- [ ] Uses emojis appropriately
- [ ] Handles missing data gracefully

---

### Task 3.6: LangGraph Workflow Integration
**Priority**: Critical
**Estimated Time**: 8 hours

**Subtasks**:
1. Implement `src/agents/workflow.py`:
   - Copy workflow from ARCHITECTURE_DESIGN.md section 3.3
   - Wire up all collector nodes
   - Wire up analysis and report nodes

2. Implement workflow nodes:
   ```python
   # Each collector node
   async def _collect_ec2(self, state: MonitoringState) -> dict:
       results = await self.collectors["ec2"].collect()
       return {"ec2_results": results}

   # Aggregation node (with parallel collection)
   async def _aggregate_results(self, state: MonitoringState) -> dict:
       import asyncio

       # Run all collectors in parallel
       collector_tasks = [collector.collect() for collector in self.collectors.values()]
       results = await asyncio.gather(*collector_tasks, return_exceptions=True)

       # Flatten results
       all_results = []
       for result in results:
           if isinstance(result, Exception):
               self.logger.error(f"Collector failed: {result}")
               continue
           all_results.extend(result)

       issues = [r for r in all_results if r.status in [HealthStatus.RED, HealthStatus.YELLOW]]

       return {"all_results": all_results, "issues": issues}

   # Analysis node
   async def _ai_analysis(self, state: MonitoringState) -> dict:
       analysis_result = await self.analysis_agent.analyze(state['issues'])
       return {
           "root_cause_analysis": analysis_result,
           "recommendations": analysis_result.get('recommendations', []),
           "token_usage": analysis_result.get('token_usage', {}).get('total_tokens', 0)
       }

   # Report generation node
   async def _generate_report(self, state: MonitoringState) -> dict:
       report = await self.report_agent.generate_report(state)
       return {"telegram_message": report}
   ```

3. Configure workflow execution:
   ```python
   # In _build_graph()
   from langgraph.graph import StateGraph, END

   workflow = StateGraph(MonitoringState)

   # Add processing nodes only (collectors called within aggregate)
   workflow.add_node("aggregate", self._aggregate_results)
   workflow.add_node("analyze", self._ai_analysis)
   workflow.add_node("generate_report", self._generate_report)
   workflow.add_node("send_telegram", self._send_telegram)

   # Set entry point
   workflow.set_entry_point("aggregate")

   # Sequential processing
   workflow.add_edge("aggregate", "analyze")
   workflow.add_edge("analyze", "generate_report")
   workflow.add_edge("generate_report", "send_telegram")
   workflow.add_edge("send_telegram", END)

   return workflow.compile()
   ```

   **Note**: Parallel collection happens inside the `_aggregate_results` node using `asyncio.gather()`,
   not through LangGraph parallel edges. This is simpler and more reliable.

**Test Cases**:
- Test workflow execution with mocked collectors
- Test parallel collection
- Test state propagation through nodes
- Integration test with real collectors

**Acceptance Criteria**:
- [ ] LangGraph workflow compiles successfully
- [ ] All collectors execute in parallel within aggregate node
- [ ] State propagates correctly through workflow
- [ ] Workflow completes end-to-end
- [ ] Error handling works for failed collectors

---

## SPRINT 4: Integration & Delivery (Week 4)

### Task 4.1: Telegram Client
**Priority**: High
**Estimated Time**: 4 hours

**Subtasks**:
1. Implement `src/services/telegram_client.py`:
   ```python
   from telegram import Bot
   from telegram.constants import ParseMode

   class TelegramClient:
       def __init__(self, config: TelegramConfig):
           self.bot = Bot(token=config.bot_token)
           self.chat_id = config.chat_id

       async def send_message(self, message: str, parse_mode: str = ParseMode.MARKDOWN) -> bool:
           """Send message to Telegram chat"""
           try:
               # Telegram has 4096 char limit per message
               if len(message) > 4096:
                   # Split into multiple messages
                   await self._send_long_message(message, parse_mode)
               else:
                   await self.bot.send_message(
                       chat_id=self.chat_id,
                       text=message,
                       parse_mode=parse_mode
                   )
               return True

           except Exception as e:
               logger.error(f"Telegram send failed: {e}", exc_info=True)
               return False

       async def _send_long_message(self, message: str, parse_mode: str):
           """Split and send long messages"""
           chunks = self._split_message(message, max_length=4000)
           for i, chunk in enumerate(chunks):
               if i > 0:
                   await asyncio.sleep(1)  # Rate limit
               await self.bot.send_message(
                   chat_id=self.chat_id,
                   text=chunk,
                   parse_mode=parse_mode
               )

       def _split_message(self, message: str, max_length: int) -> List[str]:
           """Split message at logical boundaries"""
           if len(message) <= max_length:
               return [message]

           chunks = []
           current_chunk = ""

           for line in message.split('\n'):
               if len(current_chunk) + len(line) + 1 > max_length:
                   chunks.append(current_chunk)
                   current_chunk = line
               else:
                   current_chunk += '\n' + line if current_chunk else line

           if current_chunk:
               chunks.append(current_chunk)

           return chunks
   ```

2. Add retry logic:
   ```python
   @with_retry(max_attempts=3, base_delay=2.0, exceptions=(telegram.error.TelegramError,))
   async def send_message(self, message: str, parse_mode: str = ParseMode.MARKDOWN) -> bool:
       # Implementation above
       pass
   ```

**Test Cases**:
- Mock Telegram API
- Test message splitting for long messages
- Test retry on failure
- Test markdown formatting

**Acceptance Criteria**:
- [ ] Sends messages successfully
- [ ] Handles messages >4096 chars
- [ ] Retries on failure
- [ ] Supports Markdown formatting

---

### Task 4.2: Main Application Entry Point
**Priority**: Critical
**Estimated Time**: 4 hours

**Subtasks**:
1. Implement `src/main.py`:
   - Copy implementation from ARCHITECTURE_DESIGN.md section 3.5
   - Add scheduler logic
   - Add CLI argument parsing

2. Add scheduler:
   ```python
   from apscheduler.schedulers.asyncio import AsyncIOScheduler
   from apscheduler.triggers.cron import CronTrigger

   def start_scheduler(self):
       """Start scheduled monitoring with APScheduler"""
       scheduler = AsyncIOScheduler()

       # Parse cron from config
       cron_parts = self.config.monitoring.schedule.split()
       trigger = CronTrigger(
           minute=cron_parts[0],
           hour=cron_parts[1],
           day=cron_parts[2],
           month=cron_parts[3],
           day_of_week=cron_parts[4]
       )

       scheduler.add_job(
           self.run_monitoring_cycle,
           trigger=trigger,
           id='monitoring_cycle'
       )

       scheduler.start()
       logger.info(f"Scheduler started: {self.config.monitoring.schedule}")

       # Keep running
       try:
           asyncio.get_event_loop().run_forever()
       except KeyboardInterrupt:
           scheduler.shutdown()
   ```

3. Add CLI arguments:
   ```python
   import argparse

   def main():
       parser = argparse.ArgumentParser(description='Infrastructure Monitoring Agent')
       parser.add_argument('--config', default='config/config.yaml', help='Config file path')
       parser.add_argument('--run-once', action='store_true', help='Run once and exit')
       parser.add_argument('--dry-run', action='store_true', help='Run without sending Telegram')

       args = parser.parse_args()

       app = MonitoringApp(config_path=args.config, dry_run=args.dry_run)

       if args.run_once:
           asyncio.run(app.run_monitoring_cycle())
       else:
           app.start_scheduler()
   ```

**Acceptance Criteria**:
- [ ] Scheduler runs monitoring at configured intervals
- [ ] CLI supports --run-once for testing
- [ ] CLI supports --dry-run to skip Telegram
- [ ] Graceful shutdown on SIGTERM/SIGINT

---

### Task 4.3: Docker Build
**Priority**: High
**Estimated Time**: 3 hours

**Subtasks**:
1. Create `deployment/Dockerfile`:
   - Copy from ARCHITECTURE_DESIGN.md section 4.1
   - Optimize layers for caching
   - Add health check

2. Create `deployment/docker-compose.yml`:
   - Copy from ARCHITECTURE_DESIGN.md section 4.1
   - Add volume mounts
   - Configure logging

3. Create `deployment/entrypoint.sh`:
   ```bash
   #!/bin/bash
   set -e

   # Wait for network to be ready
   sleep 5

   # Run application
   exec python -m src.main "$@"
   ```

4. Test Docker build:
   ```bash
   cd deployment
   docker-compose build
   docker-compose up -d
   docker-compose logs -f
   ```

**Acceptance Criteria**:
- [ ] Docker image builds successfully
- [ ] Container starts and runs monitoring
- [ ] Logs visible via docker-compose logs
- [ ] Environment variables passed correctly

---

### Task 4.4: Configuration Examples
**Priority**: Medium
**Estimated Time**: 2 hours

**Subtasks**:
1. Create `config/config.example.yaml`:
   - Full example with comments
   - Placeholder values for all sections
   - Instructions for customization

2. Create `.env.example`:
   - All required environment variables
   - Comments explaining each variable

3. Update `README.md`:
   - Installation instructions
   - Configuration guide
   - Usage examples
   - Troubleshooting section

**Acceptance Criteria**:
- [ ] Example config covers all features
- [ ] Example .env includes all variables
- [ ] README has clear setup instructions

---

### Task 4.5: Error Handling & Logging
**Priority**: High
**Estimated Time**: 4 hours

**Subtasks**:
1. Add global error handler in `src/main.py`:
   ```python
   async def run_monitoring_cycle(self):
       try:
           logger.info("Starting monitoring cycle")
           start_time = time.time()

           final_state = await self.workflow.run()

           duration = time.time() - start_time
           logger.info(f"Cycle completed", extra={
               "duration_seconds": duration,
               "token_usage": final_state.get('token_usage', 0),
               "issues_count": len(final_state.get('issues', [])),
               "errors_count": len(final_state.get('errors', []))
           })

       except Exception as e:
           logger.error("Monitoring cycle failed", exc_info=True, extra={
               "error_type": type(e).__name__,
               "error_message": str(e)
           })

           # Send error notification to Telegram
           await self._send_error_notification(e)

   async def _send_error_notification(self, error: Exception):
       """Send error alert to Telegram"""
       message = f"""🚨 **Monitoring System Error**

{type(error).__name__}: {str(error)}

The monitoring cycle failed to complete. Check logs for details.
"""
       try:
           telegram = TelegramClient(self.config.telegram)
           await telegram.send_message(message)
       except:
           logger.error("Failed to send error notification to Telegram")
   ```

2. Add structured logging to all collectors:
   ```python
   # In BaseCollector
   def __init__(self, config, thresholds, logger):
       self.logger = logger.getChild(self.__class__.__name__)

   # In each collector method
   self.logger.info("Starting collection", extra={
       "collector": self.collector_name,
       "target_count": len(self.config)
   })
   ```

**Acceptance Criteria**:
- [ ] All errors logged with structured context
- [ ] Critical errors send Telegram notification
- [ ] Logs include timing and token usage metrics
- [ ] JSON log format for easy parsing

---

## SPRINT 5: Testing & Deployment (Week 5)

### Task 5.1: Unit Tests
**Priority**: High
**Estimated Time**: 8 hours

**Subtasks**:
1. Create `tests/test_collectors/test_base.py`:
   ```python
   import pytest
   from src.collectors.base import BaseCollector, HealthStatus

   def test_determine_status_higher_is_worse():
       collector = MockCollector(thresholds={"cpu_red": 90, "cpu_yellow": 70})

       assert collector._determine_status("cpu", 95) == HealthStatus.RED
       assert collector._determine_status("cpu", 75) == HealthStatus.YELLOW
       assert collector._determine_status("cpu", 50) == HealthStatus.GREEN

   def test_determine_status_lower_is_worse():
       collector = MockCollector(thresholds={"disk_free_red": 10, "disk_free_yellow": 20})

       assert collector._determine_status("disk_free", 5, higher_is_worse=False) == HealthStatus.RED
       assert collector._determine_status("disk_free", 15, higher_is_worse=False) == HealthStatus.YELLOW
       assert collector._determine_status("disk_free", 50, higher_is_worse=False) == HealthStatus.GREEN
   ```

2. Create tests for each collector:
   - `tests/test_collectors/test_ec2_collector.py` - mock boto3
   - `tests/test_collectors/test_api_collector.py` - mock httpx
   - `tests/test_collectors/test_docker_collector.py` - mock SSH

3. Create `tests/test_agents/test_analysis_agent.py`:
   ```python
   @pytest.mark.asyncio
   async def test_analysis_with_issues(mock_bedrock, mock_budget):
       agent = AnalysisAgent(mock_bedrock, mock_budget)

       issues = [
           CollectorResult(
               collector_name="ec2",
               target_name="prod-server",
               status=HealthStatus.RED,
               metrics={"cpu": 95},
               message="High CPU"
           )
       ]

       result = await agent.analyze(issues)

       assert "root_cause" in result
       assert "recommendations" in result
       assert isinstance(result["recommendations"], list)
   ```

4. Create `tests/test_services/test_budget_tracker.py`:
   ```python
   def test_budget_tracking():
       tracker = BudgetTracker(daily_budget_usd=3.0)

       # Record usage
       tracker.record_usage(input_tokens=10000, output_tokens=2000)

       # Check cost calculation
       expected_cost = (10000/1_000_000)*0.80 + (2000/1_000_000)*4.00
       assert abs(tracker.today_spent - expected_cost) < 0.001

   def test_budget_enforcement():
       tracker = BudgetTracker(daily_budget_usd=0.01)  # Very low budget

       # Exhaust budget
       tracker.record_usage(input_tokens=100000, output_tokens=10000)

       # Should block next request
       assert not tracker.can_make_request()
   ```

**Acceptance Criteria**:
- [ ] All collector unit tests pass
- [ ] All agent unit tests pass
- [ ] All service unit tests pass
- [ ] Test coverage >70%

---

### Task 5.2: Integration Tests
**Priority**: Medium
**Estimated Time**: 6 hours

**Subtasks**:
1. Create `tests/test_integration/test_workflow.py`:
   ```python
   @pytest.mark.asyncio
   async def test_full_workflow_no_issues():
       """Test complete workflow with all systems healthy"""
       config = load_test_config()
       workflow = MonitoringWorkflow(config)

       # Mock all collectors to return GREEN
       with mock_collectors(status=HealthStatus.GREEN):
           final_state = await workflow.run()

       assert len(final_state['all_results']) > 0
       assert len(final_state['issues']) == 0
       assert "No issues" in final_state['root_cause_analysis']

   @pytest.mark.asyncio
   async def test_full_workflow_with_issues():
       """Test complete workflow with issues detected"""
       config = load_test_config()
       workflow = MonitoringWorkflow(config)

       # Mock some collectors to return RED
       with mock_collectors(status=HealthStatus.RED, count=3):
           final_state = await workflow.run()

       assert len(final_state['issues']) == 3
       assert final_state['root_cause_analysis'] != "No issues"
       assert len(final_state['telegram_message']) > 100
   ```

2. Create end-to-end test with real AWS (optional, manual):
   ```python
   @pytest.mark.e2e
   @pytest.mark.asyncio
   async def test_real_aws_integration():
       """Test with real AWS services (requires credentials)"""
       config = load_prod_config()
       app = MonitoringApp(config_path="config/config.yaml", dry_run=True)

       await app.run_monitoring_cycle()

       # Check logs for errors
       # Verify token usage is reasonable
   ```

**Acceptance Criteria**:
- [ ] Integration tests pass with mocked dependencies
- [ ] End-to-end test documented for manual execution
- [ ] Test fixtures created for common scenarios

---

### Task 5.3: Cost Testing
**Priority**: High
**Estimated Time**: 4 hours

**Subtasks**:
1. Create `tests/test_cost_estimation.py`:
   ```python
   @pytest.mark.asyncio
   async def test_token_usage_within_budget():
       """Verify token usage stays within daily budget"""
       config = load_test_config()
       app = MonitoringApp(config)

       # Run multiple cycles
       total_tokens = 0
       for _ in range(4):  # 4 cycles (6-hour intervals in 24h)
           await app.run_monitoring_cycle()
           total_tokens += app.workflow.budget_tracker.today_spent

       # Calculate cost
       # Haiku 4.5: $0.80/1M input, $4.00/1M output (assuming 1:1 ratio)
       estimated_cost = total_tokens * 2.40 / 1_000_000

       assert estimated_cost < 3.0, f"Estimated daily cost ${estimated_cost:.2f} exceeds budget"
   ```

2. Create cost profiling script:
   ```python
   # scripts/profile_costs.py
   async def profile_monitoring_cycle():
       """Profile token usage by component"""
       workflow = MonitoringWorkflow(load_test_config())

       # Track tokens per agent call
       analysis_tokens = 0
       report_tokens = 0

       # Run cycle with instrumentation
       final_state = await workflow.run()

       print(f"Analysis Agent: {analysis_tokens} tokens")
       print(f"Report Agent: {report_tokens} tokens")
       print(f"Total: {final_state['token_usage']} tokens")

       # Calculate cost
       cost = (final_state['token_usage'] / 1_000_000) * 2.40
       print(f"Cost per cycle: ${cost:.4f}")
       print(f"Projected daily cost (4 cycles): ${cost * 4:.2f}")
   ```

**Acceptance Criteria**:
- [ ] Token usage measured per cycle
- [ ] Projected daily cost <$3
- [ ] Cost profiling script available
- [ ] Optimization recommendations documented

---

### Task 5.4: EC2 Deployment
**Priority**: High
**Estimated Time**: 4 hours

**Subtasks**:
1. Create `deployment/deploy.sh`:
   ```bash
   #!/bin/bash
   set -e

   # Deploy to EC2 instance
   EC2_HOST="your-ec2-instance.com"
   SSH_KEY="~/.ssh/monitoring-agent.pem"

   echo "Building Docker image..."
   docker build -t monitoring-agent:latest -f deployment/Dockerfile .
   docker save monitoring-agent:latest | gzip > /tmp/monitoring-agent.tar.gz

   echo "Copying to EC2..."
   scp -i $SSH_KEY /tmp/monitoring-agent.tar.gz ec2-user@$EC2_HOST:/tmp/
   scp -i $SSH_KEY deployment/docker-compose.yml ec2-user@$EC2_HOST:/home/ec2-user/
   scp -i $SSH_KEY .env ec2-user@$EC2_HOST:/home/ec2-user/

   echo "Deploying on EC2..."
   ssh -i $SSH_KEY ec2-user@$EC2_HOST << 'EOF'
     cd /home/ec2-user
     docker load < /tmp/monitoring-agent.tar.gz
     docker-compose down
     docker-compose up -d
     docker-compose logs -f --tail=50
   EOF
   ```

2. Create IAM role for EC2:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "cloudwatch:GetMetricStatistics",
           "ec2:DescribeInstances",
           "s3:ListBucket",
           "s3:GetObject",
           "bedrock:InvokeModel"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

3. Create deployment documentation:
   ```markdown
   # Deployment Guide

   ## Prerequisites
   - EC2 instance with Docker installed
   - IAM role attached to EC2
   - Security group allows outbound HTTPS

   ## Steps
   1. Clone repository on EC2
   2. Copy .env file with credentials
   3. Copy config/config.yaml
   4. Run docker-compose up -d
   5. Check logs: docker-compose logs -f
   ```

**Acceptance Criteria**:
- [ ] Deployment script automates EC2 setup
- [ ] IAM role configured with minimal permissions
- [ ] Deployment documentation complete
- [ ] Successfully deployed and running on EC2

---

### Task 5.5: Documentation
**Priority**: Medium
**Estimated Time**: 4 hours

**Subtasks**:
1. Update `README.md`:
   ```markdown
   # IT Infrastructure Monitoring AI Agents

   AI-powered monitoring system using LangGraph and Claude Haiku 4.5.

   ## Features
   - Monitors EC2, VPS, Docker, APIs, databases, LLMs, S3
   - AI-powered root cause analysis
   - Telegram reports with actionable recommendations
   - Budget-aware LLM usage

   ## Quick Start
   1. Clone repository
   2. Copy .env.example to .env and fill in credentials
   3. Copy config/config.example.yaml to config/config.yaml
   4. Run: docker-compose up -d

   ## Configuration
   See config/config.example.yaml for full options.

   ## Development
   - Install dependencies: pip install -r deployment/requirements.txt
   - Run tests: pytest
   - Run locally: python -m src.main --run-once

   ## Cost Management
   - Daily budget: $3 USD (configurable)
   - Haiku 4.5 pricing: $0.80/1M input, $4.00/1M output tokens
   - Estimated usage: ~30k tokens per cycle
   ```

2. Create `OPERATIONS.md`:
   ```markdown
   # Operations Runbook

   ## Monitoring the Monitor
   - Check logs: docker-compose logs -f monitoring-agent
   - Check budget: cat /tmp/budget_state.json

   ## Troubleshooting
   ### No Telegram messages
   - Verify TELEGRAM_BOT_TOKEN is correct
   - Check bot has permission to send to CHAT_ID

   ### High token usage
   - Review prompt templates in agents/
   - Reduce max_tokens in config

   ### Collection failures
   - Check AWS credentials
   - Verify SSH keys have correct permissions
   - Test API endpoints manually

   ## Maintenance
   ### Updating configuration
   1. Edit config/config.yaml
   2. Restart container: docker-compose restart

   ### Updating code
   1. Pull latest changes
   2. Rebuild: docker-compose build
   3. Restart: docker-compose up -d
   ```

**Acceptance Criteria**:
- [ ] README has complete setup instructions
- [ ] Operations runbook covers common issues
- [ ] Code documentation (docstrings) complete
- [ ] Architecture diagrams included

---

## FINAL CHECKLIST

### Functionality
- [ ] All 7 collector types implemented
- [ ] LangGraph workflow runs end-to-end
- [ ] AI analysis provides root cause insights
- [ ] Telegram reports are clear and actionable
- [ ] Budget tracking prevents overspending
- [ ] Scheduler runs at configured intervals

### Code Quality
- [ ] Unit tests pass (coverage >70%)
- [ ] Integration tests pass
- [ ] No hardcoded credentials
- [ ] Structured logging throughout
- [ ] Error handling on all external calls
- [ ] Type hints on all functions

### Deployment
- [ ] Docker image builds successfully
- [ ] Runs on EC2 without errors
- [ ] IAM roles configured
- [ ] Configuration externalized
- [ ] Logs accessible

### Documentation
- [ ] README with setup guide
- [ ] Config examples provided
- [ ] Operations runbook complete
- [ ] Code documented with docstrings
- [ ] Architecture design documented

### Performance
- [ ] Monitoring cycle completes <10 minutes
- [ ] Token usage <50k per cycle
- [ ] Daily cost <$3
- [ ] Collectors run in parallel

---

## ESTIMATIONS SUMMARY

| Sprint | Tasks | Estimated Hours | Developer Days |
|--------|-------|----------------|----------------|
| 1: Core Infrastructure | 4 tasks | 13 hours | 1.6 days |
| 2: Data Collectors | 8 tasks | 41 hours | 5.1 days |
| 3: AI Agents | 6 tasks | 35 hours | 4.4 days |
| 4: Integration | 5 tasks | 17 hours | 2.1 days |
| 5: Testing & Deployment | 5 tasks | 26 hours | 3.3 days |
| **Total** | **28 tasks** | **132 hours** | **16.5 days** |

**Assuming 8 hours/day**: ~3.5 weeks for single developer

**With contingency (20%)**: ~4-5 weeks total

---

## NEXT STEPS

1. **Review**: Product owner and architect review this task breakdown
2. **Prioritize**: Confirm MVP scope (can defer some collectors if needed)
3. **Assign**: Assign developer and set start date
4. **Setup**: Create project board (Jira/GitHub Issues) with these tasks
5. **Kickoff**: Sprint 1 planning meeting

---

**Document Owner**: Software Architect
**Review Status**: Pending developer review
**Last Updated**: 2025-12-27
