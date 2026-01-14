"""Metric data structures for collectors."""

from dataclasses import dataclass
from typing import Optional, Dict
import time
from .status import HealthStatus


@dataclass
class CollectorResult:
    """Standard result format from all collectors."""

    collector_name: str
    target_name: str
    status: HealthStatus
    metrics: Dict[str, any]  # Raw metric values
    message: str  # Human-readable summary
    error: Optional[str] = None
    timestamp: Optional[float] = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = time.time()
