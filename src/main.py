"""Main application entry point for IT Infrastructure Monitoring System."""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError:
    AsyncIOScheduler = None
    CronTrigger = None

from .config.loader import ConfigLoader
from .config.models import MonitoringSystemConfig
from .workflow import MonitoringWorkflow
from .utils.logger import setup_logger
from .services.telegram_client import TelegramClient


class MonitoringApp:
    """
    Main monitoring application.

    Orchestrates scheduled monitoring cycles with workflow execution,
    error handling, and graceful shutdown.
    """

    def __init__(
        self,
        config_path: str = "config/config.yaml",
        dry_run: bool = False
    ):
        """
        Initialize monitoring application.

        Args:
            config_path: Path to configuration file
            dry_run: If True, skip Telegram sending
        """
        self.config_path = config_path
        self.dry_run = dry_run
        self.logger = setup_logger("main")
        self.scheduler = None
        self.workflow = None

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self.logger.info("=" * 60)
        self.logger.info("IT Infrastructure Monitoring System")
        self.logger.info("=" * 60)

        # Load configuration
        self.config = self._load_config()

        # Initialize workflow
        self.logger.info("Initializing monitoring workflow...")
        self.workflow = MonitoringWorkflow(self.config, self.logger)
        self.logger.info("Application initialized successfully")

    def _load_config(self) -> MonitoringSystemConfig:
        """
        Load and validate configuration.

        Returns:
            MonitoringSystemConfig: Loaded configuration

        Raises:
            SystemExit: If configuration is invalid
        """
        try:
            self.logger.info(f"Loading configuration from {self.config_path}")
            config = ConfigLoader.load_from_file(self.config_path)
            self.logger.info("Configuration loaded successfully")
            return config

        except FileNotFoundError:
            self.logger.error(
                f"Configuration file not found: {self.config_path}\n"
                "Please create config/config.yaml from config/config.example.yaml"
            )
            sys.exit(1)

        except Exception as e:
            self.logger.error(
                f"Failed to load configuration: {e}",
                exc_info=True
            )
            sys.exit(1)

    def _signal_handler(self, signum, frame):
        """
        Handle shutdown signals.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_name = signal.Signals(signum).name
        self.logger.info(f"Received {signal_name}, initiating graceful shutdown...")

        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        sys.exit(0)

    async def run_monitoring_cycle(self):
        """
        Execute one complete monitoring cycle.

        This includes:
        1. Data collection from all collectors
        2. AI analysis of issues
        3. Report generation
        4. Telegram delivery (unless dry_run)
        """
        try:
            self.logger.info("Starting monitoring cycle")
            start_time = time.time()

            # Execute workflow
            final_state = await self.workflow.run()

            # Calculate metrics
            duration = time.time() - start_time
            total_checks = len(final_state.get('all_results', []))
            issues_count = len(final_state.get('issues', []))
            tokens = final_state.get('token_usage', 0)
            telegram_sent = final_state.get('telegram_sent', False)
            errors = final_state.get('errors', [])

            # Log summary
            self.logger.info("=" * 60)
            self.logger.info("Monitoring cycle completed")
            self.logger.info(f"Duration: {duration:.1f}s")
            self.logger.info(f"Checks: {total_checks} total, {issues_count} issues")
            self.logger.info(f"Tokens used: {tokens:,}")
            self.logger.info(f"Telegram sent: {telegram_sent}")
            if errors:
                self.logger.warning(f"Errors encountered: {len(errors)}")
            self.logger.info("=" * 60)

            # If dry run, log the message instead of sending
            if self.dry_run:
                message = final_state.get('telegram_message', '')
                self.logger.info("DRY RUN - Telegram message preview:")
                self.logger.info("=" * 60)
                self.logger.info(message)
                self.logger.info("=" * 60)

        except Exception as e:
            self.logger.error(
                "Monitoring cycle failed",
                exc_info=True,
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )

            # Send error notification to Telegram (unless dry run)
            if not self.dry_run:
                await self._send_error_notification(e)

            # Re-raise in run-once mode to signal failure
            raise

    async def _send_error_notification(self, error: Exception):
        """
        Send error alert to Telegram.

        Args:
            error: Exception that occurred
        """
        try:
            telegram = TelegramClient(self.config.telegram, self.logger)
            await telegram.send_error_notification(
                error,
                context="Monitoring cycle execution"
            )
        except Exception as notification_error:
            self.logger.error(
                f"Failed to send error notification to Telegram: {notification_error}",
                exc_info=True
            )

    def start_scheduler(self):
        """
        Start scheduled monitoring with APScheduler.

        The scheduler runs monitoring cycles based on the cron
        expression in the configuration file.

        Runs indefinitely until interrupted (SIGTERM/SIGINT).
        """
        if AsyncIOScheduler is None:
            self.logger.error(
                "APScheduler not installed. "
                "Install with: pip install apscheduler>=3.10.0"
            )
            sys.exit(1)

        self.logger.info("Starting scheduler")

        # Parse cron expression from config
        schedule = self.config.monitoring.schedule
        self.logger.info(f"Schedule: {schedule}")

        try:
            # Parse cron: "minute hour day month day_of_week"
            cron_parts = schedule.split()
            if len(cron_parts) != 5:
                raise ValueError(
                    f"Invalid cron expression: {schedule}. "
                    "Expected format: 'minute hour day month day_of_week'"
                )

            trigger = CronTrigger(
                minute=cron_parts[0],
                hour=cron_parts[1],
                day=cron_parts[2],
                month=cron_parts[3],
                day_of_week=cron_parts[4]
            )

        except Exception as e:
            self.logger.error(f"Failed to parse cron expression: {e}")
            sys.exit(1)

        # Create and configure scheduler
        self.scheduler = AsyncIOScheduler()

        self.scheduler.add_job(
            self.run_monitoring_cycle,
            trigger=trigger,
            id='monitoring_cycle',
            name='Infrastructure Monitoring Cycle',
            max_instances=1,  # Prevent overlapping executions
            coalesce=True,  # If missed, run once
            misfire_grace_time=300  # 5 minutes grace for startup
        )

        self.scheduler.start()
        self.logger.info(f"Scheduler started with cron: {schedule}")
        self.logger.info("Next run time: " + str(
            self.scheduler.get_job('monitoring_cycle').next_run_time
        ))

        # Run first cycle immediately on startup
        self.logger.info("Running initial monitoring cycle immediately...")
        asyncio.get_event_loop().run_until_complete(self.run_monitoring_cycle())

        # Keep running
        try:
            self.logger.info("Scheduler running. Press Ctrl+C to exit.")
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
        finally:
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown()
            self.logger.info("Scheduler stopped")


def main():
    """
    CLI entry point.

    Parses command-line arguments and starts the monitoring system.
    """
    parser = argparse.ArgumentParser(
        description='IT Infrastructure Monitoring System with AI Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with scheduler (default)
  python -m src.main

  # Run once and exit (useful for testing)
  python -m src.main --run-once

  # Dry run: collect and analyze but don't send to Telegram
  python -m src.main --run-once --dry-run

  # Use custom config file
  python -m src.main --config /path/to/config.yaml
        """
    )

    parser.add_argument(
        '--config',
        default='config/config.yaml',
        help='Path to configuration file (default: config/config.yaml)'
    )

    parser.add_argument(
        '--run-once',
        action='store_true',
        help='Run one monitoring cycle and exit (no scheduler)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without sending Telegram notifications (log only)'
    )

    parser.add_argument(
        '--log-level',
        default=os.getenv('LOG_LEVEL', 'INFO'),
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO or LOG_LEVEL env var)'
    )

    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(args.log_level)

    # Create application
    try:
        app = MonitoringApp(
            config_path=args.config,
            dry_run=args.dry_run
        )

        if args.run_once:
            # Run once and exit
            exit_code = 0
            try:
                asyncio.run(app.run_monitoring_cycle())
            except Exception:
                exit_code = 1

            sys.exit(exit_code)
        else:
            # Start scheduler
            app.start_scheduler()

    except Exception as e:
        logging.error(f"Application startup failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
