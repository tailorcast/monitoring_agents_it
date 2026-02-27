"""Tests for MetricHistoryStore service."""

import json
import pytest
from datetime import date
from pathlib import Path

from src.services.metric_history import MetricHistoryStore
from src.utils.metrics import CollectorResult
from src.utils.status import HealthStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def history_file(tmp_path):
    """Return path to a history file inside a tmp directory."""
    return str(tmp_path / "metric_history.json")


@pytest.fixture
def store(history_file):
    """MetricHistoryStore backed by a temp file."""
    return MetricHistoryStore(history_file=history_file)


@pytest.fixture
def thresholds():
    """Minimal thresholds dict matching ThresholdsConfig defaults."""
    return {
        "cpu_red": 90,
        "cpu_yellow": 70,
        "ram_red": 90,
        "ram_yellow": 70,
        "disk_free_red": 10,
        "disk_free_yellow": 20,
        "api_timeout_ms": 5000,
        "api_slow_ms": 2000,
    }


def make_result(collector_name, target_name, metrics, status=HealthStatus.RED, error=None):
    return CollectorResult(
        collector_name=collector_name,
        target_name=target_name,
        status=status,
        metrics=metrics,
        message=f"{collector_name}:{target_name} test result",
        error=error,
    )


# ---------------------------------------------------------------------------
# Basic count operations
# ---------------------------------------------------------------------------

class TestGetAndIncrement:
    def test_initial_count_is_zero(self, store):
        assert store.get_daily_count("vps:my-server:cpu_usage_pct") == 0

    def test_increment_increases_count(self, store):
        key = "vps:my-server:cpu_usage_pct"
        store.increment(key)
        assert store.get_daily_count(key) == 1

    def test_multiple_increments(self, store):
        key = "ec2:prod-01:cpu_usage_pct"
        store.increment(key)
        store.increment(key)
        store.increment(key)
        assert store.get_daily_count(key) == 3

    def test_different_keys_are_independent(self, store):
        store.increment("vps:srv1:cpu_usage_pct")
        store.increment("vps:srv2:cpu_usage_pct")
        assert store.get_daily_count("vps:srv1:cpu_usage_pct") == 1
        assert store.get_daily_count("vps:srv2:cpu_usage_pct") == 1
        assert store.get_daily_count("vps:srv3:cpu_usage_pct") == 0


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_counts_persist_across_instances(self, history_file):
        s1 = MetricHistoryStore(history_file=history_file)
        s1.increment("vps:server:cpu_usage_pct")

        s2 = MetricHistoryStore(history_file=history_file)
        assert s2.get_daily_count("vps:server:cpu_usage_pct") == 1

    def test_file_format(self, history_file):
        store = MetricHistoryStore(history_file=history_file)
        store.increment("ec2:i-123:cpu_usage_pct")

        with open(history_file) as f:
            data = json.load(f)

        assert data["date"] == str(date.today())
        assert "ec2:i-123:cpu_usage_pct" in data["incidents"]
        assert data["incidents"]["ec2:i-123:cpu_usage_pct"]["count"] == 1
        assert "first_seen" in data["incidents"]["ec2:i-123:cpu_usage_pct"]
        assert "last_seen" in data["incidents"]["ec2:i-123:cpu_usage_pct"]


# ---------------------------------------------------------------------------
# Daily reset on date change
# ---------------------------------------------------------------------------

class TestDailyReset:
    def test_stale_date_resets_counts(self, history_file):
        # Write a state file with a past date
        stale_state = {
            "date": "2020-01-01",
            "incidents": {
                "vps:server:cpu_usage_pct": {
                    "count": 5,
                    "first_seen": "2020-01-01T00:00:00",
                    "last_seen": "2020-01-01T00:00:00",
                }
            },
        }
        Path(history_file).parent.mkdir(parents=True, exist_ok=True)
        with open(history_file, "w") as f:
            json.dump(stale_state, f)

        store = MetricHistoryStore(history_file=history_file)
        # Old key should be gone — count resets to 0
        assert store.get_daily_count("vps:server:cpu_usage_pct") == 0

    def test_same_date_restores_counts(self, history_file):
        today = str(date.today())
        existing_state = {
            "date": today,
            "incidents": {
                "vps:server:ram_usage_pct": {
                    "count": 3,
                    "first_seen": "2026-02-27T08:00:00",
                    "last_seen": "2026-02-27T10:00:00",
                }
            },
        }
        Path(history_file).parent.mkdir(parents=True, exist_ok=True)
        with open(history_file, "w") as f:
            json.dump(existing_state, f)

        store = MetricHistoryStore(history_file=history_file)
        assert store.get_daily_count("vps:server:ram_usage_pct") == 3


# ---------------------------------------------------------------------------
# get_red_metric_keys
# ---------------------------------------------------------------------------

