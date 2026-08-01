"""Structured logging configuration with trace_id injection."""

import logging
import sys
from typing import Any

try:
    from opentelemetry import trace

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


class TraceIdFilter(logging.Filter):
    """Inject trace_id and span_id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if OTEL_AVAILABLE:
            span = trace.get_current_span()
            if span and span.get_span_context().trace_id:
                record.trace_id = format(span.get_span_context().trace_id, '032x')
                record.span_id = format(span.get_span_context().span_id, '016x')
            else:
                record.trace_id = '0' * 32
                record.span_id = '0' * 16
        else:
            record.trace_id = '0' * 32
            record.span_id = '0' * 16
        return True


class StructuredFormatter(logging.Formatter):
    """Format logs as JSON with trace context."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_entry = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'trace_id': getattr(record, 'trace_id', '0' * 32),
            'span_id': getattr(record, 'span_id', '0' * 16),
        }

        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(level: str = 'INFO') -> None:
    """Configure structured logging with trace_id injection."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # Add trace_id filter
    console_handler.addFilter(TraceIdFilter())

    # Set structured formatter
    formatter = StructuredFormatter()
    console_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
