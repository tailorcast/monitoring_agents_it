"""Docker container logs error monitoring collector via SSH."""

import asyncio
from typing import List
import logging

from ..config.models import DockerLogsTargetConfig
from ..utils.status import HealthStatus
from ..utils.metrics import CollectorResult
from .base import BaseCollector, safe_collect
from .ssh_helper import SSHHelper


class DockerLogsCollector(BaseCollector):
    """Collector that monitors error counts in Docker container logs via SSH."""

    def __init__(
        self,
        config: List[DockerLogsTargetConfig],
        thresholds: dict,
        logger: logging.Logger
    ):
        super().__init__(config, thresholds, logger)

    @safe_collect
    async def collect(self) -> List[CollectorResult]:
        if not self.config:
            self.logger.info("No Docker logs targets configured")
            return []

        if not SSHHelper.is_available():
            return [CollectorResult(
                collector_name="dockerlogs",
                target_name="all",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message="paramiko library not installed",
                error="ImportError: paramiko"
            )]

        self.logger.info(f"Checking Docker logs on {len(self.config)} target(s)")

        tasks = [self._collect_target_async(target) for target in self.config]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)

        final_results = []
        for i, result in enumerate(results_nested):
            if isinstance(result, Exception):
                target_name = self.config[i].name if i < len(self.config) else "unknown"
                self.logger.error(f"Docker logs check failed for {target_name}: {result}")
                final_results.append(CollectorResult(
                    collector_name="dockerlogs",
                    target_name=target_name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message=f"Check failed: {str(result)}",
                    error=str(result)
                ))
            elif isinstance(result, list):
                final_results.extend(result)
            else:
                final_results.append(result)

        return final_results

    async def _collect_target_async(self, target: DockerLogsTargetConfig) -> List[CollectorResult]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._collect_target, target)

    def _collect_target(self, target: DockerLogsTargetConfig) -> List[CollectorResult]:
        client = None
        try:
            client = SSHHelper.create_client(target, self.logger)

            patterns = target.error_patterns or "error|exception|fatal"

            # Wrap in subshell: grep -c outputs "0" on no match but exits 1,
            # so we capture the count and always exit 0
            cmd_4h = (
                f"COUNT=$(docker compose -f {target.compose_file} logs --since 4h 2>&1"
                f" | grep -ci '{patterns}' || true) && echo $COUNT"
            )
            cmd_24h = (
                f"COUNT=$(docker compose -f {target.compose_file} logs --since 24h 2>&1"
                f" | grep -ci '{patterns}' || true) && echo $COUNT"
            )

            errors_4h = self._run_grep_count(client, cmd_4h)
            errors_24h = self._run_grep_count(client, cmd_24h)

            # Determine status based on thresholds
            status = self._determine_log_status(errors_4h, errors_24h)

            # Calculate hourly rates for context
            rate_4h = errors_4h / 4.0
            rate_24h = errors_24h / 24.0

            if status == HealthStatus.GREEN:
                message = f"Errors: {errors_4h} (4h), {errors_24h} (24h)"
            elif status == HealthStatus.RED:
                message = f"High error rate: {errors_4h} (4h), {errors_24h} (24h)"
            else:
                message = f"Elevated errors: {errors_4h} (4h), {errors_24h} (24h)"

            return [CollectorResult(
                collector_name="dockerlogs",
                target_name=target.name,
                status=status,
                metrics={
                    "errors_4h": errors_4h,
                    "errors_24h": errors_24h,
                    "rate_per_hour_4h": round(rate_4h, 1),
                    "rate_per_hour_24h": round(rate_24h, 1),
                    "host": target.host,
                    "compose_file": target.compose_file,
                },
                message=message
            )]

        except Exception as e:
            return [CollectorResult(
                collector_name="dockerlogs",
                target_name=target.name,
                status=HealthStatus.RED,
                metrics={"host": target.host},
                message=f"Collection failed: {str(e)}",
                error=str(e)
            )]

        finally:
            if client:
                SSHHelper.close_client(client, self.logger)

    def _run_grep_count(self, client, command: str) -> int:
        """Run a grep -c command and return the count. grep returns exit 1 when no matches."""
        try:
            output = SSHHelper.exec_command(client, command, timeout=30, logger=self.logger)
            return int(output.strip())
        except RuntimeError:
            # grep -c returns exit code 1 when no matches found — that means 0 errors
            return 0

    def _determine_log_status(self, errors_4h: int, errors_24h: int) -> HealthStatus:
        """Determine health status based on error counts and thresholds."""
        red_4h = self.thresholds.get("docker_logs_errors_4h_red", 50)
        yellow_4h = self.thresholds.get("docker_logs_errors_4h_yellow", 20)
        red_24h = self.thresholds.get("docker_logs_errors_24h_red", 200)
        yellow_24h = self.thresholds.get("docker_logs_errors_24h_yellow", 100)

        if errors_4h >= red_4h or errors_24h >= red_24h:
            return HealthStatus.RED
        elif errors_4h >= yellow_4h or errors_24h >= yellow_24h:
            return HealthStatus.YELLOW
        else:
            return HealthStatus.GREEN
