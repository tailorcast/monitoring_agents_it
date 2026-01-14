"""Daily LLM budget tracker to prevent cost overruns."""

import json
from pathlib import Path
from datetime import date
import logging


class BudgetTracker:
    """
    Track daily LLM costs and enforce spending limits.

    Persists daily spending to file and automatically resets
    at midnight. Prevents requests when daily budget exceeded.
    """

    # Claude Haiku 3.5 pricing (as of January 2025)
    # Source: https://aws.amazon.com/bedrock/pricing/
    INPUT_PRICE_PER_1M = 0.80   # $0.80 per 1M input tokens
    OUTPUT_PRICE_PER_1M = 4.00  # $4.00 per 1M output tokens

    def __init__(self, daily_budget_usd: float, state_file: str = "/tmp/budget_state.json", logger: logging.Logger = None):
        """
        Initialize budget tracker.

        Args:
            daily_budget_usd: Maximum daily spend in USD
            state_file: Path to persist budget state
            logger: Optional logger instance
        """
        self.daily_budget = daily_budget_usd
        self.state_file = Path(state_file)
        self.logger = logger or logging.getLogger(__name__)

        # Load existing state or initialize
        self._load_state()

        self.logger.info(f"Budget tracker initialized: ${daily_budget_usd}/day limit, ${self.today_spent:.4f} spent today")

    def can_make_request(self, estimated_tokens: int = 10000) -> bool:
        """
        Check if request is within budget.

        Args:
            estimated_tokens: Estimated total tokens (input + output)
                            Default 10k assumes ~5k input, ~5k output

        Returns:
            bool: True if request would be within budget
        """
        # Conservative estimate: assume equal input/output split
        estimated_input = estimated_tokens // 2
        estimated_output = estimated_tokens // 2

        estimated_cost = self._calculate_cost(estimated_input, estimated_output)

        can_proceed = (self.today_spent + estimated_cost) < self.daily_budget

        if not can_proceed:
            self.logger.warning(
                f"Budget exceeded: ${self.today_spent:.4f} + ${estimated_cost:.4f} >= ${self.daily_budget:.2f}"
            )

        return can_proceed

    def record_usage(self, input_tokens: int, output_tokens: int):
        """
        Record token usage and update costs.

        Args:
            input_tokens: Number of input tokens consumed
            output_tokens: Number of output tokens generated
        """
        cost = self._calculate_cost(input_tokens, output_tokens)

        self.today_spent += cost
        self._save_state()

        self.logger.info(
            f"Recorded LLM usage: {input_tokens} in, {output_tokens} out = ${cost:.4f} "
            f"(total today: ${self.today_spent:.4f}/{self.daily_budget:.2f})"
        )

    def get_budget_status(self) -> dict:
        """
        Return current budget status.

        Returns:
            dict: Budget status with keys:
                - daily_limit: Daily budget in USD
                - spent_today: Amount spent today in USD
                - remaining: Remaining budget in USD
                - utilization_pct: Percentage of budget used
        """
        remaining = max(0, self.daily_budget - self.today_spent)
        utilization_pct = (self.today_spent / self.daily_budget) * 100 if self.daily_budget > 0 else 0

        return {
            "daily_limit": self.daily_budget,
            "spent_today": self.today_spent,
            "remaining": remaining,
            "utilization_pct": utilization_pct
        }

    def should_alert_budget(self, threshold: float = 0.8) -> bool:
        """
        Check if budget alert threshold exceeded.

        Args:
            threshold: Alert when budget utilization exceeds this ratio (0-1)

        Returns:
            bool: True if alert should be triggered
        """
        return self.today_spent >= (self.daily_budget * threshold)

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost for given token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            float: Cost in USD
        """
        input_cost = (input_tokens / 1_000_000) * self.INPUT_PRICE_PER_1M
        output_cost = (output_tokens / 1_000_000) * self.OUTPUT_PRICE_PER_1M

        return input_cost + output_cost

    def _load_state(self):
        """
        Load daily spending from file.

        If file exists and date matches today, restore spending.
        Otherwise, start fresh (new day or first run).
        """
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                # Check if state is from today
                state_date = state.get('date')
                today_str = str(date.today())

                if state_date == today_str:
                    # Restore today's spending
                    self.today_spent = state.get('spent', 0.0)
                    self.logger.info(f"Restored budget state from {state_date}: ${self.today_spent:.4f}")
                else:
                    # New day - reset spending
                    self.today_spent = 0.0
                    self.logger.info(f"New day detected ({state_date} -> {today_str}), resetting budget")

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                self.logger.warning(f"Failed to load budget state: {e}, starting fresh")
                self.today_spent = 0.0
        else:
            # No state file - first run
            self.today_spent = 0.0
            self.logger.info("No existing budget state, starting fresh")

    def _save_state(self):
        """
        Persist daily spending to file.

        Creates parent directory if needed.
        """
        try:
            # Ensure parent directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            # Save state
            state = {
                'date': str(date.today()),
                'spent': self.today_spent,
                'budget': self.daily_budget
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

            self.logger.debug(f"Saved budget state to {self.state_file}")

        except Exception as e:
            self.logger.error(f"Failed to save budget state: {e}")
