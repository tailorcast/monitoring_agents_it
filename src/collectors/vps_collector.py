"""VPS server metrics collector via SSH."""

import re
import asyncio
from typing import List, Optional
import logging

try:
    from langsmith import traceable
except ImportError:
    # Graceful fallback if langsmith not installed
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not args else decorator(args[0])

from ..config.models import VPSServerConfig
from ..utils.status import HealthStatus
from ..utils.metrics import CollectorResult
from .base import BaseCollector, safe_collect
from .ssh_helper import SSHHelper


class VPSCollector(BaseCollector):
    """Collector for VPS server system metrics via SSH."""

    def __init__(
        self,
        config: List[VPSServerConfig],
        thresholds: dict,
        logger: logging.Logger
    ):
        """
        Initialize VPS collector.

        Args:
            config: List of VPS server configurations
            thresholds: System thresholds for CPU, RAM, disk
            logger: Logger instance
        """
        super().__init__(config, thresholds, logger)

    @safe_collect
    async def collect(self) -> List[CollectorResult]:
        """
        Collect metrics from all configured VPS servers.

        Returns:
            List[CollectorResult]: System metrics for all VPS servers
        """
        if not self.config:
            self.logger.info("No VPS servers configured")
            return []

        if not SSHHelper.is_available():
            return [CollectorResult(
                collector_name="vps",
                target_name="all",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message="paramiko library not installed",
                error="ImportError: paramiko"
            )]

        self.logger.info(f"Checking {len(self.config)} VPS server(s)")

        # Run all checks concurrently
        tasks = [self._collect_server_async(server_config) for server_config in self.config]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions from gather
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                server_name = self.config[i].name if i < len(self.config) else "unknown"
                self.logger.error(f"VPS check failed for {server_name}: {result}")
                final_results.append(CollectorResult(
                    collector_name="vps",
                    target_name=server_name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message=f"Check failed: {str(result)}",
                    error=str(result)
                ))
            else:
                final_results.append(result)

        return final_results

    async def _collect_server_async(self, config: VPSServerConfig) -> CollectorResult:
        """
        Async wrapper for VPS metrics collection.

        Args:
            config: VPS server configuration

        Returns:
            CollectorResult: Server metrics result
        """
        # Run blocking SSH calls in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._collect_server, config)

    @traceable(name="VPSCollector._collect_server")
    def _collect_server(self, config: VPSServerConfig) -> CollectorResult:
        """
        Collect system metrics from single VPS server.

        Args:
            config: VPS server configuration

        Returns:
            CollectorResult: Server metrics result
        """
        client = None
        try:
            # Establish SSH connection
            client = SSHHelper.create_client(config, self.logger)

            # Execute system commands
            top_output = SSHHelper.exec_command(client, "top -bn1", timeout=10, logger=self.logger)
            free_output = SSHHelper.exec_command(client, "free -m", timeout=10, logger=self.logger)
            df_output = SSHHelper.exec_command(client, "df -h", timeout=10, logger=self.logger)

            # Parse metrics
            cpu_usage = self._parse_cpu(top_output)
            ram_usage = self._parse_memory(free_output)
            disk_free = self._parse_disk(df_output)

            # Determine status for each metric
            cpu_status = self._determine_status("cpu", cpu_usage, higher_is_worse=True)
            ram_status = self._determine_status("ram", ram_usage, higher_is_worse=True)
            disk_status = self._determine_status("disk_free", disk_free, higher_is_worse=False)

            # Overall status (worst wins)
            statuses = [cpu_status, ram_status, disk_status]
            if HealthStatus.RED in statuses:
                overall_status = HealthStatus.RED
            elif HealthStatus.YELLOW in statuses:
                overall_status = HealthStatus.YELLOW
            else:
                overall_status = HealthStatus.GREEN

            return CollectorResult(
                collector_name="vps",
                target_name=config.name,
                status=overall_status,
                metrics={
                    "cpu_usage_pct": round(cpu_usage, 1),
                    "ram_usage_pct": round(ram_usage, 1),
                    "disk_free_pct": round(disk_free, 1),
                    "host": config.host
                },
                message=f"CPU: {cpu_usage:.1f}%, RAM: {ram_usage:.1f}%, Disk free: {disk_free:.1f}%"
            )

        except ImportError as e:
            return CollectorResult(
                collector_name="vps",
                target_name=config.name,
                status=HealthStatus.UNKNOWN,
                metrics={"host": config.host},
                message=str(e),
                error=str(e)
            )

        except Exception as e:
            return CollectorResult(
                collector_name="vps",
                target_name=config.name,
                status=HealthStatus.RED,
                metrics={"host": config.host},
                message=f"Collection failed: {str(e)}",
                error=str(e)
            )

        finally:
            if client:
                SSHHelper.close_client(client, self.logger)

    def _parse_cpu(self, top_output: str) -> float:
        """
        Parse CPU usage from top command output.

        Args:
            top_output: Output from 'top -bn1' command

        Returns:
            float: CPU usage percentage

        Raises:
            ValueError: If parsing fails

        Example top output:
            %Cpu(s):  5.2 us,  2.1 sy,  0.0 ni, 92.4 id,  0.2 wa,  0.0 hi,  0.1 si,  0.0 st
        """
        # Look for CPU line
        match = re.search(r'%?Cpu\(s\):\s*([\d.]+)\s+us,\s*([\d.]+)\s+sy', top_output)
        if match:
            user_cpu = float(match.group(1))
            system_cpu = float(match.group(2))
            return user_cpu + system_cpu

        # Alternative format (some systems)
        match = re.search(r'%?Cpu\(s\):\s*([\d.]+)%?\s+us', top_output)
        if match:
            return float(match.group(1))

        # Try to find idle CPU and calculate usage
        match = re.search(r'([\d.]+)\s+id', top_output)
        if match:
            idle_cpu = float(match.group(1))
            return 100.0 - idle_cpu

        raise ValueError(f"Cannot parse CPU from top output: {top_output[:200]}")

    def _parse_memory(self, free_output: str) -> float:
        """
        Parse memory usage from free command output.

        Args:
            free_output: Output from 'free -m' command

        Returns:
            float: Memory usage percentage

        Raises:
            ValueError: If parsing fails

        Example free output:
                      total        used        free      shared  buff/cache   available
            Mem:           7822        1234        5678         123        910        6123
        """
        lines = free_output.strip().split('\n')

        # Find memory line (usually second line, starts with "Mem:")
        for line in lines:
            if line.startswith('Mem:'):
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        total = float(parts[1])
                        used = float(parts[2])
                        if total > 0:
                            return (used / total) * 100
                    except (ValueError, IndexError):
                        pass

        raise ValueError(f"Cannot parse memory from free output: {free_output[:200]}")

    def _parse_disk(self, df_output: str) -> float:
        """
        Parse root partition free space from df command output.

        Args:
            df_output: Output from 'df -h' command

        Returns:
            float: Disk free space percentage

        Raises:
            ValueError: If parsing fails

        Example df output:
            Filesystem      Size  Used Avail Use% Mounted on
            /dev/sda1        50G   30G   18G  63% /
        """
        lines = df_output.strip().split('\n')

        # Skip header line
        for line in lines[1:]:
            # Look for root partition (mounted on /)
            parts = line.split()
            if len(parts) >= 6 and parts[-1] == '/':
                # Use% column (e.g., "63%")
                use_percent_str = parts[-2]
                try:
                    # Remove % sign and convert
                    use_percent = float(use_percent_str.rstrip('%'))
                    return 100.0 - use_percent
                except ValueError:
                    pass

        raise ValueError(f"Cannot find root partition in df output: {df_output[:200]}")
