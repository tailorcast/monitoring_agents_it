"""Pydantic configuration models for monitoring system."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
import re


class EC2InstanceConfig(BaseModel):
    """Configuration for EC2 instance monitoring."""
    instance_id: str
    name: str
    region: Optional[str] = "us-east-1"
    # Disk monitoring configuration
    monitor_disk: Optional[bool] = False  # Opt-in for backward compatibility
    disk_namespace: Optional[str] = "CWAgent"  # CloudWatch Agent namespace
    disk_path: Optional[str] = "/"  # Filesystem path to monitor
    disk_device: Optional[str] = None  # Auto-detect if None
    disk_fstype: Optional[str] = None  # Auto-detect if None


class VPSServerConfig(BaseModel):
    """Configuration for VPS server monitoring via SSH."""
    host: str
    name: str
    ssh_key_path: str
    port: int = 22
    username: str = "ubuntu"


class APIEndpointConfig(BaseModel):
    """Configuration for API endpoint health checks."""
    url: str
    name: str
    timeout_ms: Optional[int] = 5000

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v


class DatabaseConfig(BaseModel):
    """Configuration for PostgreSQL database monitoring."""
    host: str
    port: int = 5432
    database: str
    table: Optional[str] = None
    ssl_mode: str = "require"
    sslrootcert: Optional[str] = None  # Path to SSL CA certificate bundle


class LLMModelConfig(BaseModel):
    """Configuration for LLM availability monitoring."""
    provider: str  # "azure" or "bedrock"
    endpoint: Optional[str] = None
    model_id: Optional[str] = None


class S3BucketConfig(BaseModel):
    """Configuration for S3 bucket monitoring."""
    bucket: str
    region: str = "us-east-1"

    @field_validator('bucket')
    @classmethod
    def validate_bucket_name(cls, v: str) -> str:
        """Validate S3 bucket name format."""
        # S3 bucket naming rules: 3-63 chars, lowercase, numbers, hyphens, dots
        if not re.match(r'^[a-z0-9][a-z0-9.-]*[a-z0-9]$', v):
            raise ValueError('Invalid S3 bucket name format')
        if len(v) < 3 or len(v) > 63:
            raise ValueError('S3 bucket name must be 3-63 characters')
        return v


class ThresholdsConfig(BaseModel):
    """System health thresholds configuration."""
    cpu_red: int = Field(default=90, ge=0, le=100)
    cpu_yellow: int = Field(default=70, ge=0, le=100)
    ram_red: int = Field(default=90, ge=0, le=100)
    ram_yellow: int = Field(default=70, ge=0, le=100)
    disk_free_red: int = Field(default=10, ge=0, le=100)
    disk_free_yellow: int = Field(default=20, ge=0, le=100)
    api_timeout_ms: int = Field(default=5000, ge=100)
    api_slow_ms: int = Field(default=2000, ge=100)

    @field_validator('cpu_yellow', 'ram_yellow', 'disk_free_yellow')
    @classmethod
    def yellow_less_than_red(cls, v: int, info) -> int:
        """Ensure yellow threshold is less than red threshold."""
        # Note: This validator runs per field, cross-field validation in model_validator
        return v


class MonitoringConfig(BaseModel):
    """Monitoring schedule configuration."""
    schedule: str = "0 */6 * * *"  # Cron syntax

    @field_validator('schedule')
    @classmethod
    def validate_cron(cls, v: str) -> str:
        """Basic cron syntax validation."""
        parts = v.split()
        if len(parts) != 5:
            raise ValueError('Cron expression must have 5 parts: minute hour day month weekday')
        return v


class TelegramConfig(BaseModel):
    """Telegram bot configuration."""
    bot_token: str
    chat_id: str


class LLMConfig(BaseModel):
    """LLM configuration for AI agents."""
    provider: str = "bedrock"
    model: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0"  # Full Bedrock model ID
    region: str = "us-east-1"
    max_tokens: int = Field(default=4096, ge=100, le=1000000)
    daily_budget_usd: float = Field(default=3.0, ge=0.1)


class TargetsConfig(BaseModel):
    """All monitoring targets configuration."""
    ec2_instances: List[EC2InstanceConfig] = Field(default_factory=list)
    vps_servers: List[VPSServerConfig] = Field(default_factory=list)
    api_endpoints: List[APIEndpointConfig] = Field(default_factory=list)
    databases: List[DatabaseConfig] = Field(default_factory=list)
    llm_models: List[LLMModelConfig] = Field(default_factory=list)
    s3_buckets: List[S3BucketConfig] = Field(default_factory=list)


class MonitoringSystemConfig(BaseModel):
    """Root configuration model for the entire monitoring system."""
    monitoring: MonitoringConfig
    targets: TargetsConfig
    thresholds: ThresholdsConfig
    telegram: TelegramConfig
    llm: LLMConfig
