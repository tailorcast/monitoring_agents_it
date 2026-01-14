"""Tests for S3 collector."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.collectors.s3_collector import S3Collector
from src.utils.status import HealthStatus

# Fixtures imported from conftest.py: s3_configs, thresholds, logger


@pytest.mark.asyncio
async def test_s3_collector_success(s3_configs, thresholds, logger):
    """Test successful S3 bucket checks using real config."""
    collector = S3Collector(s3_configs, thresholds, logger)

    with patch('src.collectors.s3_collector.boto3') as mock_boto3:
        # Mock S3 client
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        # Mock successful head_bucket (bucket exists and accessible)
        mock_s3_client.head_bucket.return_value = {}

        # Mock get_bucket_location
        mock_s3_client.get_bucket_location.return_value = {
            'LocationConstraint': 'us-east-1'
        }

        # Mock list_objects_v2 (bucket has objects)
        mock_s3_client.list_objects_v2.return_value = {
            'KeyCount': 1,
            'Contents': [{'Key': 'test.txt'}]
        }

        # Mock get_bucket_versioning
        mock_s3_client.get_bucket_versioning.return_value = {
            'Status': 'Enabled'
        }

        # Execute
        results = await collector.collect()

        # Verify
        assert len(results) == len(s3_configs)

        # Check all buckets
        for i, result in enumerate(results):
            assert result.collector_name == "s3"
            assert result.target_name == s3_configs[i].bucket
            assert result.status == HealthStatus.GREEN
            assert result.metrics["accessible"] is True
            assert result.metrics["listable"] is True
            assert result.metrics["versioning"] == "Enabled"


@pytest.mark.asyncio
async def test_s3_collector_bucket_not_found(s3_configs, thresholds, logger):
    """Test S3 bucket not found (RED)."""
    collector = S3Collector([s3_configs[0]], thresholds, logger)

    with patch('src.collectors.s3_collector.boto3') as mock_boto3:
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        # Mock 404 error (bucket not found)
        from botocore.exceptions import ClientError
        error_response = {
            'Error': {
                'Code': '404',
                'Message': 'Not Found'
            }
        }
        mock_s3_client.head_bucket.side_effect = ClientError(error_response, 'head_bucket')

        # Execute
        results = await collector.collect()

        # Verify RED status
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert "not found" in results[0].message.lower()


@pytest.mark.asyncio
async def test_s3_collector_access_denied(s3_configs, thresholds, logger):
    """Test S3 bucket access denied (RED)."""
    collector = S3Collector([s3_configs[0]], thresholds, logger)

    with patch('src.collectors.s3_collector.boto3') as mock_boto3:
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        # Mock 403 error (access denied)
        from botocore.exceptions import ClientError
        error_response = {
            'Error': {
                'Code': '403',
                'Message': 'Forbidden'
            }
        }
        mock_s3_client.head_bucket.side_effect = ClientError(error_response, 'head_bucket')

        # Execute
        results = await collector.collect()

        # Verify RED status
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert "denied" in results[0].message.lower() or "forbidden" in results[0].error.lower()


@pytest.mark.asyncio
async def test_s3_collector_bucket_not_listable(s3_configs, thresholds, logger):
    """Test S3 bucket accessible but not listable (YELLOW)."""
    collector = S3Collector([s3_configs[0]], thresholds, logger)

    with patch('src.collectors.s3_collector.boto3') as mock_boto3:
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        # Mock successful head_bucket
        mock_s3_client.head_bucket.return_value = {}

        # Mock get_bucket_location
        mock_s3_client.get_bucket_location.return_value = {
            'LocationConstraint': 'us-east-1'
        }

        # Mock list_objects_v2 access denied
        from botocore.exceptions import ClientError
        error_response = {
            'Error': {
                'Code': 'AccessDenied',
                'Message': 'Access Denied'
            }
        }
        mock_s3_client.list_objects_v2.side_effect = ClientError(error_response, 'list_objects_v2')

        # Execute
        results = await collector.collect()

        # Verify YELLOW status (accessible but not listable)
        assert len(results) == 1
        assert results[0].status == HealthStatus.YELLOW
        assert results[0].metrics["accessible"] is True
        assert results[0].metrics["listable"] is False


@pytest.mark.asyncio
async def test_s3_collector_empty_bucket(s3_configs, thresholds, logger):
    """Test S3 bucket with no objects (GREEN)."""
    collector = S3Collector([s3_configs[0]], thresholds, logger)

    with patch('src.collectors.s3_collector.boto3') as mock_boto3:
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        # Mock successful head_bucket
        mock_s3_client.head_bucket.return_value = {}

        # Mock get_bucket_location
        mock_s3_client.get_bucket_location.return_value = {
            'LocationConstraint': 'us-east-1'
        }

        # Mock empty bucket
        mock_s3_client.list_objects_v2.return_value = {
            'KeyCount': 0
        }

        # Mock versioning disabled
        mock_s3_client.get_bucket_versioning.return_value = {}

        # Execute
        results = await collector.collect()

        # Verify GREEN status (empty but accessible)
        assert len(results) == 1
        assert results[0].status == HealthStatus.GREEN
        assert results[0].metrics["has_objects"] is False
        assert results[0].metrics["versioning"] == "Disabled"


@pytest.mark.asyncio
async def test_s3_collector_us_east_1_location(s3_configs, thresholds, logger):
    """Test S3 bucket in us-east-1 (special case with None location)."""
    collector = S3Collector([s3_configs[0]], thresholds, logger)

    with patch('src.collectors.s3_collector.boto3') as mock_boto3:
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        mock_s3_client.head_bucket.return_value = {}

        # us-east-1 returns None for LocationConstraint
        mock_s3_client.get_bucket_location.return_value = {
            'LocationConstraint': None
        }

        mock_s3_client.list_objects_v2.return_value = {'KeyCount': 0}
        mock_s3_client.get_bucket_versioning.return_value = {}

        # Execute
        results = await collector.collect()

        # Verify us-east-1 detected
        assert len(results) == 1
        assert results[0].status == HealthStatus.GREEN
        assert results[0].metrics["region"] == "us-east-1"


@pytest.mark.asyncio
async def test_s3_collector_no_boto3(s3_configs, thresholds, logger):
    """Test graceful handling when boto3 not installed."""
    collector = S3Collector(s3_configs, thresholds, logger)

    # Mock boto3 as unavailable
    with patch('src.collectors.s3_collector.boto3', None):
        results = await collector.collect()

        # Should return single UNKNOWN result
        assert len(results) == 1
        assert results[0].status == HealthStatus.UNKNOWN
        assert "boto3" in results[0].message.lower()


@pytest.mark.asyncio
async def test_s3_collector_empty_config(thresholds, logger):
    """Test collector with no buckets configured."""
    collector = S3Collector([], thresholds, logger)

    results = await collector.collect()

    # Should return empty list
    assert len(results) == 0


@pytest.mark.asyncio
async def test_s3_collector_multiple_buckets(s3_configs, thresholds, logger):
    """Test S3 collector with multiple buckets."""
    collector = S3Collector(s3_configs, thresholds, logger)

    with patch('src.collectors.s3_collector.boto3') as mock_boto3:
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        # Mock successful checks for all buckets
        mock_s3_client.head_bucket.return_value = {}
        mock_s3_client.get_bucket_location.return_value = {'LocationConstraint': 'us-east-1'}
        mock_s3_client.list_objects_v2.return_value = {'KeyCount': 1}
        mock_s3_client.get_bucket_versioning.return_value = {'Status': 'Enabled'}

        # Execute
        results = await collector.collect()

        # Verify all buckets checked
        assert len(results) == len(s3_configs)
        assert all(r.status == HealthStatus.GREEN for r in results)


@pytest.mark.asyncio
async def test_s3_collector_aws_api_error(s3_configs, thresholds, logger):
    """Test generic AWS API error handling."""
    collector = S3Collector([s3_configs[0]], thresholds, logger)

    with patch('src.collectors.s3_collector.boto3') as mock_boto3:
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        # Mock generic AWS error
        from botocore.exceptions import ClientError
        error_response = {
            'Error': {
                'Code': 'ServiceUnavailable',
                'Message': 'Service temporarily unavailable'
            }
        }
        mock_s3_client.head_bucket.side_effect = ClientError(error_response, 'head_bucket')

        # Execute
        results = await collector.collect()

        # Verify RED status
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED


@pytest.mark.asyncio
async def test_s3_collector_parallel_execution(s3_configs, thresholds, logger):
    """Test that multiple buckets are checked in parallel."""
    collector = S3Collector(s3_configs, thresholds, logger)

    with patch('src.collectors.s3_collector.boto3') as mock_boto3:
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        mock_s3_client.head_bucket.return_value = {}
        mock_s3_client.get_bucket_location.return_value = {'LocationConstraint': 'us-east-1'}
        mock_s3_client.list_objects_v2.return_value = {'KeyCount': 0}
        mock_s3_client.get_bucket_versioning.return_value = {}

        # Execute
        import time
        start = time.time()
        results = await collector.collect()
        duration = time.time() - start

        # Should complete quickly (parallel execution)
        assert duration < 2.0
        assert len(results) == len(s3_configs)


@pytest.mark.asyncio
async def test_s3_collector_versioning_suspended(s3_configs, thresholds, logger):
    """Test S3 bucket with versioning suspended."""
    collector = S3Collector([s3_configs[0]], thresholds, logger)

    with patch('src.collectors.s3_collector.boto3') as mock_boto3:
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        mock_s3_client.head_bucket.return_value = {}
        mock_s3_client.get_bucket_location.return_value = {'LocationConstraint': 'us-east-1'}
        mock_s3_client.list_objects_v2.return_value = {'KeyCount': 10}

        # Mock versioning suspended
        mock_s3_client.get_bucket_versioning.return_value = {'Status': 'Suspended'}

        # Execute
        results = await collector.collect()

        # Verify
        assert len(results) == 1
        assert results[0].status == HealthStatus.GREEN
        assert results[0].metrics["versioning"] == "Suspended"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
