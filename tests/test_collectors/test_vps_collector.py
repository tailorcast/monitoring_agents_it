"""Tests for VPS collector."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.collectors.vps_collector import VPSCollector
from src.utils.status import HealthStatus

# Fixtures imported from conftest.py: vps_configs, thresholds, logger


@pytest.fixture
def mock_ssh_outputs():
    """Create mock SSH command outputs."""
    return {
        'top': """top - 10:30:45 up 5 days, 12:30,  1 user,  load average: 0.50, 0.60, 0.70
Tasks: 150 total,   1 running, 149 sleeping,   0 stopped,   0 zombie
%Cpu(s): 15.2 us,  5.1 sy,  0.0 ni, 79.0 id,  0.5 wa,  0.0 hi,  0.2 si,  0.0 st
KiB Mem :  8192000 total,  2048000 free,  4096000 used,  2048000 buff/cache
KiB Swap:  2048000 total,  2048000 free,        0 used.  3072000 avail Mem""",

        'free': """              total        used        free      shared  buff/cache   available
Mem:           8000        5000        1500         200        1500        2000
Swap:          2000           0        2000""",

        'df': """Filesystem     1K-blocks    Used Available Use% Mounted on
/dev/sda1       51474912 30880896  20594016  60% /
tmpfs            4096000        0   4096000   0% /dev/shm
/dev/sdb1      103809024 83047219  20761805  81% /data"""
    }


@pytest.mark.asyncio
async def test_vps_collector_success(vps_configs, thresholds, logger, mock_ssh_outputs):
    """Test successful VPS health checks using real config."""
    collector = VPSCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.vps_collector.SSHHelper') as mock_ssh:
        # Mock SSH operations
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock SSH outputs for all configured servers
        outputs = []
        for _ in vps_configs:
            outputs.extend([
                mock_ssh_outputs['top'],
                mock_ssh_outputs['free'],
                mock_ssh_outputs['df']
            ])

        mock_ssh.exec_command.side_effect = outputs

        # Execute
        results = await collector.collect()

        # Verify
        assert len(results) == len(vps_configs)

        # Check all servers
        for i, result in enumerate(results):
            assert result.collector_name == "vps"
            assert result.target_name == vps_configs[i].name
            assert result.status in [HealthStatus.GREEN, HealthStatus.YELLOW]
            assert "cpu_usage_pct" in result.metrics
            assert "ram_usage_pct" in result.metrics
            assert "disk_free_pct" in result.metrics


@pytest.mark.asyncio
async def test_vps_collector_high_cpu(vps_configs, thresholds, logger, mock_ssh_outputs):
    """Test VPS with high CPU usage (RED)."""
    collector = VPSCollector([vps_configs[0]], thresholds, logger)

    with patch('src.collectors.vps_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock high CPU output
        high_cpu_output = mock_ssh_outputs['top'].replace('15.2 us,  5.1 sy', '85.0 us, 10.0 sy')

        mock_ssh.exec_command.side_effect = [
            high_cpu_output,
            mock_ssh_outputs['free'],
            mock_ssh_outputs['df']
        ]

        # Execute
        results = await collector.collect()

        # Verify RED status for high CPU
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert results[0].metrics["cpu_usage_pct"] >= thresholds["cpu_red"]


@pytest.mark.asyncio
async def test_vps_collector_low_disk(vps_configs, thresholds, logger, mock_ssh_outputs):
    """Test VPS with low disk space (YELLOW/RED)."""
    collector = VPSCollector([vps_configs[0]], thresholds, logger)

    with patch('src.collectors.vps_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock low disk output (95% used = 5% free)
        low_disk_output = """Filesystem     1K-blocks    Used Available Use% Mounted on
