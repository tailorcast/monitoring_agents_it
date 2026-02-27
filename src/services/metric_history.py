"""Daily per-metric incident history for alert dampening."""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import List

from ..utils.metrics import CollectorResult
from ..utils.status import HealthStatus


class MetricHistoryStore:
    """
    Track daily per-metric incident counts for threshold-breach dampening.

    Persists incident counts to a JSON file and resets automatically
    when the date changes. A RED result on its first occurrence today
    is downgraded to YELLOW by the history_filter workflow node.
    """

    # Maps (collector_name, metric_key) → (threshold_config_key, higher_is_worse)
    # Only threshold-based numeric metrics are included. Binary checks
    # (Docker container down, DB connection failure, S3 inaccessible) are absent.
    THRESHOLD_METRICS = {
        ("vps", "cpu_usage_pct"):    ("cpu_red", True),
        ("vps", "ram_usage_pct"):    ("ram_red", True),
        ("vps", "disk_free_pct"):    ("disk_free_red", False),
        ("ec2", "cpu_usage_pct"):    ("cpu_red", True),
        ("ec2", "disk_free_pct"):    ("disk_free_red", False),
        ("api", "response_time_ms"): ("api_timeout_ms", True),
    }

    def __init__(
        self,
        history_file: str = "./data/metric_history.json",
        logger: logging.Logger = None,
    ):
        """
        Initialize metric history store.

        Args:
            history_file: Path to persist incident history
            logger: Optional logger instance
        """
        self.history_file = Path(history_file)
        self.logger = logger or logging.getLogger(__name__)

        self._load_state()
        self.logger.info(
            f"MetricHistoryStore initialized from {self.history_file} "
            f"({len(self._incidents)} incident key(s) today)"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_daily_count(self, key: str) -> int:
        """Return today's incident count for the given history key, 0 if unseen."""
        return self._incidents.get(key, {}).get("count", 0)

    def increment(self, key: str) -> None:
        """Record one occurrence for a history key and persist the file."""
        now = datetime.utcnow().isoformat()

        if key not in self._incidents:
            self._incidents[key] = {"count": 0, "first_seen": now, "last_seen": now}

        self._incidents[key]["count"] += 1
        self._incidents[key]["last_seen"] = now
        self._save_state()

    def get_red_metric_keys(
        self, result: CollectorResult, thresholds: dict
    ) -> List[str]:
        """
        Re-evaluate which threshold-based metrics in *result* are crossing RED.

        Args:
            result: A CollectorResult whose overall status is RED.
            thresholds: Dict of threshold values (from ThresholdsConfig.__dict__).

        Returns:
            List of history keys (e.g. "vps:kz-vps-01:cpu_usage_pct") for every
            metric that independently exceeds its RED threshold.
            Returns [] if result.error is not None (connection failures bypass
            dampening) or if no threshold metrics exist for this collector.
        """
        if result.error is not None:
            return []

        keys = []
        for (cname, metric_key), (threshold_key, higher_is_worse) in self.THRESHOLD_METRICS.items():
            if cname != result.collector_name:
                continue

            raw_value = result.metrics.get(metric_key)
            if raw_value is None:
                continue

            threshold_val = thresholds.get(threshold_key)
            if threshold_val is None:
                continue

            if higher_is_worse:
                breached = float(raw_value) >= float(threshold_val)
            else:
                breached = float(raw_value) <= float(threshold_val)

            if breached:
                history_key = f"{result.collector_name}:{result.target_name}:{metric_key}"
                keys.append(history_key)

        return keys

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """Load incident counts from file, resetting if date has changed."""
        today_str = str(date.today())

        if self.history_file.exists():
            try:
                with open(self.history_file, "r") as f:
                    state = json.load(f)

                if state.get("date") == today_str:
                    self._incidents = state.get("incidents", {})
                    self.logger.info(
                        f"Restored metric history from {state['date']}: "
                        f"{len(self._incidents)} key(s)"
                    )
                else:
                    self._incidents = {}
                    self.logger.info(
                        f"New day ({state.get('date')} → {today_str}), resetting metric history"
                    )
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                self.logger.warning(f"Failed to load metric history: {e}, starting fresh")
                self._incidents = {}
        else:
            self._incidents = {}
            self.logger.info("No existing metric history, starting fresh")

    def _save_state(self) -> None:
        """Persist incident counts to file, creating parent dirs as needed."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)

            state = {
                "date": str(date.today()),
                "incidents": self._incidents,
            }

            with open(self.history_file, "w") as f:
                json.dump(state, f, indent=2)

            self.logger.debug(f"Saved metric history to {self.history_file}")

        except Exception as e:
            self.logger.error(f"Failed to save metric history: {e}")
