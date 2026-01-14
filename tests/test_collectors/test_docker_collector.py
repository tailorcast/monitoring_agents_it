"""Tests for Docker collector."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from src.collectors.docker_collector import DockerCollector
from src.utils.status import HealthStatus

# Fixtures imported from conftest.py: vps_configs, thresholds, logger
# Note: Docker collector uses VPS server configs for SSH access


@pytest.fixture
def mock_docker_outputs():
    """Create mock docker ps JSON outputs."""
    return {
        'healthy': json.dumps({
            "Command": "nginx -g 'daemon off;'",
            "CreatedAt": "2024-01-15 10:30:45",
            "ID": "abc123def456",
            "Image": "nginx:latest",
            "Names": "web-server",
            "Ports": "0.0.0.0:80->80/tcp",
            "Status": "Up 2 days (healthy)"
        }),
        'unhealthy': json.dumps({
            "Command": "python app.py",
            "CreatedAt": "2024-01-15 10:30:50",
            "ID": "def456ghi789",
            "Image": "python:3.11",
            "Names": "api-server",
            "Ports": "0.0.0.0:8000->8000/tcp",
            "Status": "Up 2 days (unhealthy)"
        }),
        'stopped': json.dumps({
            "Command": "/bin/sh",
            "CreatedAt": "2024-01-14 10:00:00",
            "ID": "ghi789jkl012",
            "Image": "alpine:latest",
            "Names": "worker",
            "Ports": "",
            "Status": "Exited (1) 2 hours ago"
        }),
        'restarting': json.dumps({
            "Command": "node server.js",
            "CreatedAt": "2024-01-15 11:00:00",
            "ID": "jkl012mno345",
            "Image": "node:18",
            "Names": "frontend",
            "Ports": "3000/tcp",
            "Status": "Restarting (1) 5 seconds ago"
        })
    }


@pytest.mark.asyncio
async def test_docker_collector_healthy_containers(vps_configs, thresholds, logger, mock_docker_outputs):
    """Test Docker collector with healthy containers."""
    collector = DockerCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.docker_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock docker ps output with healthy container
        mock_ssh.exec_command.return_value = mock_docker_outputs['healthy']

        # Execute
        results = await collector.collect()

        # Verify
        assert len(results) == 1
        assert results[0].collector_name == "docker"
        assert results[0].target_name == "docker-host-01/web-server"
        assert results[0].status == HealthStatus.GREEN
        assert "container_id" in results[0].metrics
        assert results[0].metrics["image"] == "nginx:latest"


@pytest.mark.asyncio
async def test_docker_collector_unhealthy_container(vps_configs, thresholds, logger, mock_docker_outputs):
    """Test Docker collector with unhealthy container (RED)."""
    collector = DockerCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.docker_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock docker ps output with unhealthy container
        mock_ssh.exec_command.return_value = mock_docker_outputs['unhealthy']

        # Execute
        results = await collector.collect()

        # Verify RED status for unhealthy container
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert "unhealthy" in results[0].message.lower()


@pytest.mark.asyncio
async def test_docker_collector_stopped_container(vps_configs, thresholds, logger, mock_docker_outputs):
    """Test Docker collector with stopped container."""
    collector = DockerCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.docker_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock docker ps output with exited container
        mock_ssh.exec_command.return_value = mock_docker_outputs['stopped']

        # Execute
        results = await collector.collect()

        # Verify RED status for stopped container with error exit code
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert "exit" in results[0].message.lower() or "stop" in results[0].message.lower()


@pytest.mark.asyncio
async def test_docker_collector_restarting_container(vps_configs, thresholds, logger, mock_docker_outputs):
    """Test Docker collector with restarting container (YELLOW)."""
    collector = DockerCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.docker_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock docker ps output with restarting container
        mock_ssh.exec_command.return_value = mock_docker_outputs['restarting']

        # Execute
        results = await collector.collect()

        # Verify YELLOW status for restarting container
        assert len(results) == 1
        assert results[0].status == HealthStatus.YELLOW
        assert "restart" in results[0].message.lower()


@pytest.mark.asyncio
async def test_docker_collector_multiple_containers(vps_configs, thresholds, logger, mock_docker_outputs):
    """Test Docker collector with multiple containers."""
    collector = DockerCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.docker_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock docker ps output with multiple containers (one per line)
        docker_output = "\n".join([
            mock_docker_outputs['healthy'],
            mock_docker_outputs['unhealthy'],
            mock_docker_outputs['stopped']
        ])

        mock_ssh.exec_command.return_value = docker_output

        # Execute
        results = await collector.collect()

        # Verify all containers checked
        assert len(results) == 3
        assert any(r.status == HealthStatus.GREEN for r in results)
        assert any(r.status == HealthStatus.RED for r in results)


@pytest.mark.asyncio
async def test_docker_collector_no_containers(vps_configs, thresholds, logger):
    """Test Docker collector when no containers found."""
    collector = DockerCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.docker_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock empty docker ps output
        mock_ssh.exec_command.return_value = ""

        # Execute
        results = await collector.collect()

        # Should return YELLOW status for no containers
        assert len(results) == 1
        assert results[0].status == HealthStatus.YELLOW
        assert "no containers" in results[0].message.lower()


@pytest.mark.asyncio
async def test_docker_collector_ssh_connection_failure(vps_configs, thresholds, logger):
    """Test SSH connection failure (RED)."""
    collector = DockerCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.docker_collector.SSHHelper') as mock_ssh:
        mock_ssh.is_available.return_value = True
        mock_ssh.create_client.side_effect = Exception("Connection refused")

        # Execute
        results = await collector.collect()

        # Verify RED status
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED


@pytest.mark.asyncio
async def test_docker_collector_no_paramiko(vps_configs, thresholds, logger):
    """Test graceful handling when paramiko not installed."""
    collector = DockerCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.docker_collector.SSHHelper') as mock_ssh:
        mock_ssh.is_available.return_value = False

        results = await collector.collect()

        # Should return single UNKNOWN result
        assert len(results) == 1
        assert results[0].status == HealthStatus.UNKNOWN
        assert "paramiko" in results[0].message.lower()


@pytest.mark.asyncio
async def test_docker_collector_empty_config(thresholds, logger):
    """Test collector with no servers configured."""
    collector = DockerCollector([], thresholds, logger)

    results = await collector.collect()

    # Should return empty list
    assert len(results) == 0


@pytest.mark.asyncio
async def test_docker_collector_invalid_json(vps_configs, thresholds, logger):
    """Test handling of invalid JSON in docker ps output."""
    collector = DockerCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.docker_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock invalid JSON output
        mock_ssh.exec_command.return_value = "not valid json\n{broken json"

        # Execute
        results = await collector.collect()

        # Should handle parsing error gracefully
        # Either return YELLOW for no valid containers or continue with valid ones
        assert len(results) >= 1


@pytest.mark.asyncio
async def test_docker_collector_exit_code_zero(vps_configs, thresholds, logger):
    """Test stopped container with exit code 0 (YELLOW not RED)."""
    collector = DockerCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.docker_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock stopped container with exit code 0
        stopped_clean = json.dumps({
            "Command": "echo done",
            "ID": "abc123",
            "Image": "alpine",
            "Names": "one-time-job",
            "Status": "Exited (0) 1 hour ago"
        })

        mock_ssh.exec_command.return_value = stopped_clean

        # Execute
        results = await collector.collect()

        # Verify YELLOW (not RED) for clean exit
        assert len(results) == 1
        assert results[0].status == HealthStatus.YELLOW
        assert "0" in results[0].message or "clean" in results[0].message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
