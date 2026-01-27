"""PostgreSQL database health check collector."""

import os
import asyncio
from typing import List
import logging

try:
    import psycopg2
except ImportError:
    psycopg2 = None

from ..config.models import DatabaseConfig
from ..utils.status import HealthStatus
from ..utils.metrics import CollectorResult
from .base import BaseCollector, safe_collect


class DatabaseCollector(BaseCollector):
    """Collector for PostgreSQL database health checks."""

    def __init__(
        self,
        config: List[DatabaseConfig],
        thresholds: dict,
        logger: logging.Logger
    ):
        """
        Initialize database collector.

        Args:
            config: List of database configurations
            thresholds: System thresholds (not used for database checks)
            logger: Logger instance
        """
        super().__init__(config, thresholds, logger)

        if psycopg2 is None:
            self.logger.warning("psycopg2 not installed, database checks will fail")

    @safe_collect
    async def collect(self) -> List[CollectorResult]:
        """
        Check all configured databases.

        Returns:
            List[CollectorResult]: Database health check results
        """
        if not self.config:
            self.logger.info("No databases configured")
            return []

        if psycopg2 is None:
            return [CollectorResult(
                collector_name="database",
                target_name="all",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message="psycopg2 library not installed",
                error="ImportError: psycopg2"
            )]

        self.logger.info(f"Checking {len(self.config)} database(s)")

        # Run all checks concurrently (using asyncio for consistency)
        tasks = [self._check_database_async(db_config) for db_config in self.config]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions from gather
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                db_name = f"{self.config[i].host}/{self.config[i].database}" if i < len(self.config) else "unknown"
                self.logger.error(f"Database check failed for {db_name}: {result}")
                final_results.append(CollectorResult(
                    collector_name="database",
                    target_name=db_name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message=f"Check failed: {str(result)}",
                    error=str(result)
                ))
            else:
                final_results.append(result)

        return final_results

    async def _check_database_async(self, config: DatabaseConfig) -> CollectorResult:
        """
        Async wrapper for database check (runs in thread pool).

        Args:
            config: Database configuration

        Returns:
            CollectorResult: Database health check result
        """
        # Run blocking DB call in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._check_database, config)

    def _check_database(self, config: DatabaseConfig) -> CollectorResult:
        """
        Check single database connection.

        Args:
            config: Database configuration

        Returns:
            CollectorResult: Database health check result
        """
        target_name = f"{config.host}/{config.database}"

        try:
            # Get credentials from environment
            username = os.getenv('POSTGRES_USER')
            password = os.getenv('POSTGRES_PASSWORD')

            if not username or not password:
                return CollectorResult(
                    collector_name="database",
                    target_name=target_name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message="Missing POSTGRES_USER or POSTGRES_PASSWORD environment variables",
                    error="Missing credentials"
                )

            # Attempt connection
            conn_params = {
                'host': config.host,
                'port': config.port,
                'database': config.database,
                'user': username,
                'password': password,
                'sslmode': config.ssl_mode,
                'connect_timeout': 10
            }

            # Add SSL root certificate if specified
            if config.sslrootcert:
                conn_params['sslrootcert'] = config.sslrootcert

            conn = psycopg2.connect(**conn_params)

            cursor = conn.cursor()

            # Get database version
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]

            metrics = {
                "version": version.split(',')[0] if ',' in version else version[:100],
                "host": config.host,
                "port": config.port,
                "database": config.database
            }

            # Optional: query table statistics
            if config.table:
                try:
                    # Use parameterized query to prevent SQL injection
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {psycopg2.extensions.quote_ident(config.table, conn)};"
                    )
                    count = cursor.fetchone()[0]
                    metrics["row_count"] = count
                    metrics["table"] = config.table
                except Exception as e:
                    self.logger.warning(f"Failed to query table {config.table}: {e}")
                    metrics["table_query_error"] = str(e)

            cursor.close()
            conn.close()

            message = f"Connected successfully"
            if config.table and "row_count" in metrics:
                message += f", table {config.table}: {metrics['row_count']} rows"

            return CollectorResult(
                collector_name="database",
                target_name=target_name,
                status=HealthStatus.GREEN,
                metrics=metrics,
                message=message
            )

        except psycopg2.OperationalError as e:
            return CollectorResult(
                collector_name="database",
                target_name=target_name,
                status=HealthStatus.RED,
                metrics={},
                message=f"Connection failed: {str(e)}",
                error=str(e)
            )

        except psycopg2.Error as e:
            return CollectorResult(
                collector_name="database",
                target_name=target_name,
                status=HealthStatus.RED,
                metrics={},
                message=f"Database error: {str(e)}",
                error=str(e)
            )

        except Exception as e:
            return CollectorResult(
                collector_name="database",
                target_name=target_name,
                status=HealthStatus.UNKNOWN,
                metrics={},
                message=f"Unexpected error: {str(e)}",
                error=str(e)
            )
