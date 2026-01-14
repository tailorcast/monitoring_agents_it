"""Shared pytest configuration and fixtures."""

import pytest
import os
from pathlib import Path

from src.config.loader import ConfigLoader
from src.utils.logger import setup_logger


# Path to config file
CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"


@pytest.fixture(scope="session")
def config():
    """Load actual configuration from config.yaml."""
    if not CONFIG_PATH.exists():
        pytest.skip(f"Config file not found: {CONFIG_PATH}")

    return ConfigLoader.load_from_file(str(CONFIG_PATH))


@pytest.fixture
def logger():
    """Create logger for tests."""
    return setup_logger("test")


@pytest.fixture
def ec2_configs(config):
    """Get EC2 configurations from config.yaml."""
    if not config.targets.ec2_instances:
        pytest.skip("No EC2 instances configured in config.yaml")
    return config.targets.ec2_instances


@pytest.fixture
def vps_configs(config):
    """Get VPS configurations from config.yaml."""
    if not config.targets.vps_servers:
        pytest.skip("No VPS servers configured in config.yaml")
    return config.targets.vps_servers


@pytest.fixture
def api_configs(config):
    """Get API endpoint configurations from config.yaml."""
    if not config.targets.api_endpoints:
        pytest.skip("No API endpoints configured in config.yaml")
    return config.targets.api_endpoints


@pytest.fixture
def database_configs(config):
    """Get database configurations from config.yaml."""
    if not config.targets.databases:
        pytest.skip("No databases configured in config.yaml")
    return config.targets.databases


@pytest.fixture
def llm_configs(config):
    """Get LLM model configurations from config.yaml."""
    if not config.targets.llm_models:
        pytest.skip("No LLM models configured in config.yaml")
    return config.targets.llm_models


@pytest.fixture
def s3_configs(config):
    """Get S3 bucket configurations from config.yaml."""
    if not config.targets.s3_buckets:
        pytest.skip("No S3 buckets configured in config.yaml")
    return config.targets.s3_buckets


@pytest.fixture
def thresholds(config):
    """Get system thresholds from config.yaml."""
    return config.thresholds.__dict__
