"""Retry handler with exponential backoff for transient failures."""

import asyncio
import random
import logging
from functools import wraps
from typing import Callable, TypeVar, Any, Tuple


T = TypeVar('T')


class RetryHandler:
    """
    Handles retry logic with exponential backoff and jitter.

    Useful for transient failures like network errors, API throttling,
    and temporary service unavailability.
    """

    @staticmethod
    async def with_retry(
        func: Callable[[], T],
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exceptions: Tuple[type, ...] = (Exception,),
        logger: logging.Logger = None
    ) -> T:
        """
        Execute function with exponential backoff retry.

        Args:
            func: Async callable to execute
            max_attempts: Maximum retry attempts (default 3)
            base_delay: Initial delay in seconds (default 1.0)
            max_delay: Maximum delay in seconds (default 60.0)
            exceptions: Tuple of exception types to retry on
            logger: Optional logger for retry events

        Returns:
            Result from successful function execution

        Raises:
            Exception: Last exception if all retries exhausted
        """
        logger = logger or logging.getLogger(__name__)

        last_exception = None

        for attempt in range(1, max_attempts + 1):
            try:
                # Execute function
                result = await func() if asyncio.iscoroutinefunction(func) else func()
                return result

            except exceptions as e:
                last_exception = e

                if attempt == max_attempts:
                    # Final attempt failed
                    logger.error(f"All {max_attempts} retry attempts exhausted: {e}")
                    raise

                # Calculate delay with exponential backoff and jitter
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                jitter = random.uniform(0, delay * 0.1)  # Add 0-10% jitter
                total_delay = delay + jitter

                logger.warning(
                    f"Attempt {attempt}/{max_attempts} failed: {e}. "
                    f"Retrying in {total_delay:.2f}s..."
                )

                # Wait before retry
                await asyncio.sleep(total_delay)

        # Should never reach here, but handle edge case
        raise last_exception or Exception("Retry failed with no exception")


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[type, ...] = (Exception,)
):
    """
    Decorator for automatic retry with exponential backoff.

    Usage:
        @with_retry(max_attempts=3, base_delay=1.0)
        async def my_function():
            # Code that may fail transiently
            pass

    Args:
        max_attempts: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exceptions: Tuple of exception types to retry on

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            """Async wrapper with retry logic."""
            logger = logging.getLogger(func.__module__)

            async def execute():
                return await func(*args, **kwargs)

            return await RetryHandler.with_retry(
                execute,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                exceptions=exceptions,
                logger=logger
            )

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            """Sync wrapper - not supported, raise error."""
            raise NotImplementedError(
                "Retry decorator only supports async functions. "
                "Use RetryHandler.with_retry() directly for sync functions."
            )

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Common retry configurations

def retry_network_errors(max_attempts: int = 3, base_delay: float = 1.0):
    """Retry decorator configured for network errors."""
    return with_retry(
        max_attempts=max_attempts,
        base_delay=base_delay,
        exceptions=(
            ConnectionError,
            TimeoutError,
            OSError,
        )
    )


def retry_api_throttling(max_attempts: int = 5, base_delay: float = 2.0):
    """Retry decorator configured for API throttling errors."""
    return with_retry(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=120.0,  # Allow longer delays for throttling
        exceptions=(Exception,)  # Catch all - check error message in handler
    )
