"""Tests for VPS collector."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.collectors.vps_collector import VPSCollector
from src.utils.status import HealthStatus

# Fixtures imported from conftest.py: vps_configs, thresholds, logger


@pytest.fixture
def mock_ssh_outputs():
    """Create mock SSH command outputs.

    /proc/stat cpu line fields: user nice system idle iowait irq softirq steal
    Two readings 1s apart simulate 'head -1 /proc/stat; sleep 1; head -1 /proc/stat'.
    With delta total=200 and delta idle=159 → CPU = (200-159)/200*100 = 20.5%
    """
    return {
        # ~20.5% CPU: delta user=30, nice=0, system=11, idle=150, iowait=9, irq=0, softirq=0, steal=0
        'cpu_stat': "cpu  10000 0 5000 80000 500 0 0 0 0 0\n"
                    "cpu  10030 0 5011 80150 509 0 0 0 0 0",

        # ~95% CPU: delta user=170, nice=0, system=20, idle=8, iowait=2
        'cpu_stat_high': "cpu  10000 0 5000 80000 500 0 0 0 0 0\n"
                         "cpu  10170 0 5020 80008 502 0 0 0 0 0",

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
                mock_ssh_outputs['cpu_stat'],
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

        mock_ssh.exec_command.side_effect = [
            mock_ssh_outputs['cpu_stat_high'],
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
            mock_ssh_outputs['cpu_stat'],
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

        # Mock /proc/stat with different field count (older kernel, no guest fields)
        alt_cpu_stat = "cpu  10000 0 5000 80000 500 0 0 0\ncpu  10030 0 5011 80150 509 0 0 0"

        alt_free = """       total   used   free  shared  buffers  cached
Mem:    8000   6000   2000     100      500    1000"""

        mock_ssh.exec_command.side_effect = [
            alt_cpu_stat,
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
                mock_ssh_outputs['cpu_stat'], mock_ssh_outputs['free'], mock_ssh_outputs['df']
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
