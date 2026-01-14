"""Environment settings and validation."""

import os
from typing import Optional


class Settings:
    """Application settings from environment variables."""

    @staticmethod
    def get(key: str, default: Optional[str] = None, required: bool = False) -> str:
        """
        Get environment variable value.

        Args:
            key: Environment variable name
            default: Default value if not set
            required: Whether the variable is required

        Returns:
            str: Environment variable value

        Raises:
            ValueError: If required variable is not set
        """
        value = os.getenv(key, default)
        if required and not value:
            raise ValueError(f"Required environment variable not set: {key}")
        return value or ""

    @staticmethod
    def validate_required() -> None:
        """
        Validate that all required environment variables are set.

        Raises:
            ValueError: If any required variable is missing
        """
        required_vars = [
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
        ]

        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    # Convenience accessors
    AWS_REGION = property(lambda self: Settings.get("AWS_REGION", "us-east-1"))
    LOG_LEVEL = property(lambda self: Settings.get("LOG_LEVEL", "INFO"))
