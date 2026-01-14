"""Health status enumeration."""

from enum import Enum


class HealthStatus(Enum):
    """Infrastructure component health status."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    UNKNOWN = "unknown"

    def to_emoji(self) -> str:
        """
        Convert status to emoji representation.

        Returns:
            str: Emoji representing the health status
        """
        return {
            HealthStatus.GREEN: "🟢",
            HealthStatus.YELLOW: "🟡",
            HealthStatus.RED: "🔴",
            HealthStatus.UNKNOWN: "⚪"
        }[self]
