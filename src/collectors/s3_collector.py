"""S3 bucket accessibility checker."""

import asyncio
from typing import List
import logging

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = None

from ..config.models import S3BucketConfig
from ..utils.status import HealthStatus
from ..utils.metrics import CollectorResult
from .base import BaseCollector, safe_collect


class S3Collector(BaseCollector):
    """Collector for S3 bucket accessibility checks."""

    def __init__(
        self,
        config: List[S3BucketConfig],
        thresholds: dict,
        logger: logging.Logger
    ):
        """
        Initialize S3 collector.

        Args:
            config: List of S3 bucket configurations
            thresholds: System thresholds (not used for S3 checks)
            logger: Logger instance
        """
        super().__init__(config, thresholds, logger)

    @safe_collect
    async def collect(self) -> List[CollectorResult]:
        """
        Check all configured S3 buckets.

        Returns:
            List[CollectorResult]: S3 bucket check results
        """
        if not self.config:
            self.logger.info("No S3 buckets configured")
            return []

        if boto3 is None:
            return [CollectorResult(
                collector_name="s3",
                target_name="all",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message="boto3 library not installed",
                error="ImportError: boto3"
            )]

        self.logger.info(f"Checking {len(self.config)} S3 bucket(s)")

        # Run all checks concurrently
        tasks = [self._check_bucket_async(bucket_config) for bucket_config in self.config]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions from gather
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                bucket_name = self.config[i].bucket if i < len(self.config) else "unknown"
                self.logger.error(f"S3 check failed for {bucket_name}: {result}")
                final_results.append(CollectorResult(
                    collector_name="s3",
                    target_name=bucket_name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message=f"Check failed: {str(result)}",
                    error=str(result)
                ))
            else:
                final_results.append(result)

        return final_results

    async def _check_bucket_async(self, config: S3BucketConfig) -> CollectorResult:
        """
        Async wrapper for S3 bucket check.

        Args:
            config: S3 bucket configuration

        Returns:
            CollectorResult: Bucket check result
        """
        # Run blocking boto3 calls in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._check_bucket, config)

    def _check_bucket(self, config: S3BucketConfig) -> CollectorResult:
        """
        Check single S3 bucket accessibility.

        Args:
            config: S3 bucket configuration

        Returns:
            CollectorResult: Bucket check result
        """
        try:
            # Create S3 client
            s3_client = boto3.client('s3', region_name=config.region)

            # Check 1: Bucket exists and we have access (head_bucket)
            try:
                s3_client.head_bucket(Bucket=config.bucket)
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == '404':
                    return CollectorResult(
                        collector_name="s3",
                        target_name=config.bucket,
                        status=HealthStatus.RED,
                        metrics={
                            "bucket": config.bucket,
                            "region": config.region
                        },
                        message="Bucket not found",
                        error="NoSuchBucket"
                    )
                elif error_code == '403':
                    return CollectorResult(
                        collector_name="s3",
                        target_name=config.bucket,
                        status=HealthStatus.RED,
                        metrics={
                            "bucket": config.bucket,
                            "region": config.region
                        },
                        message="Access denied",
                        error="Forbidden"
                    )
                else:
                    raise

            # Check 2: Get bucket location
            try:
                location_response = s3_client.get_bucket_location(Bucket=config.bucket)
                bucket_region = location_response.get('LocationConstraint') or 'us-east-1'
            except Exception as e:
                self.logger.warning(f"Failed to get bucket location for {config.bucket}: {e}")
                bucket_region = config.region

            # Check 3: List objects (just first page to verify read access)
            try:
                list_response = s3_client.list_objects_v2(
                    Bucket=config.bucket,
                    MaxKeys=1  # Minimal request
                )
                object_count = list_response.get('KeyCount', 0)
                has_contents = object_count > 0
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'AccessDenied':
                    # Bucket exists but we can't list objects
                    return CollectorResult(
                        collector_name="s3",
                        target_name=config.bucket,
                        status=HealthStatus.YELLOW,
                        metrics={
                            "bucket": config.bucket,
                            "region": bucket_region,
                            "accessible": True,
                            "listable": False
                        },
                        message="Bucket accessible but not listable"
                    )
                else:
                    raise

            # Optional: Get bucket versioning status
            try:
                versioning_response = s3_client.get_bucket_versioning(Bucket=config.bucket)
                versioning_status = versioning_response.get('Status', 'Disabled')
            except Exception:
                versioning_status = 'Unknown'

            # Success - bucket is fully accessible
            return CollectorResult(
                collector_name="s3",
                target_name=config.bucket,
                status=HealthStatus.GREEN,
                metrics={
                    "bucket": config.bucket,
                    "region": bucket_region,
                    "accessible": True,
                    "listable": True,
                    "has_objects": has_contents,
                    "versioning": versioning_status
                },
                message=f"Bucket accessible (versioning: {versioning_status})"
            )

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error'].get('Message', str(e))

            return CollectorResult(
                collector_name="s3",
                target_name=config.bucket,
                status=HealthStatus.RED,
                metrics={
                    "bucket": config.bucket,
                    "region": config.region
                },
                message=f"AWS error: {error_code}",
                error=error_message
            )

        except Exception as e:
            return CollectorResult(
                collector_name="s3",
                target_name=config.bucket,
                status=HealthStatus.RED,
                metrics={
                    "bucket": config.bucket,
                    "region": config.region
                },
                message=f"Check failed: {str(e)}",
                error=str(e)
            )
