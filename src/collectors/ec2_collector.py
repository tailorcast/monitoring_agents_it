"""EC2 instance metrics collector via CloudWatch."""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
import logging

try:
    import boto3
except ImportError:
    boto3 = None

try:
    from langsmith import traceable
except ImportError:
    # Graceful fallback if langsmith not installed
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not args else decorator(args[0])

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

    @traceable(name="EC2Collector._collect_instance")
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

            # Get CloudWatch metrics (last 15 minutes to account for delays)
            cpu_usage = self._get_cpu_utilization(
                cloudwatch_client,
                config.instance_id,
                minutes=15
            )

            # Get disk metrics if monitoring enabled
            disk_free = None
            if config.monitor_disk:
                disk_free = self._get_disk_utilization(
                    cloudwatch_client,
                    config.instance_id,
                    config,
                    minutes=15
                )

            # Determine status for each metric
            if cpu_usage is not None:
                cpu_status = self._determine_status("cpu", cpu_usage, higher_is_worse=True)
            else:
                cpu_status = HealthStatus.YELLOW

            # Determine disk status if monitoring enabled
            if config.monitor_disk:
                if disk_free is not None:
                    disk_status = self._determine_status("disk_free", disk_free, higher_is_worse=False)
                else:
                    # Disk monitoring enabled but metrics unavailable
                    disk_status = HealthStatus.YELLOW
                    self.logger.warning(f"Disk monitoring enabled for {config.name} but metrics unavailable")
            else:
                disk_status = None  # Not monitoring disk

            # Overall status (worst wins) - only consider enabled metrics
            statuses = [cpu_status]
            if disk_status is not None:
                statuses.append(disk_status)

            if HealthStatus.RED in statuses:
                overall_status = HealthStatus.RED
            elif HealthStatus.YELLOW in statuses:
                overall_status = HealthStatus.YELLOW
            else:
                overall_status = HealthStatus.GREEN

            # Build metrics dict
            metrics = {
                "instance_id": config.instance_id,
                "region": config.region,
                "state": instance_status['state'],
                "cpu_usage_pct": round(cpu_usage, 1) if cpu_usage is not None else None,
                "instance_type": instance_status.get('instance_type', 'unknown')
            }

            # Add disk metrics if monitoring enabled
            if config.monitor_disk:
                metrics["disk_free_pct"] = round(disk_free, 1) if disk_free is not None else None

            # Build human-readable message
            message_parts = []
            if cpu_usage is not None:
                message_parts.append(f"CPU: {cpu_usage:.1f}%")
            else:
                message_parts.append("CPU: unavailable")

            if config.monitor_disk:
                if disk_free is not None:
                    message_parts.append(f"Disk free: {disk_free:.1f}%")
                else:
                    message_parts.append("Disk: unavailable")

            message = f"Running, {', '.join(message_parts)}"

            return CollectorResult(
                collector_name="ec2",
                target_name=config.name,
                status=overall_status,
                metrics=metrics,
                message=message
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

    @traceable(name="EC2Collector._get_cpu_utilization")
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

    @traceable(name="EC2Collector._get_disk_utilization")
    def _get_disk_utilization(
        self,
        cloudwatch_client,
        instance_id: str,
        config: EC2InstanceConfig,
        minutes: int = 15
    ) -> Optional[float]:
        """
        Get disk free percentage from CloudWatch Agent metrics.

        Args:
            cloudwatch_client: boto3 CloudWatch client
            instance_id: EC2 instance ID
            config: EC2 instance configuration
            minutes: Lookback period in minutes

        Returns:
            Optional[float]: Disk free percentage (calculated from used), or None if no data

        Note:
            CloudWatch Agent publishes metrics to 'CWAgent' namespace with dimensions:
            - InstanceId
            - path (mount point)
            - device (e.g., nvme0n1p1, xvda1)
            - fstype (e.g., ext4, xfs)

            We query disk_used_percent and convert to disk_free_pct for consistency
            with threshold logic (disk_free_red: 10, disk_free_yellow: 20).
        """
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=minutes)

            # Build dimensions - only include non-None values
            dimensions = [
                {'Name': 'InstanceId', 'Value': instance_id},
                {'Name': 'path', 'Value': config.disk_path}
            ]

            # Add optional dimensions if configured
            if config.disk_device:
                dimensions.append({'Name': 'device', 'Value': config.disk_device})
            if config.disk_fstype:
                dimensions.append({'Name': 'fstype', 'Value': config.disk_fstype})

            # Try with specified dimensions first
            response = cloudwatch_client.get_metric_statistics(
                Namespace=config.disk_namespace,
                MetricName='disk_used_percent',
                Dimensions=dimensions,
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5 minutes
                Statistics=['Average']
            )

            datapoints = response.get('Datapoints', [])

            # If no data and device/fstype not specified, try listing metrics to find them
            if not datapoints and (not config.disk_device or not config.disk_fstype):
                self.logger.info(f"No disk metrics with specified dimensions for {instance_id}, attempting auto-discovery")

                # List available metrics to find device/fstype
                list_response = cloudwatch_client.list_metrics(
                    Namespace=config.disk_namespace,
                    MetricName='disk_used_percent',
                    Dimensions=[
                        {'Name': 'InstanceId', 'Value': instance_id},
                        {'Name': 'path', 'Value': config.disk_path}
                    ]
                )

                metrics = list_response.get('Metrics', [])
                if metrics:
                    # Use first available metric's dimensions
                    discovered_dimensions = metrics[0]['Dimensions']
                    self.logger.info(f"Auto-discovered disk metric dimensions for {instance_id}: {discovered_dimensions}")

                    # Retry with discovered dimensions
                    response = cloudwatch_client.get_metric_statistics(
                        Namespace=config.disk_namespace,
                        MetricName='disk_used_percent',
                        Dimensions=discovered_dimensions,
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=300,
                        Statistics=['Average']
                    )
                    datapoints = response.get('Datapoints', [])

            if not datapoints:
                self.logger.warning(
                    f"No disk metrics available for {instance_id} at path {config.disk_path}. "
                    "Ensure CloudWatch Agent is installed and configured."
                )
                return None

            # Get most recent datapoint
            latest = sorted(datapoints, key=lambda x: x['Timestamp'], reverse=True)[0]
            disk_used_pct = latest['Average']

            # Convert to disk_free_pct for consistency with thresholds
            disk_free_pct = 100.0 - disk_used_pct

            return disk_free_pct

        except Exception as e:
            self.logger.error(f"Failed to get disk metrics for {instance_id}: {e}")
            return None
