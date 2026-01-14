"""Docker container health check collector via SSH."""

import json
import asyncio
from typing import List, Optional
import logging

from ..config.models import VPSServerConfig
from ..utils.status import HealthStatus
from ..utils.metrics import CollectorResult
from .base import BaseCollector, safe_collect
from .ssh_helper import SSHHelper


class DockerCollector(BaseCollector):
    """Collector for Docker container health checks via SSH."""

    def __init__(
        self,
        config: List[VPSServerConfig],
        thresholds: dict,
        logger: logging.Logger
    ):
        """
        Initialize Docker collector.

        Args:
            config: List of VPS server configurations (same as VPS collector)
            thresholds: System thresholds (not used for Docker checks)
            logger: Logger instance
        """
        super().__init__(config, thresholds, logger)

    @safe_collect
    async def collect(self) -> List[CollectorResult]:
        """
        Collect Docker container statuses from all configured servers.

        Returns:
            List[CollectorResult]: Container health check results
        """
        if not self.config:
            self.logger.info("No Docker servers configured")
            return []

        if not SSHHelper.is_available():
            return [CollectorResult(
                collector_name="docker",
                target_name="all",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message="paramiko library not installed",
                error="ImportError: paramiko"
            )]

        self.logger.info(f"Checking Docker containers on {len(self.config)} server(s)")

        # Run all checks concurrently
        tasks = [self._collect_server_async(server_config) for server_config in self.config]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten results (each server returns multiple containers)
        final_results = []
        for i, result in enumerate(results_nested):
            if isinstance(result, Exception):
                server_name = self.config[i].name if i < len(self.config) else "unknown"
                self.logger.error(f"Docker check failed for {server_name}: {result}")
                final_results.append(CollectorResult(
                    collector_name="docker",
                    target_name=server_name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message=f"Check failed: {str(result)}",
                    error=str(result)
                ))
            elif isinstance(result, list):
                # Server returned multiple container results
                final_results.extend(result)
            else:
                # Server returned single result (likely error)
                final_results.append(result)

        return final_results

    async def _collect_server_async(self, config: VPSServerConfig) -> List[CollectorResult]:
        """
        Async wrapper for Docker container collection.

        Args:
            config: VPS server configuration

        Returns:
            List[CollectorResult]: Container check results from this server
        """
        # Run blocking SSH calls in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._collect_server, config)

    def _collect_server(self, config: VPSServerConfig) -> List[CollectorResult]:
        """
        Collect Docker container statuses from single server.

        Args:
            config: VPS server configuration

        Returns:
            List[CollectorResult]: Container check results
        """
        client = None
        try:
            # Establish SSH connection
            client = SSHHelper.create_client(config, self.logger)

            # Execute docker ps command with JSON format
            # Format: one JSON object per line
            docker_output = SSHHelper.exec_command(
                client,
                'docker ps -a --format "{{json .}}"',
                timeout=15,
                logger=self.logger
            )

            # Parse container list
            containers = self._parse_containers(docker_output)

            if not containers:
                # No containers found
                return [CollectorResult(
                    collector_name="docker",
                    target_name=f"{config.name}/no-containers",
                    status=HealthStatus.YELLOW,
                    metrics={"host": config.host, "server": config.name},
                    message="No containers found"
                )]

            # Create result for each container
            results = []
            for container in containers:
                result = self._check_container(container, config)
                results.append(result)

            return results

        except ImportError as e:
            return [CollectorResult(
                collector_name="docker",
                target_name=config.name,
                status=HealthStatus.UNKNOWN,
                metrics={"host": config.host},
                message=str(e),
                error=str(e)
            )]

        except Exception as e:
            return [CollectorResult(
                collector_name="docker",
                target_name=config.name,
                status=HealthStatus.RED,
                metrics={"host": config.host},
                message=f"Collection failed: {str(e)}",
                error=str(e)
            )]

        finally:
            if client:
                SSHHelper.close_client(client, self.logger)

    def _parse_containers(self, docker_output: str) -> List[dict]:
        """
        Parse docker ps JSON output.

        Args:
            docker_output: Output from docker ps -a --format "{{json .}}"

        Returns:
            List[dict]: Parsed container data

        Example output (one JSON per line):
            {"Command":"nginx -g 'daemon off;'","CreatedAt":"2024-01-15 10:30:45","ID":"abc123","Image":"nginx:latest","Names":"web-server","Ports":"0.0.0.0:80->80/tcp","Status":"Up 2 days"}
            {"Command":"python app.py","CreatedAt":"2024-01-15 10:30:50","ID":"def456","Image":"python:3.11","Names":"api-server","Ports":"0.0.0.0:8000->8000/tcp","Status":"Up 2 days (healthy)"}
        """
        containers = []
        lines = docker_output.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                container_data = json.loads(line)
                containers.append(container_data)
            except json.JSONDecodeError as e:
                self.logger.warning(f"Failed to parse container JSON: {line[:100]} - {e}")
                continue

        return containers

    def _check_container(self, container: dict, server_config: VPSServerConfig) -> CollectorResult:
        """
        Check single container health.

        Args:
            container: Parsed container data from docker ps
            server_config: Server configuration

        Returns:
            CollectorResult: Container health check result
        """
        container_id = container.get('ID', 'unknown')[:12]  # Short ID
        container_name = container.get('Names', 'unknown')
        status_str = container.get('Status', '').lower()
        image = container.get('Image', 'unknown')

        # Target name: server/container
        target_name = f"{server_config.name}/{container_name}"

        # Determine health status from Status field
        # Examples:
        #   "Up 2 days" -> GREEN
        #   "Up 2 days (healthy)" -> GREEN
        #   "Up 2 days (unhealthy)" -> RED
        #   "Restarting (1) 5 seconds ago" -> YELLOW
        #   "Exited (0) 2 hours ago" -> YELLOW
        #   "Exited (1) 2 hours ago" -> RED
        #   "Created" -> YELLOW

        if 'up' in status_str:
            if '(unhealthy)' in status_str:
                status = HealthStatus.RED
                message = "Container unhealthy"
            elif '(healthy)' in status_str or 'healthy' not in status_str:
                # Either explicitly healthy or no health check configured
                status = HealthStatus.GREEN
                message = "Container running"
            else:
                status = HealthStatus.GREEN
                message = "Container running"

        elif 'restarting' in status_str:
            status = HealthStatus.YELLOW
            message = "Container restarting"

        elif 'exited' in status_str:
            # Check exit code
            # Format: "Exited (0) 2 hours ago"
            import re
            match = re.search(r'exited \((\d+)\)', status_str)
            if match:
                exit_code = int(match.group(1))
                if exit_code == 0:
                    status = HealthStatus.YELLOW
                    message = f"Container stopped cleanly (exit {exit_code})"
                else:
                    status = HealthStatus.RED
                    message = f"Container exited with error (exit {exit_code})"
            else:
                status = HealthStatus.YELLOW
                message = "Container stopped"

        elif 'created' in status_str:
            status = HealthStatus.YELLOW
            message = "Container created but not started"

        elif 'dead' in status_str or 'removing' in status_str:
            status = HealthStatus.RED
            message = "Container in error state"

        else:
            status = HealthStatus.UNKNOWN
            message = f"Unknown status: {status_str}"

        return CollectorResult(
            collector_name="docker",
            target_name=target_name,
            status=status,
            metrics={
                "container_id": container_id,
                "image": image,
                "status": container.get('Status', 'unknown'),
                "host": server_config.host,
                "server": server_config.name
            },
            message=message
        )
