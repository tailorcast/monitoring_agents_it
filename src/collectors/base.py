"""Base collector abstract class for all monitoring collectors."""

from abc import ABC, abstractmethod
from typing import List, Any, Optional, Dict
import logging
from functools import wraps

from ..utils.status import HealthStatus
from ..utils.metrics import CollectorResult


class BaseCollector(ABC):
    """Abstract base class for all collectors."""

    def __init__(self, config: Any, thresholds: Dict[str, int], logger: logging.Logger):
        """
        Initialize base collector.

        Args:
            config: Collector-specific configuration
            thresholds: System-wide threshold configuration
            logger: Logger instance
        """
        self.config = config
        self.thresholds = thresholds
        self.logger = logger.getChild(self.__class__.__name__)

    @abstractmethod
    async def collect(self) -> List[CollectorResult]:
        """
        Collect metrics and return results.

        Returns:
            List[CollectorResult]: Collection results

        Raises:
            Exception: Any collection errors (will be caught by safe_collect)
        """
        pass

    def _determine_status(
        self,
        metric_name: str,
        value: float,
        higher_is_worse: bool = True
    ) -> HealthStatus:
        """
        Determine health status based on thresholds.

        Args:
            metric_name: Name of metric (e.g., "cpu", "ram", "disk_free")
            value: Current metric value
            higher_is_worse: True for CPU/RAM (high is bad), False for disk_free (low is bad)

        Returns:
            HealthStatus: Determined health status
        """
        red_threshold = self.thresholds.get(f"{metric_name}_red")
        yellow_threshold = self.thresholds.get(f"{metric_name}_yellow")

        if red_threshold is None or yellow_threshold is None:
            self.logger.warning(f"Missing thresholds for {metric_name}")
            return HealthStatus.UNKNOWN

        if higher_is_worse:
            if value >= red_threshold:
                return HealthStatus.RED
            elif value >= yellow_threshold:
                return HealthStatus.YELLOW
            return HealthStatus.GREEN
        else:
            # Lower is worse (e.g., disk_free)
            if value <= red_threshold:
                return HealthStatus.RED
            elif value <= yellow_threshold:
                return HealthStatus.YELLOW
            return HealthStatus.GREEN


def safe_collect(func):
    """
    Decorator to handle collector exceptions gracefully.

    Args:
        func: Collector method to wrap

    Returns:
        Wrapped function that catches exceptions
    """
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            self.logger.error(f"Collection failed: {e}", exc_info=True)
            return [CollectorResult(
                collector_name=self.__class__.__name__.lower().replace('collector', ''),
                target_name="unknown",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message=f"Collection error: {str(e)}",
                error=str(e)
            )]
    return wrapper
