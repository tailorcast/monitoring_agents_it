"""Tests for EC2 collector."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.collectors.ec2_collector import EC2Collector
from src.utils.status import HealthStatus

# Fixtures imported from conftest.py: ec2_configs, thresholds, logger


@pytest.mark.asyncio
async def test_ec2_collector_success(ec2_configs, thresholds, logger):
    """Test successful EC2 instance checks using real config."""
    collector = EC2Collector(ec2_configs, thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        # Mock EC2 client
        mock_ec2_client = MagicMock()
        mock_cloudwatch_client = MagicMock()

        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'ec2': mock_ec2_client,
            'cloudwatch': mock_cloudwatch_client
        }[service]

        # Mock describe_instances response for any instance
        def mock_describe_instances(InstanceIds):
            return {
                'Reservations': [{
                    'Instances': [{
                        'InstanceId': InstanceIds[0],
                        'State': {'Name': 'running'},
                        'InstanceType': 't3.medium',
                        'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                    }]
                }]
            }

        mock_ec2_client.describe_instances.side_effect = mock_describe_instances

        # Mock get_metric_statistics response (low CPU)
        mock_cloudwatch_client.get_metric_statistics.return_value = {
            'Datapoints': [{
                'Timestamp': datetime.utcnow(),
                'Average': 25.5
            }]
        }

        # Execute
        results = await collector.collect()

        # Verify
        assert len(results) == len(ec2_configs)

        # Check all instances
        for i, result in enumerate(results):
            assert result.collector_name == "ec2"
            assert result.target_name == ec2_configs[i].name
            assert result.status == HealthStatus.GREEN
            assert result.metrics["cpu_usage_pct"] == 25.5
            assert result.metrics["state"] == "running"
            assert result.metrics["instance_id"] == ec2_configs[i].instance_id


@pytest.mark.asyncio
async def test_ec2_collector_high_cpu(ec2_configs, thresholds, logger):
    """Test EC2 instance with high CPU (RED)."""
    collector = EC2Collector([ec2_configs[0]], thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()
        mock_cloudwatch_client = MagicMock()

        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'ec2': mock_ec2_client,
            'cloudwatch': mock_cloudwatch_client
        }[service]

        # Mock running instance
        mock_ec2_client.describe_instances.return_value = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-1234567890abcdef0',
                    'State': {'Name': 'running'},
                    'InstanceType': 't3.medium',
                    'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                }]
            }]
        }

        # Mock high CPU metric
        mock_cloudwatch_client.get_metric_statistics.return_value = {
            'Datapoints': [{
                'Timestamp': datetime.utcnow(),
                'Average': 95.0
            }]
        }

        # Execute
        results = await collector.collect()

        # Verify RED status for high CPU
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert results[0].metrics["cpu_usage_pct"] >= thresholds["cpu_red"]


@pytest.mark.asyncio
async def test_ec2_collector_instance_stopped(ec2_configs, thresholds, logger):
    """Test stopped EC2 instance (RED)."""
    collector = EC2Collector([ec2_configs[0]], thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()

        mock_boto3.client.return_value = mock_ec2_client

        # Mock stopped instance
        mock_ec2_client.describe_instances.return_value = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-1234567890abcdef0',
                    'State': {'Name': 'stopped'},
                    'InstanceType': 't3.medium',
                    'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                }]
            }]
        }

        # Execute
        results = await collector.collect()

        # Verify RED status for stopped instance
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert results[0].metrics["state"] == "stopped"
        assert "stopped" in results[0].message.lower()


@pytest.mark.asyncio
async def test_ec2_collector_no_metrics(ec2_configs, thresholds, logger):
    """Test EC2 instance with no CloudWatch metrics available (YELLOW)."""
    collector = EC2Collector([ec2_configs[0]], thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()
        mock_cloudwatch_client = MagicMock()

        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'ec2': mock_ec2_client,
            'cloudwatch': mock_cloudwatch_client
        }[service]

        # Mock running instance
        mock_ec2_client.describe_instances.return_value = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-1234567890abcdef0',
                    'State': {'Name': 'running'},
                    'InstanceType': 't3.medium',
                    'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                }]
            }]
        }

        # Mock no metrics available
        mock_cloudwatch_client.get_metric_statistics.return_value = {
            'Datapoints': []
        }

        # Execute
        results = await collector.collect()

        # Verify YELLOW status when metrics unavailable
        assert len(results) == 1
        assert results[0].status == HealthStatus.YELLOW
        assert results[0].metrics["cpu_usage_pct"] is None


@pytest.mark.asyncio
async def test_ec2_collector_instance_not_found(ec2_configs, thresholds, logger):
    """Test EC2 instance not found (RED)."""
    collector = EC2Collector([ec2_configs[0]], thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()
        mock_boto3.client.return_value = mock_ec2_client

        # Mock no reservations (instance not found)
        mock_ec2_client.describe_instances.return_value = {
            'Reservations': []
        }

        # Execute
        results = await collector.collect()

        # Verify RED status
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert "not found" in results[0].error.lower()


@pytest.mark.asyncio
async def test_ec2_collector_aws_api_error(ec2_configs, thresholds, logger):
    """Test AWS API error handling (RED)."""
    collector = EC2Collector([ec2_configs[0]], thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()
        mock_boto3.client.return_value = mock_ec2_client

        # Mock API error
        from botocore.exceptions import ClientError
        error_response = {
            'Error': {
                'Code': 'UnauthorizedOperation',
                'Message': 'You are not authorized to perform this operation'
            }
        }
        mock_ec2_client.describe_instances.side_effect = ClientError(
            error_response,
            'DescribeInstances'
        )

        # Execute
        results = await collector.collect()

        # Verify RED status for API error
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED


@pytest.mark.asyncio
async def test_ec2_collector_no_boto3(ec2_configs, thresholds, logger):
    """Test graceful handling when boto3 not installed."""
    collector = EC2Collector(ec2_configs, thresholds, logger)

    # Mock boto3 as unavailable
    with patch('src.collectors.ec2_collector.boto3', None):
        results = await collector.collect()

        # Should return single UNKNOWN result
        assert len(results) == 1
        assert results[0].status == HealthStatus.UNKNOWN
        assert "boto3" in results[0].message.lower()


@pytest.mark.asyncio
async def test_ec2_collector_empty_config(thresholds, logger):
    """Test collector with no instances configured."""
    collector = EC2Collector([], thresholds, logger)

    results = await collector.collect()

    # Should return empty list
    assert len(results) == 0


@pytest.mark.asyncio
async def test_ec2_collector_multiple_regions(ec2_configs, thresholds, logger):
    """Test EC2 collector with instances in different regions."""
    collector = EC2Collector(ec2_configs, thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        # Mock clients for different regions
        mock_clients = {}

        def get_client(service, region_name=None, **kwargs):
            key = f"{service}_{region_name}"
            if key not in mock_clients:
                mock_clients[key] = MagicMock()

                if service == 'ec2':
                    # Return correct instance based on InstanceIds parameter
                    def mock_describe_instances(InstanceIds):
                        return {
                            'Reservations': [{
                                'Instances': [{
                                    'InstanceId': InstanceIds[0],
                                    'State': {'Name': 'running'},
                                    'InstanceType': 't3.medium',
                                    'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                                }]
                            }]
                        }
                    mock_clients[key].describe_instances.side_effect = mock_describe_instances
                elif service == 'cloudwatch':
                    mock_clients[key].get_metric_statistics.return_value = {
                        'Datapoints': [{'Timestamp': datetime.utcnow(), 'Average': 30.0}]
                    }

            return mock_clients[key]

        mock_boto3.client.side_effect = get_client

        # Execute
        results = await collector.collect()

        # Verify all instances checked with their actual regions
        assert len(results) == len(ec2_configs)
        # Verify each result has the correct region from config
        result_regions = {r.metrics["region"] for r in results}
        config_regions = {c.region for c in ec2_configs}
        assert result_regions == config_regions


@pytest.mark.asyncio
async def test_ec2_collector_parallel_execution(ec2_configs, thresholds, logger):
    """Test that multiple instances are checked in parallel."""
    collector = EC2Collector(ec2_configs, thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()
        mock_cloudwatch_client = MagicMock()

        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'ec2': mock_ec2_client,
            'cloudwatch': mock_cloudwatch_client
        }[service]

        # Mock describe_instances to return correct instance based on InstanceIds parameter
        def mock_describe_instances(InstanceIds):
            return {
                'Reservations': [{
                    'Instances': [{
                        'InstanceId': InstanceIds[0],
                        'State': {'Name': 'running'},
                        'InstanceType': 't3.medium',
                        'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                    }]
                }]
            }

        mock_ec2_client.describe_instances.side_effect = mock_describe_instances
        mock_cloudwatch_client.get_metric_statistics.return_value = {
            'Datapoints': [{'Timestamp': datetime.utcnow(), 'Average': 30.0}]
        }

        # Execute
        import time
        start = time.time()
        results = await collector.collect()
        duration = time.time() - start

        # Should complete quickly (parallel execution)
        assert duration < 3.0
        assert len(results) == len(ec2_configs)


@pytest.mark.asyncio
async def test_ec2_collector_with_disk_monitoring(thresholds, logger):
    """Test EC2 instance with disk monitoring enabled (GREEN)."""
    from src.config.models import EC2InstanceConfig

    config_with_disk = EC2InstanceConfig(
        instance_id="i-1234567890abcdef0",
        name="test-instance-with-disk",
        region="us-east-1",
        monitor_disk=True,
        disk_path="/",
        disk_device="nvme0n1p1",
        disk_fstype="ext4"
    )

    collector = EC2Collector([config_with_disk], thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()
        mock_cloudwatch_client = MagicMock()

        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'ec2': mock_ec2_client,
            'cloudwatch': mock_cloudwatch_client
        }[service]

        # Mock running instance
        mock_ec2_client.describe_instances.return_value = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-1234567890abcdef0',
                    'State': {'Name': 'running'},
                    'InstanceType': 't3.medium',
                    'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                }]
            }]
        }

        # Mock get_metric_statistics to return different metrics based on call
        def mock_get_metrics(**kwargs):
            metric_name = kwargs.get('MetricName')
            if metric_name == 'CPUUtilization':
                return {
                    'Datapoints': [{
                        'Timestamp': datetime.utcnow(),
                        'Average': 25.0
                    }]
                }
            elif metric_name == 'disk_used_percent':
                # 75% used = 25% free (GREEN)
                return {
                    'Datapoints': [{
                        'Timestamp': datetime.utcnow(),
                        'Average': 75.0
                    }]
                }
            return {'Datapoints': []}

        mock_cloudwatch_client.get_metric_statistics.side_effect = mock_get_metrics

        # Execute
        results = await collector.collect()

        # Verify
        assert len(results) == 1
        assert results[0].status == HealthStatus.GREEN
        assert results[0].metrics["cpu_usage_pct"] == 25.0
        assert results[0].metrics["disk_free_pct"] == 25.0  # 100 - 75 = 25
        assert "CPU: 25.0%" in results[0].message
        assert "Disk free: 25.0%" in results[0].message


@pytest.mark.asyncio
async def test_ec2_collector_low_disk_space(thresholds, logger):
    """Test EC2 instance with low disk space (RED)."""
    from src.config.models import EC2InstanceConfig

    config_with_disk = EC2InstanceConfig(
        instance_id="i-1234567890abcdef0",
        name="test-low-disk",
        region="us-east-1",
        monitor_disk=True
    )

    collector = EC2Collector([config_with_disk], thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()
        mock_cloudwatch_client = MagicMock()

        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'ec2': mock_ec2_client,
            'cloudwatch': mock_cloudwatch_client
        }[service]

        mock_ec2_client.describe_instances.return_value = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-1234567890abcdef0',
                    'State': {'Name': 'running'},
                    'InstanceType': 't3.medium',
                    'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                }]
            }]
        }

        def mock_get_metrics(**kwargs):
            metric_name = kwargs.get('MetricName')
            if metric_name == 'CPUUtilization':
                return {
                    'Datapoints': [{
                        'Timestamp': datetime.utcnow(),
                        'Average': 30.0
                    }]
                }
            elif metric_name == 'disk_used_percent':
                # 95% used = 5% free (RED - below threshold of 10%)
                return {
                    'Datapoints': [{
                        'Timestamp': datetime.utcnow(),
                        'Average': 95.0
                    }]
                }
            return {'Datapoints': []}

        mock_cloudwatch_client.get_metric_statistics.side_effect = mock_get_metrics

        # Execute
        results = await collector.collect()

        # Verify RED status due to low disk
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert results[0].metrics["disk_free_pct"] == 5.0
        assert results[0].metrics["disk_free_pct"] <= thresholds["disk_free_red"]


@pytest.mark.asyncio
async def test_ec2_collector_disk_monitoring_no_agent(thresholds, logger):
    """Test EC2 with disk monitoring enabled but CloudWatch Agent not installed (YELLOW)."""
    from src.config.models import EC2InstanceConfig

    config_with_disk = EC2InstanceConfig(
        instance_id="i-1234567890abcdef0",
        name="test-no-agent",
        region="us-east-1",
        monitor_disk=True
    )

    collector = EC2Collector([config_with_disk], thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()
        mock_cloudwatch_client = MagicMock()

        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'ec2': mock_ec2_client,
            'cloudwatch': mock_cloudwatch_client
        }[service]

        mock_ec2_client.describe_instances.return_value = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-1234567890abcdef0',
                    'State': {'Name': 'running'},
                    'InstanceType': 't3.medium',
                    'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                }]
            }]
        }

        def mock_get_metrics(**kwargs):
            metric_name = kwargs.get('MetricName')
            if metric_name == 'CPUUtilization':
                return {
                    'Datapoints': [{
                        'Timestamp': datetime.utcnow(),
                        'Average': 30.0
                    }]
                }
            elif metric_name == 'disk_used_percent':
                # No data - CloudWatch Agent not installed
                return {'Datapoints': []}
            return {'Datapoints': []}

        # list_metrics also returns empty (agent not installed)
        mock_cloudwatch_client.list_metrics.return_value = {'Metrics': []}
        mock_cloudwatch_client.get_metric_statistics.side_effect = mock_get_metrics

        # Execute
        results = await collector.collect()

        # Verify YELLOW status (disk unavailable but CPU ok)
        assert len(results) == 1
        assert results[0].status == HealthStatus.YELLOW
        assert results[0].metrics["cpu_usage_pct"] == 30.0
        assert results[0].metrics["disk_free_pct"] is None
        assert "Disk: unavailable" in results[0].message


@pytest.mark.asyncio
async def test_ec2_collector_disk_auto_discovery(thresholds, logger):
    """Test auto-discovery of disk device/fstype when not specified."""
    from src.config.models import EC2InstanceConfig

    config_auto_disk = EC2InstanceConfig(
        instance_id="i-1234567890abcdef0",
        name="test-auto-disk",
        region="us-east-1",
        monitor_disk=True,
        disk_path="/"
        # No disk_device or disk_fstype specified
    )

    collector = EC2Collector([config_auto_disk], thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()
        mock_cloudwatch_client = MagicMock()

        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'ec2': mock_ec2_client,
            'cloudwatch': mock_cloudwatch_client
        }[service]

        mock_ec2_client.describe_instances.return_value = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-1234567890abcdef0',
                    'State': {'Name': 'running'},
                    'InstanceType': 't3.medium',
                    'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                }]
            }]
        }

        # First call with partial dimensions returns no data
        # Second call after auto-discovery returns data
        call_count = [0]

        def mock_get_metrics(**kwargs):
            metric_name = kwargs.get('MetricName')
            if metric_name == 'CPUUtilization':
                return {
                    'Datapoints': [{
                        'Timestamp': datetime.utcnow(),
                        'Average': 40.0
                    }]
                }
            elif metric_name == 'disk_used_percent':
                call_count[0] += 1
                if call_count[0] == 1:
                    # First call - no data with partial dimensions
                    return {'Datapoints': []}
                else:
                    # Second call - after auto-discovery
                    return {
                        'Datapoints': [{
                            'Timestamp': datetime.utcnow(),
                            'Average': 60.0
                        }]
                    }
            return {'Datapoints': []}

        # Mock list_metrics to return discovered dimensions
        mock_cloudwatch_client.list_metrics.return_value = {
            'Metrics': [{
                'Namespace': 'CWAgent',
                'MetricName': 'disk_used_percent',
                'Dimensions': [
                    {'Name': 'InstanceId', 'Value': 'i-1234567890abcdef0'},
                    {'Name': 'path', 'Value': '/'},
                    {'Name': 'device', 'Value': 'nvme0n1p1'},
                    {'Name': 'fstype', 'Value': 'ext4'}
                ]
            }]
        }

        mock_cloudwatch_client.get_metric_statistics.side_effect = mock_get_metrics

        # Execute
        results = await collector.collect()

        # Verify auto-discovery worked
        assert len(results) == 1
        assert results[0].status == HealthStatus.GREEN
        assert results[0].metrics["disk_free_pct"] == 40.0  # 100 - 60
        assert "Disk free: 40.0%" in results[0].message


@pytest.mark.asyncio
async def test_ec2_collector_backward_compatibility(ec2_configs, thresholds, logger):
    """Test that existing configs without monitor_disk still work (backward compatibility)."""
    # ec2_configs from fixture don't have monitor_disk field
    collector = EC2Collector(ec2_configs, thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()
        mock_cloudwatch_client = MagicMock()

        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'ec2': mock_ec2_client,
            'cloudwatch': mock_cloudwatch_client
        }[service]

        def mock_describe_instances(InstanceIds):
            return {
                'Reservations': [{
                    'Instances': [{
                        'InstanceId': InstanceIds[0],
                        'State': {'Name': 'running'},
                        'InstanceType': 't3.medium',
                        'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                    }]
                }]
            }

        mock_ec2_client.describe_instances.side_effect = mock_describe_instances
        mock_cloudwatch_client.get_metric_statistics.return_value = {
            'Datapoints': [{'Timestamp': datetime.utcnow(), 'Average': 25.5}]
        }

        # Execute
        results = await collector.collect()

        # Verify existing behavior preserved
        assert len(results) == len(ec2_configs)
        for result in results:
            assert result.status == HealthStatus.GREEN
            assert "cpu_usage_pct" in result.metrics
            assert "disk_free_pct" not in result.metrics  # Disk not monitored
            assert "Disk" not in result.message  # No disk in message


@pytest.mark.asyncio
async def test_ec2_collector_mixed_configs(thresholds, logger):
    """Test collector with mix of instances (some with disk monitoring, some without)."""
    from src.config.models import EC2InstanceConfig

    configs = [
        EC2InstanceConfig(
            instance_id="i-1111111111111111",
            name="instance-with-disk",
            region="us-east-1",
            monitor_disk=True
        ),
        EC2InstanceConfig(
            instance_id="i-2222222222222222",
            name="instance-cpu-only",
            region="us-east-1",
            monitor_disk=False  # Explicit false
        )
    ]

    collector = EC2Collector(configs, thresholds, logger)

    with patch('src.collectors.ec2_collector.boto3') as mock_boto3:
        mock_ec2_client = MagicMock()
        mock_cloudwatch_client = MagicMock()

        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'ec2': mock_ec2_client,
            'cloudwatch': mock_cloudwatch_client
        }[service]

        def mock_describe_instances(InstanceIds):
            return {
                'Reservations': [{
                    'Instances': [{
                        'InstanceId': InstanceIds[0],
                        'State': {'Name': 'running'},
                        'InstanceType': 't3.medium',
                        'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                    }]
                }]
            }

        mock_ec2_client.describe_instances.side_effect = mock_describe_instances

        def mock_get_metrics(**kwargs):
            metric_name = kwargs.get('MetricName')
            if metric_name == 'CPUUtilization':
                return {
                    'Datapoints': [{
                        'Timestamp': datetime.utcnow(),
                        'Average': 30.0
                    }]
                }
            elif metric_name == 'disk_used_percent':
                return {
                    'Datapoints': [{
                        'Timestamp': datetime.utcnow(),
                        'Average': 70.0
                    }]
                }
            return {'Datapoints': []}

        mock_cloudwatch_client.get_metric_statistics.side_effect = mock_get_metrics

        # Execute
        results = await collector.collect()

        # Verify mixed behavior
        assert len(results) == 2

        # First instance has disk monitoring
        disk_result = next(r for r in results if r.target_name == "instance-with-disk")
        assert "disk_free_pct" in disk_result.metrics
        assert disk_result.metrics["disk_free_pct"] == 30.0

        # Second instance does not have disk monitoring
        cpu_only_result = next(r for r in results if r.target_name == "instance-cpu-only")
        assert "disk_free_pct" not in cpu_only_result.metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
