"""Tests for BudgetTracker service."""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import date
from src.services.budget_tracker import BudgetTracker


class TestBudgetTracker:
    """Test suite for BudgetTracker."""

    def test_initialization(self):
        """Test budget tracker initialization."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tracker = BudgetTracker(daily_budget_usd=3.0, state_file=f.name)

            assert tracker.daily_budget == 3.0
            assert tracker.today_spent == 0.0
            assert tracker.state_file == Path(f.name)

    def test_cost_calculation(self):
        """Test accurate cost calculation with Haiku pricing."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tracker = BudgetTracker(daily_budget_usd=3.0, state_file=f.name)

            # Test cost calculation
            # Input: 10,000 tokens @ $0.80/1M = $0.008
            # Output: 2,000 tokens @ $4.00/1M = $0.008
            # Total: $0.016
            cost = tracker._calculate_cost(input_tokens=10000, output_tokens=2000)
            expected_cost = (10000 / 1_000_000) * 0.80 + (2000 / 1_000_000) * 4.00
            assert abs(cost - expected_cost) < 0.0001
            assert abs(cost - 0.016) < 0.0001

    def test_record_usage(self):
        """Test recording token usage and updating costs."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tracker = BudgetTracker(daily_budget_usd=3.0, state_file=f.name)

            # Record usage
            tracker.record_usage(input_tokens=10000, output_tokens=2000)

            # Check spending updated
            expected_cost = (10000 / 1_000_000) * 0.80 + (2000 / 1_000_000) * 4.00
            assert abs(tracker.today_spent - expected_cost) < 0.0001

            # Record more usage
            tracker.record_usage(input_tokens=5000, output_tokens=1000)

            # Check cumulative spending
            total_expected = expected_cost + (5000 / 1_000_000) * 0.80 + (1000 / 1_000_000) * 4.00
            assert abs(tracker.today_spent - total_expected) < 0.0001

    def test_budget_enforcement(self):
        """Test that budget prevents requests when exceeded."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            # Very low budget for testing
            tracker = BudgetTracker(daily_budget_usd=0.01, state_file=f.name)

            # Should allow initial request
            assert tracker.can_make_request(estimated_tokens=1000) is True

            # Exhaust budget
            tracker.record_usage(input_tokens=100000, output_tokens=10000)

            # Should block next request
            assert tracker.can_make_request(estimated_tokens=1000) is False

    def test_can_make_request_estimation(self):
        """Test request approval based on estimated token usage."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tracker = BudgetTracker(daily_budget_usd=3.0, state_file=f.name)

            # Large request that would exceed budget
            # Estimate 1M tokens total = ~$2.40 (assuming 50/50 split)
            # With 3.0 budget, should allow
            assert tracker.can_make_request(estimated_tokens=1_000_000) is True

            # After spending some, check again
            tracker.record_usage(input_tokens=500_000, output_tokens=500_000)

            # Now another 1M token request would exceed
            assert tracker.can_make_request(estimated_tokens=1_000_000) is False

    def test_get_budget_status(self):
        """Test budget status reporting."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tracker = BudgetTracker(daily_budget_usd=3.0, state_file=f.name)

            # Initial status
            status = tracker.get_budget_status()
            assert status['daily_limit'] == 3.0
            assert status['spent_today'] == 0.0
            assert status['remaining'] == 3.0
            assert status['utilization_pct'] == 0.0

            # After spending
            tracker.record_usage(input_tokens=100_000, output_tokens=100_000)
            status = tracker.get_budget_status()

            expected_spent = (100_000 / 1_000_000) * 0.80 + (100_000 / 1_000_000) * 4.00
            assert abs(status['spent_today'] - expected_spent) < 0.0001
            assert abs(status['remaining'] - (3.0 - expected_spent)) < 0.0001
            assert status['utilization_pct'] > 0
            assert status['utilization_pct'] < 100

    def test_should_alert_budget(self):
        """Test budget alert threshold."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tracker = BudgetTracker(daily_budget_usd=3.0, state_file=f.name)

            # Initially should not alert
            assert tracker.should_alert_budget(threshold=0.8) is False

            # Spend just over 80% of budget to trigger alert
            # 80% of $3 = $2.40, so spend $2.41
            # Cost = (input/1M * 0.80) + (output/1M * 4.00)
            # To get $2.41: 500k input + 502.5k output = 0.4 + 2.01 = 2.41
            tracker.record_usage(input_tokens=500_000, output_tokens=502_500)

            # Should now trigger alert (spent >= 80% of $3)
            assert tracker.should_alert_budget(threshold=0.8) is True

            # Verify we're over the threshold
            assert tracker.today_spent > (3.0 * 0.8)

    def test_state_persistence(self):
        """Test that budget state persists across instances."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            state_file = f.name

            # First instance - record some spending
            tracker1 = BudgetTracker(daily_budget_usd=3.0, state_file=state_file)
            tracker1.record_usage(input_tokens=10000, output_tokens=2000)
            spent1 = tracker1.today_spent

            # Second instance - should restore spending
            tracker2 = BudgetTracker(daily_budget_usd=3.0, state_file=state_file)
            assert abs(tracker2.today_spent - spent1) < 0.0001

            # Verify state file contains correct data
            with open(state_file, 'r') as f:
                state = json.load(f)
                assert state['date'] == str(date.today())
                assert abs(state['spent'] - spent1) < 0.0001
                assert state['budget'] == 3.0

            # Clean up
            Path(state_file).unlink()

    def test_state_reset_new_day(self):
        """Test that budget resets for a new day."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            state_file = f.name

            # Create state file with yesterday's date
            yesterday_state = {
                'date': '2025-01-13',  # Hardcoded old date
                'spent': 2.50,
                'budget': 3.0
            }

            with open(state_file, 'w') as f:
                json.dump(yesterday_state, f)

            # Initialize tracker - should reset spending
            tracker = BudgetTracker(daily_budget_usd=3.0, state_file=state_file)
            assert tracker.today_spent == 0.0

            # Clean up
            Path(state_file).unlink()

    def test_state_file_corruption_handling(self):
        """Test graceful handling of corrupted state file."""
        with tempfile.NamedTemporaryFile(delete=False, mode='w') as f:
            # Write invalid JSON
            f.write("{invalid json}")
            f.flush()
            state_file = f.name

        # Should handle corruption gracefully
        tracker = BudgetTracker(daily_budget_usd=3.0, state_file=state_file)
        assert tracker.today_spent == 0.0

        # Clean up
        Path(state_file).unlink()

    def test_state_file_missing(self):
        """Test handling of missing state file."""
        # Non-existent file path
        tracker = BudgetTracker(daily_budget_usd=3.0, state_file="/tmp/nonexistent_budget_state.json")
        assert tracker.today_spent == 0.0

    def test_realistic_usage_scenario(self):
        """Test realistic daily usage scenario."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tracker = BudgetTracker(daily_budget_usd=3.0, state_file=f.name)

            # Simulate 4 monitoring cycles per day
            # Each cycle: ~30k tokens (15k input, 15k output)
            for cycle in range(4):
                # Check budget before cycle
                assert tracker.can_make_request(estimated_tokens=30_000) is True

                # Simulate cycle usage
                tracker.record_usage(input_tokens=15_000, output_tokens=15_000)

            # Total cost should be under $3
            # Per cycle: (15k/1M * 0.80) + (15k/1M * 4.00) = 0.012 + 0.06 = $0.072
            # 4 cycles: $0.288
            expected_total = 4 * ((15_000 / 1_000_000) * 0.80 + (15_000 / 1_000_000) * 4.00)
            assert abs(tracker.today_spent - expected_total) < 0.001
            assert tracker.today_spent < 3.0

            # Clean up
            Path(f.name).unlink()

    def test_zero_budget_handling(self):
        """Test handling of zero budget."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tracker = BudgetTracker(daily_budget_usd=0.0, state_file=f.name)

            # Should block all requests with zero budget
            assert tracker.can_make_request(estimated_tokens=1) is False

            # Get status should not crash
            status = tracker.get_budget_status()
            assert status['daily_limit'] == 0.0
            assert status['utilization_pct'] == 0.0

    def test_large_token_usage(self):
        """Test handling of very large token usage."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tracker = BudgetTracker(daily_budget_usd=100.0, state_file=f.name)

            # Record large usage (1M input, 1M output)
            tracker.record_usage(input_tokens=1_000_000, output_tokens=1_000_000)

            # Cost: (1M/1M * 0.80) + (1M/1M * 4.00) = $4.80
            expected_cost = 0.80 + 4.00
            assert abs(tracker.today_spent - expected_cost) < 0.001

            # Clean up
            Path(f.name).unlink()