class TestGetRedMetricKeys:
    def test_connection_failure_bypasses_dampening(self, store, thresholds):
        result = make_result(
            "vps", "my-server",
            {"cpu_usage_pct": 95},
            error="Connection refused",
        )
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == []

    def test_binary_collector_returns_empty(self, store, thresholds):
        # Docker is not in THRESHOLD_METRICS — binary check only
        result = make_result(
            "docker", "my-server",
            {"containers_running": 0, "containers_expected": 3},
        )
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == []

    def test_database_collector_returns_empty(self, store, thresholds):
        result = make_result(
            "database", "prod-db",
            {"connected": False},
        )
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == []

    def test_vps_cpu_above_threshold(self, store, thresholds):
        result = make_result("vps", "kz-vps-01", {"cpu_usage_pct": 95})
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == ["vps:kz-vps-01:cpu_usage_pct"]

    def test_vps_cpu_below_threshold_not_included(self, store, thresholds):
        result = make_result("vps", "kz-vps-01", {"cpu_usage_pct": 50})
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == []

    def test_vps_disk_free_below_threshold(self, store, thresholds):
        # disk_free_red = 10, lower is worse, 5% free → RED
        result = make_result("vps", "kz-vps-01", {"disk_free_pct": 5})
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == ["vps:kz-vps-01:disk_free_pct"]

    def test_vps_disk_free_above_threshold_not_included(self, store, thresholds):
        result = make_result("vps", "kz-vps-01", {"disk_free_pct": 50})
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == []

    def test_ec2_cpu_above_threshold(self, store, thresholds):
        result = make_result("ec2", "prod-api", {"cpu_usage_pct": 92})
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == ["ec2:prod-api:cpu_usage_pct"]

    def test_api_response_time_above_threshold(self, store, thresholds):
        result = make_result("api", "Main API", {"response_time_ms": 6000})
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == ["api:Main API:response_time_ms"]

    def test_multiple_metrics_both_breached(self, store, thresholds):
        result = make_result(
            "vps", "my-server",
            {"cpu_usage_pct": 95, "ram_usage_pct": 92},
        )
        keys = store.get_red_metric_keys(result, thresholds)
        assert set(keys) == {
            "vps:my-server:cpu_usage_pct",
            "vps:my-server:ram_usage_pct",
        }

    def test_metric_missing_from_result(self, store, thresholds):
        # Result has no cpu_usage_pct key
        result = make_result("vps", "my-server", {"ram_usage_pct": 95})
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == ["vps:my-server:ram_usage_pct"]

    def test_threshold_at_exact_boundary_higher_is_worse(self, store, thresholds):
        # cpu_red = 90 → exactly 90 should be RED
        result = make_result("vps", "my-server", {"cpu_usage_pct": 90})
        keys = store.get_red_metric_keys(result, thresholds)
        assert "vps:my-server:cpu_usage_pct" in keys

    def test_threshold_at_exact_boundary_lower_is_worse(self, store, thresholds):
        # disk_free_red = 10 → exactly 10 should be RED
        result = make_result("vps", "my-server", {"disk_free_pct": 10})
        keys = store.get_red_metric_keys(result, thresholds)
        assert "vps:my-server:disk_free_pct" in keys


# ---------------------------------------------------------------------------
# Dampening logic scenarios (simulating workflow node behaviour)
# ---------------------------------------------------------------------------

class TestDampeningScenarios:
    """
    Directly exercise the dampening logic that the _history_filter node uses:
    check counts, increment, and verify outcome.
    """

    def test_first_occurrence_should_downgrade(self, store, thresholds):
        result = make_result("vps", "kz-vps-01", {"cpu_usage_pct": 95})
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys  # threshold keys found

        all_first = all(store.get_daily_count(k) == 0 for k in keys)
        assert all_first is True  # → should downgrade to YELLOW

        for k in keys:
            store.increment(k)

    def test_second_occurrence_stays_red(self, store, thresholds):
        result = make_result("vps", "kz-vps-01", {"cpu_usage_pct": 95})
        keys = store.get_red_metric_keys(result, thresholds)

        # Simulate first run
        for k in keys:
            store.increment(k)

        # Second run — count is now 1
        all_first = all(store.get_daily_count(k) == 0 for k in keys)
        assert all_first is False  # → stays RED

        for k in keys:
            store.increment(k)

        assert store.get_daily_count(keys[0]) == 2

    def test_mixed_metrics_any_prior_count_stays_red(self, store, thresholds):
        """
        CPU is first-occurrence, RAM has prior count → overall result stays RED.
        """
        result = make_result(
            "vps", "my-server",
            {"cpu_usage_pct": 95, "ram_usage_pct": 92},
        )
        keys = store.get_red_metric_keys(result, thresholds)
        assert len(keys) == 2

        # Pre-record one occurrence for RAM only
        ram_key = "vps:my-server:ram_usage_pct"
        store.increment(ram_key)

        # Check: CPU is first (count=0), RAM already seen (count=1)
        all_first = all(store.get_daily_count(k) == 0 for k in keys)
        assert all_first is False  # → stays RED

    def test_connection_failure_bypasses_dampening(self, store, thresholds):
        result = make_result(
            "vps", "my-server",
            {"cpu_usage_pct": 95},
            error="SSH timeout",
        )
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == []  # no keys → binary/connection failure path, no downgrade

    def test_binary_check_bypasses_dampening(self, store, thresholds):
        result = make_result(
            "docker", "my-server",
            {"containers_running": 0},
        )
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == []  # no keys → stays RED

    def test_green_result_untouched(self, store, thresholds):
        result = make_result(
            "vps", "kz-vps-01",
            {"cpu_usage_pct": 30},
            status=HealthStatus.GREEN,
        )
        # Workflow only calls get_red_metric_keys for RED results,
        # but we verify the store itself returns proper data
        keys = store.get_red_metric_keys(result, thresholds)
        assert keys == []  # cpu not above red threshold
