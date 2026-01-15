"""Tests for BaseCollector class."""

import pytest
from src.collectors.base import BaseCollector
from src.utils.status import HealthStatus
from src.utils.metrics import CollectorResult


class MockCollector(BaseCollector):
    """Mock collector for testing BaseCollector functionality."""

    def __init__(self, config=None, thresholds=None, logger=None):
        import logging
        if logger is None:
            logger = logging.getLogger(__name__)
        super().__init__(config or [], thresholds or {}, logger)

    async def collect(self):
        """Mock collect method."""
        return []


class TestBaseCollector:
    """Test suite for BaseCollector."""

    def test_determine_status_higher_is_worse_red(self):
        """Test status determination for metrics where higher is worse - RED."""
        collector = MockCollector(thresholds={
            "cpu_red": 90,
            "cpu_yellow": 70
        })

        status = collector._determine_status("cpu", 95, higher_is_worse=True)
        assert status == HealthStatus.RED

    def test_determine_status_higher_is_worse_yellow(self):
        """Test status determination for metrics where higher is worse - YELLOW."""
        collector = MockCollector(thresholds={
            "cpu_red": 90,
            "cpu_yellow": 70
        })

        status = collector._determine_status("cpu", 75, higher_is_worse=True)
        assert status == HealthStatus.YELLOW

    def test_determine_status_higher_is_worse_green(self):
        """Test status determination for metrics where higher is worse - GREEN."""
        collector = MockCollector(thresholds={
            "cpu_red": 90,
            "cpu_yellow": 70
        })

        status = collector._determine_status("cpu", 50, higher_is_worse=True)
        assert status == HealthStatus.GREEN

    def test_determine_status_lower_is_worse_red(self):
        """Test status determination for metrics where lower is worse - RED."""
        collector = MockCollector(thresholds={
            "disk_free_red": 10,
            "disk_free_yellow": 20
        })

        status = collector._determine_status("disk_free", 5, higher_is_worse=False)
        assert status == HealthStatus.RED

    def test_determine_status_lower_is_worse_yellow(self):
        """Test status determination for metrics where lower is worse - YELLOW."""
        collector = MockCollector(thresholds={
            "disk_free_red": 10,
            "disk_free_yellow": 20
        })

        status = collector._determine_status("disk_free", 15, higher_is_worse=False)
        assert status == HealthStatus.YELLOW

    def test_determine_status_lower_is_worse_green(self):
        """Test status determination for metrics where lower is worse - GREEN."""
        collector = MockCollector(thresholds={
            "disk_free_red": 10,
            "disk_free_yellow": 20
        })

        status = collector._determine_status("disk_free", 50, higher_is_worse=False)
        assert status == HealthStatus.GREEN

    def test_determine_status_boundary_red(self):
        """Test status determination at exact red threshold."""
        collector = MockCollector(thresholds={
            "cpu_red": 90,
            "cpu_yellow": 70
        })

        # Exactly at red threshold should be RED
        assert collector._determine_status("cpu", 90, higher_is_worse=True) == HealthStatus.RED

    def test_determine_status_boundary_yellow(self):
        """Test status determination at exact yellow threshold."""
        collector = MockCollector(thresholds={
            "cpu_red": 90,
            "cpu_yellow": 70
        })

        # Exactly at yellow threshold should be YELLOW
        assert collector._determine_status("cpu", 70, higher_is_worse=True) == HealthStatus.YELLOW

    def test_determine_status_missing_thresholds(self):
        """Test status determination when thresholds are missing."""
        collector = MockCollector(thresholds={})

        # Should return UNKNOWN when thresholds missing
        status = collector._determine_status("cpu", 95, higher_is_worse=True)
        assert status == HealthStatus.UNKNOWN

    def test_determine_status_ram_thresholds(self):
        """Test RAM status determination (higher is worse)."""
        collector = MockCollector(thresholds={
            "ram_red": 90,
            "ram_yellow": 70
        })

        assert collector._determine_status("ram", 95, higher_is_worse=True) == HealthStatus.RED
        assert collector._determine_status("ram", 80, higher_is_worse=True) == HealthStatus.YELLOW
        assert collector._determine_status("ram", 50, higher_is_worse=True) == HealthStatus.GREEN

    def test_determine_status_partial_thresholds_only_red(self):
        """Test status when only red threshold is defined."""
        collector = MockCollector(thresholds={
            "cpu_red": 90
        })

        # Without yellow threshold, should return UNKNOWN
        assert collector._determine_status("cpu", 95, higher_is_worse=True) == HealthStatus.UNKNOWN
        assert collector._determine_status("cpu", 50, higher_is_worse=True) == HealthStatus.UNKNOWN

    def test_determine_status_partial_thresholds_only_yellow(self):
        """Test status when only yellow threshold is defined."""
        collector = MockCollector(thresholds={
            "cpu_yellow": 70
        })

        # Without red threshold, should return UNKNOWN
        assert collector._determine_status("cpu", 95, higher_is_worse=True) == HealthStatus.UNKNOWN
        assert collector._determine_status("cpu", 50, higher_is_worse=True) == HealthStatus.UNKNOWN

    def test_collector_initialization_with_config(self):
        """Test collector initialization with configuration."""
        config = [{"name": "test-target"}]
        thresholds = {"cpu_red": 90, "cpu_yellow": 70}

        collector = MockCollector(config, thresholds)

        assert collector.config == config
        assert collector.thresholds == thresholds
        assert collector.logger is not None

    def test_collector_initialization_without_config(self):
        """Test collector initialization without configuration."""
        collector = MockCollector()

        assert collector.config == []
        assert collector.thresholds == {}
        assert collector.logger is not None

    def test_collector_logger_hierarchy(self):
        """Test that collector creates child logger."""
        import logging

        parent_logger = logging.getLogger("test_parent")
        collector = MockCollector(logger=parent_logger)

        assert collector.logger.parent == parent_logger or collector.logger == parent_logger

    @pytest.mark.asyncio
    async def test_collect_method_exists(self):
        """Test that collect method is callable."""
        collector = MockCollector()
        result = await collector.collect()

        assert isinstance(result, list)

    def test_threshold_combinations(self):
        """Test various threshold value combinations."""
        # Test case 1: Normal thresholds
        collector = MockCollector(thresholds={
            "metric_red": 90,
            "metric_yellow": 70
        })

        assert collector._determine_status("metric", 100, True) == HealthStatus.RED
        assert collector._determine_status("metric", 80, True) == HealthStatus.YELLOW
        assert collector._determine_status("metric", 60, True) == HealthStatus.GREEN

        # Test case 2: Inverted threshold order (yellow > red)
        # This is unusual but should still work based on comparison logic
        collector2 = MockCollector(thresholds={
            "metric_red": 10,
            "metric_yellow": 20
        })

        assert collector2._determine_status("metric", 5, False) == HealthStatus.RED
        assert collector2._determine_status("metric", 15, False) == HealthStatus.YELLOW
        assert collector2._determine_status("metric", 25, False) == HealthStatus.GREEN

    def test_zero_thresholds(self):
        """Test handling of zero threshold values."""
        collector = MockCollector(thresholds={
            "metric_red": 0,
            "metric_yellow": 0
        })

        # Any value >= 0 should trigger thresholds
        assert collector._determine_status("metric", 0, True) == HealthStatus.RED
        assert collector._determine_status("metric", -1, True) == HealthStatus.GREEN

    def test_negative_values(self):
        """Test status determination with negative metric values."""
        collector = MockCollector(thresholds={
            "metric_red": 10,
            "metric_yellow": 5
        })

        # Negative value should be GREEN for higher_is_worse
        assert collector._determine_status("metric", -5, True) == HealthStatus.GREEN

    def test_float_thresholds(self):
        """Test status determination with float threshold values."""
        collector = MockCollector(thresholds={
            "metric_red": 90.5,
            "metric_yellow": 70.2
        })

        assert collector._determine_status("metric", 91.0, True) == HealthStatus.RED
        assert collector._determine_status("metric", 75.5, True) == HealthStatus.YELLOW
        assert collector._determine_status("metric", 65.0, True) == HealthStatus.GREEN

    def test_float_metric_values(self):
        """Test status determination with float metric values."""
        collector = MockCollector(thresholds={
            "metric_red": 90,
            "metric_yellow": 70
        })

        assert collector._determine_status("metric", 90.1, True) == HealthStatus.RED
        assert collector._determine_status("metric", 70.5, True) == HealthStatus.YELLOW
        assert collector._determine_status("metric", 69.9, True) == HealthStatus.GREEN
