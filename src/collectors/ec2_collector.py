"""EC2 instance metrics collector via CloudWatch."""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
import logging

try:
    import boto3
except ImportError:
    boto3 = None

from ..config.models import EC2InstanceConfig
from ..utils.status import HealthStatus
from ..utils.metrics import CollectorResult
from .base import BaseCollector, safe_collect


class EC2Collector(BaseCollector):
    """Collector for AWS EC2 instance metrics via CloudWatch."""

    def __init__(
        self,
        config: List[EC2InstanceConfig],
        thresholds: dict,
        logger: logging.Logger
    ):
        """
        Initialize EC2 collector.

        Args:
            config: List of EC2 instance configurations
            thresholds: System thresholds for CPU usage
            logger: Logger instance
        """
        super().__init__(config, thresholds, logger)

    @safe_collect
    async def collect(self) -> List[CollectorResult]:
        """
        Collect metrics from all configured EC2 instances.

        Returns:
            List[CollectorResult]: EC2 instance metrics
        """
        if not self.config:
            self.logger.info("No EC2 instances configured")
            return []

        if boto3 is None:
            return [CollectorResult(
                collector_name="ec2",
                target_name="all",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message="boto3 library not installed",
                error="ImportError: boto3"
            )]

        self.logger.info(f"Checking {len(self.config)} EC2 instance(s)")

        # Run all checks concurrently
        tasks = [self._collect_instance_async(instance_config) for instance_config in self.config]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions from gather
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                instance_name = self.config[i].name if i < len(self.config) else "unknown"
                self.logger.error(f"EC2 check failed for {instance_name}: {result}")
                final_results.append(CollectorResult(
                    collector_name="ec2",
                    target_name=instance_name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message=f"Check failed: {str(result)}",
                    error=str(result)
                ))
            else:
                final_results.append(result)

        return final_results

    async def _collect_instance_async(self, config: EC2InstanceConfig) -> CollectorResult:
        """
        Async wrapper for EC2 metrics collection.

        Args:
            config: EC2 instance configuration

        Returns:
            CollectorResult: Instance metrics result
        """
        # Run blocking boto3 calls in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._collect_instance, config)

    def _collect_instance(self, config: EC2InstanceConfig) -> CollectorResult:
        """
        Collect metrics from single EC2 instance.

        Args:
            config: EC2 instance configuration

        Returns:
            CollectorResult: Instance metrics result
        """
        try:
            # Create AWS clients
            ec2_client = boto3.client('ec2', region_name=config.region)
            cloudwatch_client = boto3.client('cloudwatch', region_name=config.region)

            # Get instance status
            instance_status = self._get_instance_status(ec2_client, config.instance_id)

            # If instance is not running, return early
            if instance_status['state'] != 'running':
                return CollectorResult(
                    collector_name="ec2",
                    target_name=config.name,
                    status=HealthStatus.RED,
                    metrics={
                        "instance_id": config.instance_id,
                        "region": config.region,
                        "state": instance_status['state']
                    },
                    message=f"Instance {instance_status['state']}"
                )

            # Get CloudWatch metrics (last 5 minutes)
            cpu_usage = self._get_cpu_utilization(
                cloudwatch_client,
                config.instance_id,
                minutes=5
            )

            # Determine status based on CPU usage
            if cpu_usage is not None:
                cpu_status = self._determine_status("cpu", cpu_usage, higher_is_worse=True)
            else:
                cpu_status = HealthStatus.YELLOW

            return CollectorResult(
                collector_name="ec2",
                target_name=config.name,
                status=cpu_status,
                metrics={
                    "instance_id": config.instance_id,
                    "region": config.region,
                    "state": instance_status['state'],
                    "cpu_usage_pct": round(cpu_usage, 1) if cpu_usage is not None else None,
                    "instance_type": instance_status.get('instance_type', 'unknown')
                },
                message=f"Running, CPU: {cpu_usage:.1f}%" if cpu_usage is not None else "Running, CPU data unavailable"
            )

        except Exception as e:
            return CollectorResult(
                collector_name="ec2",
                target_name=config.name,
                status=HealthStatus.RED,
                metrics={
                    "instance_id": config.instance_id,
                    "region": config.region
                },
                message=f"Collection failed: {str(e)}",
                error=str(e)
            )

    def _get_instance_status(self, ec2_client, instance_id: str) -> dict:
        """
        Get EC2 instance status.

        Args:
            ec2_client: boto3 EC2 client
            instance_id: EC2 instance ID

        Returns:
            dict: Instance status information

        Raises:
            Exception: If instance not found or API error
        """
        response = ec2_client.describe_instances(InstanceIds=[instance_id])

        if not response['Reservations']:
            raise ValueError(f"Instance {instance_id} not found")

        instance = response['Reservations'][0]['Instances'][0]

        return {
            'state': instance['State']['Name'],  # running, stopped, terminated, etc.
            'instance_type': instance.get('InstanceType', 'unknown'),
            'launch_time': instance.get('LaunchTime')
        }

    def _get_cpu_utilization(
        self,
        cloudwatch_client,
        instance_id: str,
        minutes: int = 5
    ) -> Optional[float]:
        """
        Get average CPU utilization from CloudWatch.

        Args:
            cloudwatch_client: boto3 CloudWatch client
            instance_id: EC2 instance ID
            minutes: Lookback period in minutes

        Returns:
            Optional[float]: Average CPU utilization percentage, or None if no data

        Note:
            CloudWatch metrics have up to 5 minute delay for basic monitoring
        """
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=minutes)

            response = cloudwatch_client.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[
                    {
                        'Name': 'InstanceId',
                        'Value': instance_id
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5 minutes
                Statistics=['Average']
            )

            datapoints = response.get('Datapoints', [])

            if not datapoints:
                self.logger.warning(f"No CPU metrics available for {instance_id}")
                return None

            # Get most recent datapoint
            latest = sorted(datapoints, key=lambda x: x['Timestamp'], reverse=True)[0]
            return latest['Average']

        except Exception as e:
            self.logger.error(f"Failed to get CloudWatch metrics for {instance_id}: {e}")
            return None