/dev/sda1       51474912 48901160   2573752  95% /"""

        mock_ssh.exec_command.side_effect = [
            mock_ssh_outputs['top'],
            mock_ssh_outputs['free'],
            low_disk_output
        ]

        # Execute
        results = await collector.collect()

        # Verify RED status for low disk
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert results[0].metrics["disk_free_pct"] <= thresholds["disk_free_red"]


@pytest.mark.asyncio
async def test_vps_collector_ssh_connection_failure(vps_configs, thresholds, logger):
    """Test SSH connection failure (RED)."""
    collector = VPSCollector([vps_configs[0]], thresholds, logger)

    with patch('src.collectors.vps_collector.SSHHelper') as mock_ssh:
        mock_ssh.is_available.return_value = True
        mock_ssh.create_client.side_effect = Exception("Connection refused")

        # Execute
        results = await collector.collect()

        # Verify RED status
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert "connection" in results[0].message.lower() or "refused" in results[0].error.lower()


@pytest.mark.asyncio
async def test_vps_collector_command_execution_failure(vps_configs, thresholds, logger):
    """Test SSH command execution failure (RED)."""
    collector = VPSCollector([vps_configs[0]], thresholds, logger)

    with patch('src.collectors.vps_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True
        mock_ssh.exec_command.side_effect = Exception("Command failed")

        # Execute
        results = await collector.collect()

        # Verify RED status
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED


@pytest.mark.asyncio
async def test_vps_collector_no_paramiko(vps_configs, thresholds, logger):
    """Test graceful handling when paramiko not installed."""
    collector = VPSCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.vps_collector.SSHHelper') as mock_ssh:
        mock_ssh.is_available.return_value = False

        results = await collector.collect()

        # Should return single UNKNOWN result
        assert len(results) == 1
        assert results[0].status == HealthStatus.UNKNOWN
        assert "paramiko" in results[0].message.lower()


@pytest.mark.asyncio
async def test_vps_collector_empty_config(thresholds, logger):
    """Test collector with no servers configured."""
    collector = VPSCollector([], thresholds, logger)

    results = await collector.collect()

    # Should return empty list
    assert len(results) == 0


@pytest.mark.asyncio
async def test_vps_collector_parsing_edge_cases(vps_configs, thresholds, logger):
    """Test parsing of various Linux output formats."""
    collector = VPSCollector([vps_configs[0]], thresholds, logger)

    with patch('src.collectors.vps_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock alternative output format (different Linux distribution)
        alt_top = """top - 10:30:45 up 5 days
%Cpu(s): 20.5 us,  3.2 sy,  0.0 ni, 75.0 id,  1.3 wa,  0.0 hi,  0.0 si,  0.0 st"""

        alt_free = """       total   used   free  shared  buffers  cached
Mem:    8000   6000   2000     100      500    1000"""

        mock_ssh.exec_command.side_effect = [
            alt_top,
            alt_free,
            "Filesystem     Size  Used Avail Use% Mounted on\n/dev/sda1       50G   30G   20G  60% /"
        ]

        # Execute
        results = await collector.collect()

        # Should handle alternative formats
        assert len(results) == 1
        # May succeed or fail parsing, but should not crash
        assert results[0].status in [HealthStatus.GREEN, HealthStatus.YELLOW, HealthStatus.RED, HealthStatus.UNKNOWN]


@pytest.mark.asyncio
async def test_vps_collector_parallel_execution(vps_configs, thresholds, logger, mock_ssh_outputs):
    """Test that multiple servers are checked in parallel."""
    # Use all configured servers from vps_configs
    collector = VPSCollector(vps_configs, thresholds, logger)

    with patch('src.collectors.vps_collector.SSHHelper') as mock_ssh:
        mock_client = MagicMock()
        mock_ssh.create_client.return_value = mock_client
        mock_ssh.is_available.return_value = True

        # Mock SSH outputs for all configured servers
        outputs = []
        for _ in vps_configs:
            outputs.extend([
                mock_ssh_outputs['top'], mock_ssh_outputs['free'], mock_ssh_outputs['df']
            ])
        mock_ssh.exec_command.side_effect = outputs

        # Execute
        import time
        start = time.time()
        results = await collector.collect()
        duration = time.time() - start

        # Should complete quickly (parallel execution)
        assert duration < 2.0
        assert len(results) == len(vps_configs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
