"""API endpoint health check collector."""

import asyncio
import time
from typing import List
import logging

try:
    import httpx
except ImportError:
    httpx = None

from ..config.models import APIEndpointConfig
from ..utils.status import HealthStatus
from ..utils.metrics import CollectorResult
from .base import BaseCollector, safe_collect


class APICollector(BaseCollector):
    """Collector for API endpoint health checks."""

    def __init__(
        self,
        config: List[APIEndpointConfig],
        thresholds: dict,
        logger: logging.Logger
    ):
        """
        Initialize API collector.

        Args:
            config: List of API endpoint configurations
            thresholds: System thresholds including api_timeout_ms and api_slow_ms
            logger: Logger instance
        """
        super().__init__(config, thresholds, logger)

    @safe_collect
    async def collect(self) -> List[CollectorResult]:
        """
        Check all API endpoints concurrently.

        Returns:
            List[CollectorResult]: Health check results for all endpoints
        """
        if httpx is None:
            self.logger.warning("httpx library not available")
            return [CollectorResult(
                collector_name="api",
                target_name="all",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message="httpx library not installed",
                error="httpx not available"
            )]

        if not self.config:
            self.logger.info("No API endpoints configured")
            return []

        self.logger.info(f"Checking {len(self.config)} API endpoints")

        # Run all checks concurrently
        tasks = [self._check_endpoint(endpoint_config) for endpoint_config in self.config]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions from gather
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                endpoint_name = self.config[i].name if i < len(self.config) else "unknown"
                self.logger.error(f"Endpoint check failed for {endpoint_name}: {result}")
                final_results.append(CollectorResult(
                    collector_name="api",
                    target_name=endpoint_name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message=f"Check failed: {str(result)}",
                    error=str(result)
                ))
            else:
                final_results.append(result)

        return final_results

    async def _check_endpoint(self, config: APIEndpointConfig) -> CollectorResult:
        """
        Check single API endpoint.

        Args:
            config: API endpoint configuration

        Returns:
            CollectorResult: Health check result
        """
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
            elif response_time_ms > self.thresholds.get("api_timeout_ms", 5000):
                status = HealthStatus.RED
                message = f"Timeout ({response_time_ms:.0f}ms)"
            elif response_time_ms > self.thresholds.get("api_slow_ms", 2000):
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

        except httpx.RequestError as e:
            return CollectorResult(
                collector_name="api",
                target_name=config.name,
                status=HealthStatus.RED,
                metrics={"url": config.url},
                message=f"Request error: {str(e)}",
                error=str(e)
            )

        except Exception as e:
            return CollectorResult(
                collector_name="api",
                target_name=config.name,
                status=HealthStatus.UNKNOWN,
                metrics={"url": config.url},
                message=f"Unexpected error: {str(e)}",
                error=str(e)
            )
