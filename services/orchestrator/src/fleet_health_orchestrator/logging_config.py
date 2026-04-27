"""Structured JSON logging configuration for Fleet Health Orchestrator.

This module provides:
- Structured JSON logging with correlation IDs for request tracing
- Log formatters for console (human-readable) and file (JSON)
- Centralized logger setup with configurable log levels
"""

import json
import logging
import sys
import uuid
from typing import Any

# Thread-local storage for correlation ID
_request_context = __import__("contextvars").ContextVar(
    "request_context", default={"correlation_id": None}
)


def get_correlation_id() -> str | None:
    """Get the current correlation ID from context."""
    context = _request_context.get()
    return context.get("correlation_id")


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID in context."""
    context = _request_context.get().copy()
    context["correlation_id"] = correlation_id
    _request_context.set(context)


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return f"req_{uuid.uuid4().hex[:12]}"


class StructuredFormatter(logging.Formatter):
    """Formats log records as structured JSON with correlation ID and metadata."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if available
        correlation_id = get_correlation_id()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from the log record
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter with colors and correlation ID."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console with colors."""
        color = self.COLORS.get(record.levelname, "")
        correlation_id = get_correlation_id() or ""
        corr_str = f" [{correlation_id}]" if correlation_id else ""

        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)

        return f"{color}[{record.levelname:8}]{self.RESET} {record.name} {msg}{corr_str}"


def setup_logging(
    log_level: str = "INFO",
    json_output: bool = False,
) -> logging.Logger:
    """Set up structured logging for the orchestrator.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, use JSON format; otherwise use console format

    Returns:
        Configured logger instance for fleet_health_orchestrator
    """
    logger = logging.getLogger("fleet_health_orchestrator")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    formatter = (
        StructuredFormatter() if json_output else ConsoleFormatter()
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def create_child_logger(name: str) -> logging.Logger:
    """Create a child logger with automatic correlation ID propagation.

    Args:
        name: Logger name (typically __name__ in calling module)

    Returns:
        Child logger instance
    """
    logger = logging.getLogger(name)
    return logger


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **extra_fields: Any,
) -> None:
    """Log a message with extra context fields.

    Args:
        logger: Logger instance
        level: Logging level
        message: Log message
        **extra_fields: Additional fields to include in structured log
    """
    record = logging.LogRecord(
        name=logger.name,
        level=level,
        pathname="",
        lineno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.extra_fields = extra_fields
    logger.handle(record)
