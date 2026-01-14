"""Structured JSON logging configuration."""

import logging
import sys
from pythonjsonlogger import jsonlogger


def setup_logger(name: str = "monitoring_agent", level: str = "INFO") -> logging.Logger:
    """
    Configure structured JSON logging.

    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers = []

    # Create console handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s',
        timestamp=True
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Don't propagate to root logger
    logger.propagate = False

    return logger


# Global logger instance
logger = setup_logger()
