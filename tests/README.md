# Test Suite

Comprehensive test suite for the IT Infrastructure Monitoring System.

## Overview

Tests are organized by component and use the actual `config/config.yaml` configuration to validate collectors work with real-world settings.

## Structure

```
tests/
├── conftest.py                      # Shared fixtures and config loader
├── test_collectors/                 # Collector tests
│   ├── test_api_collector.py       # API endpoint health checks
│   ├── test_database_collector.py  # PostgreSQL connectivity
│   ├── test_docker_collector.py    # Docker container status
│   ├── test_ec2_collector.py       # EC2 instance metrics
│   ├── test_llm_collector.py       # LLM model availability
│   ├── test_s3_collector.py        # S3 bucket accessibility
│   └── test_vps_collector.py       # VPS server metrics
├── test_agents/                     # AI agent tests (future)
├── test_services/                   # Service tests (future)
└── test_integration/                # End-to-end tests (future)
```

## Configuration-Based Testing

Tests use **real configuration** from `config/config.yaml` via shared pytest fixtures in `conftest.py`:

- `ec2_configs` - Loads EC2 instances from config
- `vps_configs` - Loads VPS servers from config
- `api_configs` - Loads API endpoints from config
- `database_configs` - Loads databases from config
- `llm_configs` - Loads LLM models from config
- `s3_configs` - Loads S3 buckets from config
- `thresholds` - Loads system thresholds from config

### Benefits

✅ **Tests validate actual infrastructure** - Uses your real EC2 instance IDs, API URLs, bucket names
✅ **No hardcoded test data** - Configuration changes automatically reflected in tests
✅ **Skip when not configured** - Tests skip gracefully if resource type not in config
✅ **Realistic validation** - Ensures collectors work with your specific setup

### Example

If your `config/config.yaml` has:
```yaml
targets:
  ec2_instances:
    - instance_id: "i-0cb02c48bb5346606"
      name: "spim_vm1"
      region: "us-east-1"
    - instance_id: "i-064b9dd3118646f06"
      name: "spim_vm2"
      region: "us-east-1"
```

Then `test_ec2_collector.py` will test with **both instances** and validate names/IDs match your config.

## Running Tests

### Run All Tests
```bash
pytest tests/ -v
```

### Run Specific Collector Tests
```bash
pytest tests/test_collectors/test_api_collector.py -v
pytest tests/test_collectors/test_ec2_collector.py -v
```

### Run with Coverage
```bash
pytest tests/ --cov=src --cov-report=html --cov-report=term
```

Coverage report will be in `htmlcov/index.html`.

### Run Tests Matching Pattern
```bash
# Only success tests
pytest tests/ -v -k "success"

# Only failure tests
pytest tests/ -v -k "failure or error"

# Specific collector
pytest tests/ -v -k "ec2"
```

### Skip Slow Tests
```bash
# Future: when integration tests added
pytest tests/ -v -m "not slow"
```

## Test Coverage

### Collector Tests

Each collector test suite covers:

✅ **Success scenarios** - Normal operation with GREEN status
✅ **Warning scenarios** - Threshold warnings with YELLOW status
✅ **Failure scenarios** - Errors and outages with RED status
✅ **Missing dependencies** - Graceful handling with UNKNOWN status
✅ **Empty configuration** - No resources configured
✅ **Parallel execution** - Concurrent checks performance
✅ **Error handling** - API errors, connection failures, parsing errors

### Test Patterns

**Mocking External Services**:
- All AWS API calls mocked with `unittest.mock`
- SSH connections mocked with `paramiko` stubs
- HTTP requests mocked with `httpx` mocks
- Database connections mocked with `psycopg2` stubs

**No Real Infrastructure Required**:
- Tests don't make actual AWS API calls
- Tests don't SSH to real servers
- Tests don't query real databases
- Tests don't hit real API endpoints

**Fast Execution**:
- All external I/O mocked
- Tests complete in seconds
- Safe to run in CI/CD pipelines

## Writing New Tests

### 1. Use Shared Fixtures

```python
def test_my_feature(ec2_configs, thresholds, logger):
    """Test uses real EC2 configs from config.yaml."""
    collector = EC2Collector(ec2_configs, thresholds, logger)
    # Test logic...
```

### 2. Mock External Services

```python
with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    # Setup mock responses...
```

### 3. Handle Missing Config

Tests automatically skip if resource type not configured:

```python
@pytest.fixture
def ec2_configs(config):
    """Get EC2 configurations from config.yaml."""
    if not config.targets.ec2_instances:
        pytest.skip("No EC2 instances configured in config.yaml")
    return config.targets.ec2_instances
```

### 4. Test Multiple Scenarios

```python
@pytest.mark.asyncio
async def test_success(configs, thresholds, logger):
    """Test successful operation."""

@pytest.mark.asyncio
async def test_failure(configs, thresholds, logger):
    """Test error handling."""

@pytest.mark.asyncio
async def test_empty_config(thresholds, logger):
    """Test with no resources configured."""
```

## Continuous Integration

Tests are designed for CI/CD:

```yaml
# .github/workflows/test.yml
- name: Run tests
  run: |
    pytest tests/ --cov=src --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
```

## Troubleshooting

### Config File Not Found

```
SKIPPED [1] tests/conftest.py:18: Config file not found: /path/to/config.yaml
```

**Solution**: Ensure `config/config.yaml` exists. Copy from `config/config.example.yaml` if needed.

### All Tests Skipped

```
SKIPPED [7] tests/conftest.py:XX: No [resource] configured in config.yaml
```

**Solution**: This is normal if you haven't configured that resource type. Tests skip gracefully.

### Import Errors

```
ModuleNotFoundError: No module named 'src'
```

**Solution**: Run tests from project root, or install package in development mode:
```bash
pip install -e .
```

### Mock Assertion Failures

If mocks aren't being called as expected, verify:
- Patch path matches actual import path
- Mock setup happens before collector execution
- Side effects configured for multiple calls

## Future Enhancements

- [ ] Integration tests with real AWS sandbox
- [ ] Performance benchmarks
- [ ] Load testing for parallel collection
- [ ] Agent tests (analysis, reporting)
- [ ] Workflow tests (LangGraph)
- [ ] End-to-end tests with mocked Bedrock

## Contributing

When adding new collectors:
1. Add fixture to `conftest.py`
2. Create test file in `tests/test_collectors/`
3. Use shared fixtures from conftest
4. Mock all external dependencies
5. Test success, failure, and edge cases
6. Ensure tests work with empty config
