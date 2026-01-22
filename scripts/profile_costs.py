#!/usr/bin/env python3
"""
Cost profiling script for monitoring system.

Analyzes token usage and projects daily/monthly costs based on
actual or simulated monitoring cycles.
"""

import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.loader import ConfigLoader
from src.workflow import MonitoringWorkflow
from src.utils.logger import setup_logger


class CostProfiler:
    """Profile token usage and costs for monitoring cycles."""

    # Claude Haiku 3.5 pricing
    INPUT_PRICE_PER_1M = 0.80   # $0.80 per 1M input tokens
    OUTPUT_PRICE_PER_1M = 4.00  # $4.00 per 1M output tokens

    def __init__(self, config_path: str):
        """Initialize cost profiler."""
        self.logger = setup_logger("cost_profiler")
        self.config_path = config_path

        self.logger.info("Loading configuration...")
        self.config = ConfigLoader.load_from_file(config_path)

        self.logger.info("Initializing workflow...")
        self.workflow = MonitoringWorkflow(self.config, self.logger)

    async def profile_single_cycle(self) -> dict:
        """
        Profile a single monitoring cycle.

        Returns:
            dict: Profile results with token usage and cost breakdown
        """
        self.logger.info("=" * 70)
        self.logger.info("COST PROFILING: Single Monitoring Cycle")
        self.logger.info("=" * 70)

        start_time = datetime.now()

        # Run monitoring cycle
        self.logger.info("\nExecuting monitoring cycle...")
        final_state = await self.workflow.run()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Extract metrics
        token_usage = final_state.get('token_usage', 0)
        all_results = final_state.get('all_results', [])
        issues = final_state.get('issues', [])

        # Calculate costs
        # Note: We don't have exact input/output split, so estimate 50/50
        estimated_input = token_usage // 2
        estimated_output = token_usage // 2

        input_cost = (estimated_input / 1_000_000) * self.INPUT_PRICE_PER_1M
        output_cost = (estimated_output / 1_000_000) * self.OUTPUT_PRICE_PER_1M
        total_cost = input_cost + output_cost

        profile = {
            'timestamp': start_time.isoformat(),
            'duration_seconds': duration,
            'total_checks': len(all_results),
            'issues_detected': len(issues),
            'token_usage': {
                'total': token_usage,
                'estimated_input': estimated_input,
                'estimated_output': estimated_output
            },
            'cost': {
                'per_cycle': total_cost,
                'input_cost': input_cost,
                'output_cost': output_cost
            }
        }

        return profile

    def project_costs(self, cost_per_cycle: float, cycles_per_day: int = 4) -> dict:
        """
        Project daily and monthly costs.

        Args:
            cost_per_cycle: Cost per monitoring cycle in USD
            cycles_per_day: Number of cycles per day

        Returns:
            dict: Projected costs
        """
        daily_cost = cost_per_cycle * cycles_per_day
        monthly_cost = daily_cost * 30
        yearly_cost = daily_cost * 365

        return {
            'cost_per_cycle': cost_per_cycle,
            'cycles_per_day': cycles_per_day,
            'daily_cost': daily_cost,
            'monthly_cost': monthly_cost,
            'yearly_cost': yearly_cost,
            'daily_budget': self.config.llm.daily_budget_usd,
            'budget_utilization_pct': (daily_cost / self.config.llm.daily_budget_usd) * 100 if self.config.llm.daily_budget_usd > 0 else 0
        }

    def print_profile_report(self, profile: dict, projections: dict):
        """Print formatted cost profile report."""
        print("\n" + "=" * 70)
        print("COST PROFILE REPORT")
        print("=" * 70)

        print("\n📊 CYCLE METRICS")
        print(f"  Duration: {profile['duration_seconds']:.1f}s")
        print(f"  Total Checks: {profile['total_checks']}")
        print(f"  Issues Detected: {profile['issues_detected']}")

        print("\n🔢 TOKEN USAGE")
        print(f"  Total Tokens: {profile['token_usage']['total']:,}")
        print(f"  Estimated Input: {profile['token_usage']['estimated_input']:,}")
        print(f"  Estimated Output: {profile['token_usage']['estimated_output']:,}")

        print("\n💰 COST BREAKDOWN (per cycle)")
        print(f"  Input Cost: ${profile['cost']['input_cost']:.4f}")
        print(f"  Output Cost: ${profile['cost']['output_cost']:.4f}")
        print(f"  Total Cost: ${profile['cost']['per_cycle']:.4f}")

        print("\n📈 PROJECTED COSTS")
        print(f"  Cycles per Day: {projections['cycles_per_day']}")
        print(f"  Daily Cost: ${projections['daily_cost']:.2f}")
        print(f"  Monthly Cost: ${projections['monthly_cost']:.2f}")
        print(f"  Yearly Cost: ${projections['yearly_cost']:.2f}")

        print("\n💵 BUDGET ANALYSIS")
        print(f"  Daily Budget: ${projections['daily_budget']:.2f}")
        print(f"  Budget Utilization: {projections['budget_utilization_pct']:.1f}%")

        if projections['budget_utilization_pct'] > 100:
            print(f"\n  ⚠️  WARNING: Projected cost EXCEEDS daily budget!")
            print(f"  Over budget by: ${projections['daily_cost'] - projections['daily_budget']:.2f}/day")
        elif projections['budget_utilization_pct'] > 80:
            print(f"\n  ⚠️  CAUTION: Using {projections['budget_utilization_pct']:.1f}% of daily budget")
        else:
            print(f"\n  ✅ GOOD: Well within budget ({projections['budget_utilization_pct']:.1f}% utilization)")

        print("\n📝 RECOMMENDATIONS")

        if projections['budget_utilization_pct'] > 100:
            print("  1. Increase daily budget")
            print("  2. Reduce monitoring frequency (e.g., 6 hours → 12 hours)")
            print("  3. Optimize prompts to reduce token usage")
            print("  4. Filter non-critical targets")
        elif projections['budget_utilization_pct'] > 80:
            print("  1. Monitor budget closely")
            print("  2. Consider increasing buffer for peak usage")
        else:
            print("  1. Current configuration is cost-effective")
            print("  2. Budget has room for expansion if needed")

        # Token optimization tips
        tokens_per_check = profile['token_usage']['total'] / max(profile['total_checks'], 1)
        print(f"\n💡 OPTIMIZATION INSIGHTS")
        print(f"  Tokens per Check: {tokens_per_check:.0f}")

        if tokens_per_check > 500:
            print("  - Consider optimizing prompt templates")
            print("  - Reduce metrics included in analysis prompts")

        print("\n" + "=" * 70)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Profile token usage and costs for monitoring system',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--config',
        default='config/config.yaml',
        help='Path to configuration file'
    )

    parser.add_argument(
        '--cycles',
        type=int,
        default=4,
        help='Number of cycles per day for projections (default: 4)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without sending Telegram notifications'
    )

    args = parser.parse_args()

    try:
        # Create profiler
        profiler = CostProfiler(args.config)

        # Profile single cycle
        profile = await profiler.profile_single_cycle()

        # Project costs
        projections = profiler.project_costs(
            cost_per_cycle=profile['cost']['per_cycle'],
            cycles_per_day=args.cycles
        )

        # Print report
        profiler.print_profile_report(profile, projections)

        # Exit with appropriate code
        if projections['budget_utilization_pct'] > 100:
            sys.exit(2)  # Over budget
        elif projections['budget_utilization_pct'] > 80:
            sys.exit(1)  # Warning
        else:
            sys.exit(0)  # OK

    except KeyboardInterrupt:
        print("\n\nProfiler interrupted by user")
        sys.exit(130)

    except Exception as e:
        print(f"\n❌ Profiling failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
