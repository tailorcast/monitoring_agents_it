"""Tests for API collector."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx

from src.collectors.api_collector import APICollector
from src.utils.status import HealthStatus

# Fixtures imported from conftest.py: api_configs, thresholds, logger


@pytest.mark.asyncio
async def test_api_collector_success(api_configs, thresholds, logger):
    """Test successful API health checks using real config."""
    collector = APICollector(api_configs, thresholds, logger)

    # Mock httpx responses
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock successful responses for all configured endpoints
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client.get.return_value = mock_response

        # Execute
        results = await collector.collect()

        # Verify
        assert len(results) == len(api_configs)

        # Check all results are GREEN (response time will be very fast since mocked)
        for result in results:
            assert result.collector_name == "api"
            assert result.status == HealthStatus.GREEN
            assert "response_time_ms" in result.metrics
            assert result.metrics["response_time_ms"] < 1000  # Should be fast
            assert result.metrics["status_code"] == 200


@pytest.mark.asyncio
async def test_api_collector_slow_response(api_configs, thresholds, logger):
    """Test API with slow response (YELLOW)."""
    collector = APICollector(api_configs[:1], thresholds, logger)

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock slow response (use actual sleep to make it slow)
        import asyncio

        async def slow_get(*args, **kwargs):
            await asyncio.sleep(2.5)  # 2500ms - slow but not timeout
            mock_response = Mock()
            mock_response.status_code = 200
            return mock_response

        mock_client.get = slow_get

        # Execute
        results = await collector.collect()

        # Verify YELLOW status for slow response
        assert len(results) == 1
        assert results[0].status == HealthStatus.YELLOW
        assert results[0].metrics["response_time_ms"] > 2000  # Above slow threshold
        assert results[0].metrics["response_time_ms"] < 5000  # Below timeout
        assert "slow" in results[0].message.lower()


@pytest.mark.asyncio
async def test_api_collector_timeout(api_configs, thresholds, logger):
    """Test API timeout (RED)."""
    collector = APICollector(api_configs[:1], thresholds, logger)

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock timeout exception
        mock_client.get.side_effect = httpx.TimeoutException("Request timed out")

        # Execute
        results = await collector.collect()

        # Verify RED status for timeout
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert "timeout" in results[0].message.lower()


@pytest.mark.asyncio
async def test_api_collector_http_error(api_configs, thresholds, logger):
    """Test API HTTP error responses (RED)."""
    collector = APICollector(api_configs[:1], thresholds, logger)

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock 500 error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.elapsed.total_seconds.return_value = 0.5

        mock_client.get.return_value = mock_response

        # Execute
        results = await collector.collect()

        # Verify RED status for 500 error
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert results[0].metrics["status_code"] == 500


@pytest.mark.asyncio
async def test_api_collector_no_httpx(api_configs, thresholds, logger):
    """Test graceful handling when httpx not installed."""
    collector = APICollector(api_configs, thresholds, logger)

    # Mock httpx as unavailable
    with patch('src.collectors.api_collector.httpx', None):
        results = await collector.collect()

        # Should return single UNKNOWN result
        assert len(results) == 1
        assert results[0].status == HealthStatus.UNKNOWN
        assert "httpx" in results[0].message.lower()


@pytest.mark.asyncio
async def test_api_collector_empty_config(thresholds, logger):
    """Test collector with no endpoints configured."""
    collector = APICollector([], thresholds, logger)

    results = await collector.collect()

    # Should return empty list
    assert len(results) == 0


@pytest.mark.asyncio
async def test_api_collector_parallel_execution(api_configs, thresholds, logger):
    """Test that multiple endpoints are checked in parallel."""
    collector = APICollector(api_configs, thresholds, logger)

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock responses with delays
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.elapsed.total_seconds.return_value = 0.5

        mock_client.get.return_value = mock_response

        # Execute
        import time
        start = time.time()
        results = await collector.collect()
        duration = time.time() - start

        # Should complete quickly (parallel execution)
        # If sequential, would take 2x endpoint time
        assert duration < 2.0  # Should be much faster with parallel
        assert len(results) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
