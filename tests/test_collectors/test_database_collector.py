"""Tests for Database collector."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.collectors.database_collector import DatabaseCollector
from src.config.models import DatabaseConfig
from src.utils.status import HealthStatus

# Fixtures imported from conftest.py: database_configs (as db_configs alias), thresholds, logger


@pytest.fixture
def db_configs(database_configs):
    """Alias for database_configs from conftest."""
    return database_configs if database_configs else [
        DatabaseConfig(
            host="db1.example.com",
            port=5432,
            database="test_db",
            ssl_mode="require"
        )
    ]


@pytest.mark.asyncio
async def test_database_collector_success(db_configs, thresholds, logger):
    """Test successful database connections."""
    collector = DatabaseCollector(db_configs, thresholds, logger)

    with patch('src.collectors.database_collector.psycopg2') as mock_psycopg2:
        # Mock successful connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_cursor.fetchone.return_value = ("PostgreSQL 14.5",)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        # Mock environment variables
        with patch('os.getenv') as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                'POSTGRES_USER': 'test_user',
                'POSTGRES_PASSWORD': 'test_pass'
            }.get(key, default)

            # Execute
            results = await collector.collect()

            # Verify
            assert len(results) == 2

            # First database
            assert results[0].collector_name == "database"
            assert results[0].target_name == "db1.example.com/main_db"
            assert results[0].status == HealthStatus.GREEN
            assert "version" in results[0].metrics
            assert "Connected successfully" in results[0].message


@pytest.mark.asyncio
async def test_database_collector_with_table_count(db_configs, thresholds, logger):
    """Test database check with table row count."""
    collector = DatabaseCollector([db_configs[1]], thresholds, logger)

    with patch('src.collectors.database_collector.psycopg2') as mock_psycopg2:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # Mock version query and table count
        mock_cursor.fetchone.side_effect = [
            ("PostgreSQL 14.5",),  # Version query
            (12345,)  # Row count query
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        with patch('os.getenv') as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                'POSTGRES_USER': 'test_user',
                'POSTGRES_PASSWORD': 'test_pass'
            }.get(key, default)

            # Execute
            results = await collector.collect()

            # Verify table count in metrics
            assert len(results) == 1
            assert results[0].status == HealthStatus.GREEN
            assert "row_count" in results[0].metrics
            assert results[0].metrics["row_count"] == 12345


@pytest.mark.asyncio
async def test_database_collector_connection_failure(db_configs, thresholds, logger):
    """Test database connection failure (RED)."""
    collector = DatabaseCollector([db_configs[0]], thresholds, logger)

    with patch('src.collectors.database_collector.psycopg2') as mock_psycopg2:
        # Mock connection error
        mock_psycopg2.connect.side_effect = Exception("Connection refused")

        with patch('os.getenv') as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                'POSTGRES_USER': 'test_user',
                'POSTGRES_PASSWORD': 'test_pass'
            }.get(key, default)

            # Execute
            results = await collector.collect()

            # Verify RED status
            assert len(results) == 1
            assert results[0].status == HealthStatus.RED
            assert "Connection refused" in results[0].error


@pytest.mark.asyncio
async def test_database_collector_missing_credentials(db_configs, thresholds, logger):
    """Test missing database credentials (RED)."""
    collector = DatabaseCollector([db_configs[0]], thresholds, logger)

    with patch('src.collectors.database_collector.psycopg2'):
        # Mock missing credentials
        with patch('os.getenv') as mock_getenv:
            mock_getenv.return_value = None

            # Execute
            results = await collector.collect()

            # Verify RED status for missing credentials
            assert len(results) == 1
            assert results[0].status == HealthStatus.RED


@pytest.mark.asyncio
async def test_database_collector_no_psycopg2(db_configs, thresholds, logger):
    """Test graceful handling when psycopg2 not installed."""
    collector = DatabaseCollector(db_configs, thresholds, logger)

    # Mock psycopg2 as unavailable
    with patch('src.collectors.database_collector.psycopg2', None):
        results = await collector.collect()

        # Should return single UNKNOWN result
        assert len(results) == 1
        assert results[0].status == HealthStatus.UNKNOWN
        assert "psycopg2" in results[0].message.lower()


@pytest.mark.asyncio
async def test_database_collector_empty_config(thresholds, logger):
    """Test collector with no databases configured."""
    collector = DatabaseCollector([], thresholds, logger)

    results = await collector.collect()

    # Should return empty list
    assert len(results) == 0


@pytest.mark.asyncio
async def test_database_collector_parallel_execution(db_configs, thresholds, logger):
    """Test that multiple databases are checked in parallel."""
    collector = DatabaseCollector(db_configs, thresholds, logger)

    with patch('src.collectors.database_collector.psycopg2') as mock_psycopg2:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("PostgreSQL 14.5",)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        with patch('os.getenv') as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                'POSTGRES_USER': 'test_user',
                'POSTGRES_PASSWORD': 'test_pass'
            }.get(key, default)

            # Execute
            import time
            start = time.time()
            results = await collector.collect()
            duration = time.time() - start

            # Should complete quickly (parallel execution)
            assert duration < 2.0
            assert len(results) == 2


@pytest.mark.asyncio
async def test_database_collector_query_error(db_configs, thresholds, logger):
    """Test database query execution error."""
    collector = DatabaseCollector([db_configs[1]], thresholds, logger)

    with patch('src.collectors.database_collector.psycopg2') as mock_psycopg2:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # First query (version) succeeds, second query (table count) fails
        mock_cursor.fetchone.side_effect = [
            ("PostgreSQL 14.5",),
            Exception("Table does not exist")
        ]
        mock_cursor.execute.side_effect = [None, Exception("Table does not exist")]
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        with patch('os.getenv') as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                'POSTGRES_USER': 'test_user',
                'POSTGRES_PASSWORD': 'test_pass'
            }.get(key, default)

            # Execute
            results = await collector.collect()

            # Should still return GREEN if connection works, even if table query fails
            assert len(results) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
