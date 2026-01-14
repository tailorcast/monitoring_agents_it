"""Configuration loader with YAML parsing and environment variable substitution."""

import yaml
import os
import re
from pathlib import Path
from typing import Any, Dict
from .models import MonitoringSystemConfig


class ConfigLoader:
    """Load and validate monitoring system configuration."""

    @staticmethod
    def load_from_file(config_path: str) -> MonitoringSystemConfig:
        """
        Load configuration from YAML file with environment variable substitution.

        Args:
            config_path: Path to YAML configuration file

        Returns:
            MonitoringSystemConfig: Validated configuration object

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML parsing fails
            pydantic.ValidationError: If configuration validation fails
        """
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_file, 'r') as f:
            raw_config = yaml.safe_load(f)

        # Substitute environment variables
        raw_config = ConfigLoader._substitute_env_vars(raw_config)

        # Validate with Pydantic
        return MonitoringSystemConfig(**raw_config)

    @staticmethod
    def _substitute_env_vars(obj: Any) -> Any:
        """
        Recursively substitute ${ENV_VAR} placeholders with environment values.

        Args:
            obj: Object to process (str, dict, list, or primitive)

        Returns:
            Object with environment variables substituted
        """
        if isinstance(obj, str):
            # Replace ${VAR_NAME} with os.getenv('VAR_NAME')
            pattern = r'\$\{(\w+)\}'
            return re.sub(pattern, lambda m: os.getenv(m.group(1), ''), obj)

        elif isinstance(obj, dict):
            return {k: ConfigLoader._substitute_env_vars(v) for k, v in obj.items()}

        elif isinstance(obj, list):
            return [ConfigLoader._substitute_env_vars(item) for item in obj]

        return obj
