"""Sanitize error messages to prevent leaking sensitive infrastructure details."""

import re


# Patterns that may appear in exception messages and leak sensitive info
_SANITIZE_PATTERNS = [
    # IPv4 addresses (e.g. 10.0.1.45, 192.168.1.100)
    (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<ip>'),
    # Hostnames with domain (e.g. database-1.cli88ausay5k.us-west-2.rds.amazonaws.com)
    (r'\b[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,}\b', '<host>'),
    # Port numbers in context (e.g. "port 5432", ":5432")
    (r'(?:port\s+|:)(\d{2,5})\b', lambda m: m.group(0).replace(m.group(1), '<port>')),
    # File paths (e.g. /opt/docker/..., /home/ubuntu/.ssh/key.pem, ~/.ssh/key)
    (r'(?:/[\w.~-]+){2,}', '<path>'),
    # Connection strings (e.g. postgresql://user:pass@host/db)
    (r'\w+://[^\s]+', '<connection_string>'),
    # AWS ARNs (e.g. arn:aws:s3:::bucket-name)
    (r'arn:aws:[^\s]+', '<arn>'),
    # AWS account IDs (12-digit numbers in AWS context)
    (r'\b\d{12}\b', '<account_id>'),
]

_COMPILED_PATTERNS = [
    (re.compile(pat), repl) for pat, repl in _SANITIZE_PATTERNS
]


def sanitize_error(error: Exception) -> str:
    """Return a sanitized error string safe for external services (Telegram, LLM).

    Preserves the error type and general meaning while stripping hostnames,
    IPs, ports, file paths, and connection strings.

    Args:
        error: The exception to sanitize

    Returns:
        str: Sanitized error message like "OperationalError: Connection refused to <host>:<port>"
    """
    error_type = type(error).__name__
    message = str(error)
    cleaned = _sanitize_message(message)
    return f"{error_type}: {cleaned}"


def _sanitize_message(message: str) -> str:
    """Strip sensitive patterns from a message string."""
    result = message
    for pattern, replacement in _COMPILED_PATTERNS:
        if callable(replacement):
            result = pattern.sub(replacement, result)
        else:
            result = pattern.sub(replacement, result)
    return result
