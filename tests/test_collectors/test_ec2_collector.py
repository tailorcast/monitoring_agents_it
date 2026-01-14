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
                    # Return correct instance based on config
                    for config in ec2_configs:
                        if config.region == region_name:
                            mock_clients[key].describe_instances.return_value = {
                                'Reservations': [{
                                    'Instances': [{
                                        'InstanceId': config.instance_id,
                                        'State': {'Name': 'running'},
                                        'InstanceType': 't3.medium',
                                        'LaunchTime': datetime(2024, 1, 1, 10, 0, 0)
                                    }]
                                }]
                            }
                            break
                elif service == 'cloudwatch':
                    mock_clients[key].get_metric_statistics.return_value = {
                        'Datapoints': [{'Timestamp': datetime.utcnow(), 'Average': 30.0}]
                    }

            return mock_clients[key]

        mock_boto3.client.side_effect = get_client

        # Execute
        results = await collector.collect()

        # Verify both instances checked with their actual regions
        assert len(results) == 2
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
        assert len(results) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
