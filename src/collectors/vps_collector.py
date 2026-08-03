"""VPS server metrics collector via SSH."""

import asyncio
import time
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
from ..utils.sanitize import sanitize_error
from .base import BaseCollector, safe_collect
from .host_lock import get_host_lock
from .ssh_helper import SSHHelper


class VPSCollector(BaseCollector):
    """Collector for VPS server system metrics via SSH."""

    # Seconds to wait after SSH login (and after the RAM/disk commands) before
    # taking the first /proc/stat snapshot, so the cost of logging in is not
    # counted as host load.
    CPU_SETTLE_SECONDS = 2

    # Width of the /proc/stat sampling window in seconds. This is a spot sample
    # of instantaneous load — alerting is driven by load average instead, see
    # _load_status(). Kept short since it only feeds a reported metric now.
    CPU_SAMPLE_SECONDS = 3

    # 5-minute load average per core. 1.0 = CPUs exactly saturated, so RED at
    # 2.0 means work has been queuing at twice capacity for minutes. Overridable
    # via load_red / load_yellow in the thresholds config.
    DEFAULT_LOAD_RED = 2.0
    DEFAULT_LOAD_YELLOW = 1.0

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
        # Serialize with the Docker/DockerLogs collectors targeting this same
        # host, so their work is not counted as this host's CPU load.
        async with get_host_lock(config.host):
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
            free_output = SSHHelper.exec_command(client, "free -m", timeout=10, logger=self.logger)
            df_output = SSHHelper.exec_command(client, "df -h", timeout=10, logger=self.logger)

            # Load average is the primary CPU signal: the kernel maintains it
            # over 1/5/15 minutes, so it reflects sustained pressure and cannot
            # be skewed by whatever happens during our own SSH session.
            loadavg_output = SSHHelper.exec_command(
                client, "cat /proc/loadavg", timeout=10, logger=self.logger
            )
            nproc_output = SSHHelper.exec_command(
                client, "nproc", timeout=10, logger=self.logger
            )

            # Short settle so SSH login cost falls outside the spot sample.
            time.sleep(self.CPU_SETTLE_SECONDS)

            # Instantaneous CPU: two /proc/stat snapshots with a local sleep in
            # between. Python-side sleep avoids depending on the remote PATH
            # having 'sleep'. Reported for visibility, but too short a window to
            # alarm on — a single cron job or log rotation saturates it.
            stat_reading1 = SSHHelper.exec_command(
                client, "head -1 /proc/stat", timeout=10, logger=self.logger
            )
            time.sleep(self.CPU_SAMPLE_SECONDS)
            stat_reading2 = SSHHelper.exec_command(
                client, "head -1 /proc/stat", timeout=10, logger=self.logger
            )
            cpu_stat_output = stat_reading1.strip() + "\n" + stat_reading2.strip()

            # Parse metrics
            cpu_usage = self._parse_cpu(cpu_stat_output)
            ram_usage = self._parse_memory(free_output)
            disk_free = self._parse_disk(df_output)
            load_1, load_5, load_15 = self._parse_loadavg(loadavg_output)
            cpu_count = self._parse_nproc(nproc_output)

            # Load per core: 1.0 means the CPUs are exactly saturated.
            load_per_core = load_5 / cpu_count

            # Determine status for each metric. CPU status comes from load
            # average, not the spot sample.
            cpu_status = self._load_status(load_per_core)
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
                    "load_per_core": round(load_per_core, 2),
                    "load_1m": round(load_1, 2),
                    "load_5m": round(load_5, 2),
                    "load_15m": round(load_15, 2),
                    "cpu_count": cpu_count,
                    "cpu_sample_pct": round(cpu_usage, 1),
                    "ram_usage_pct": round(ram_usage, 1),
                    "disk_free_pct": round(disk_free, 1),
                    "host": config.host
                },
                message=(
                    f"Load: {load_per_core:.2f}/core ({load_1:.2f}, {load_5:.2f}, "
                    f"{load_15:.2f} over 1/5/15m on {cpu_count} vCPU), "
                    f"RAM: {ram_usage:.1f}%, Disk free: {disk_free:.1f}%"
                )
            )

        except ImportError as e:
            safe_msg = sanitize_error(e)
            return CollectorResult(
                collector_name="vps",
                target_name=config.name,
                status=HealthStatus.UNKNOWN,
                metrics={},
                message=safe_msg,
                error=safe_msg
            )

        except Exception as e:
            self.logger.error(f"VPS collection failed for {config.name}: {e}")
            safe_msg = sanitize_error(e)
            return CollectorResult(
                collector_name="vps",
                target_name=config.name,
                status=HealthStatus.RED,
                metrics={},
                message=f"Collection failed: {safe_msg}",
                error=safe_msg
            )

        finally:
            if client:
                SSHHelper.close_client(client, self.logger)

    def _load_status(self, load_per_core: float) -> HealthStatus:
        """
        Determine CPU health from 5-minute load average per core.

        Load per core is the run-queue length normalized by CPU count: 1.0 means
        the CPUs are exactly saturated, above 1.0 means work is queuing. This is
        used instead of a CPU percentage because a percentage sampled over a few
        seconds cannot distinguish a saturated host from a brief burst.

        Thresholds come from `load_red`/`load_yellow` when configured, so the
        defaults below can be tuned per deployment.

        Args:
            load_per_core: 5-minute load average divided by CPU count

        Returns:
            HealthStatus: GREEN, YELLOW, or RED
        """
        red = self.thresholds.get("load_red", self.DEFAULT_LOAD_RED)
        yellow = self.thresholds.get("load_yellow", self.DEFAULT_LOAD_YELLOW)

        if load_per_core >= red:
            return HealthStatus.RED
        if load_per_core >= yellow:
            return HealthStatus.YELLOW
        return HealthStatus.GREEN

    def _parse_loadavg(self, loadavg_output: str) -> tuple:
        """
        Parse the 1/5/15-minute load averages from /proc/loadavg.

        /proc/loadavg format:
            0.52 0.58 0.59 1/1234 56789

        Args:
            loadavg_output: Contents of /proc/loadavg

        Returns:
            tuple: (load_1m, load_5m, load_15m) as floats

        Raises:
            ValueError: If parsing fails
        """
        parts = loadavg_output.strip().split()

        if len(parts) < 3:
            raise ValueError(f"Cannot parse /proc/loadavg: {loadavg_output[:200]}")

        try:
            return float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError as e:
            raise ValueError(f"Cannot parse /proc/loadavg values: {e}")

    def _parse_nproc(self, nproc_output: str) -> int:
        """
        Parse the CPU count from nproc output.

        Args:
            nproc_output: Output from 'nproc'

        Returns:
            int: Number of CPUs (at least 1)

        Raises:
            ValueError: If parsing fails
        """
        try:
            count = int(nproc_output.strip())
        except ValueError as e:
            raise ValueError(f"Cannot parse nproc output: {e}")

        if count < 1:
            raise ValueError(f"Implausible CPU count from nproc: {count}")

        return count

    def _parse_cpu(self, stat_output: str) -> float:
        """
        Parse CPU usage from two /proc/stat readings taken CPU_SAMPLE_SECONDS apart.

        /proc/stat 'cpu' line format:
            cpu  user nice system idle iowait irq softirq steal [guest guest_nice]

        All values are cumulative jiffies since boot, summed across all CPUs.
        The percentage is automatically normalized to 0-100% regardless of
        core count.

        Args:
            stat_output: Two /proc/stat 'cpu' lines joined by newline

        Returns:
            float: CPU usage percentage (0-100)

        Raises:
            ValueError: If parsing fails
        """
        lines = [
            line.strip() for line in stat_output.strip().split('\n')
            if line.strip().startswith('cpu ')
        ]

        if len(lines) < 2:
            raise ValueError(
                f"Expected 2 cpu lines from /proc/stat, got {len(lines)}: "
                f"{stat_output[:200]}"
            )

        def parse_cpu_line(line: str) -> list:
            # parts[0] is 'cpu', rest are numeric jiffie counters
            return [int(x) for x in line.split()[1:]]

        try:
            values1 = parse_cpu_line(lines[0])
            values2 = parse_cpu_line(lines[1])
        except (ValueError, IndexError) as e:
            raise ValueError(f"Cannot parse /proc/stat cpu line: {e}")

        deltas = [v2 - v1 for v1, v2 in zip(values1, values2)]
        total = sum(deltas)
        if total == 0:
            return 0.0

        # idle is index 3, iowait is index 4
        idle = deltas[3] + (deltas[4] if len(deltas) > 4 else 0)

        return ((total - idle) / total) * 100.0

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
