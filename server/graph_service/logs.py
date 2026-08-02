"""Structured logging configuration with trace_id injection and OTLP export."""

import logging
import os
import sys
from typing import Any

# --- OTel trace (for trace_id injection) ---
try:
    from opentelemetry import trace

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

# --- OTel logs SDK + OTLP exporter ---
_OTEL_LOGS_AVAILABLE = False
try:
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import Resource as LogsResource

    _OTEL_LOGS_AVAILABLE = True
except ImportError:
    pass


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

        log_entry: dict[str, Any] = {
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


def _setup_otlp_logging(level: int) -> logging.Handler | None:
    """Create an OTLP LoggingHandler that exports logs to the OTel collector.

    Returns the handler, or None if OTel logs SDK is unavailable or the
    OTLP endpoint is not configured.
    """
    if not _OTEL_LOGS_AVAILABLE:
        return None

    otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', '')
    if not otlp_endpoint:
        return None

    service_name = os.getenv('OTEL_SERVICE_NAME', 'graphiti-server')
    try:
        import importlib.metadata

        service_version = importlib.metadata.version('graphiti-core')
    except Exception:
        service_version = os.getenv('OTEL_SERVICE_VERSION', 'unknown')

    resource = LogsResource.create(
        {
            'service.name': service_name,
            'service.version': service_version,
            'deployment.environment': os.getenv('DEPLOYMENT_ENVIRONMENT', 'development'),
        }
    )

    provider = LoggerProvider(resource=resource)
    exporter = OTLPLogExporter(endpoint=f'{otlp_endpoint}/v1/logs')
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(provider)

    handler = LoggingHandler(logger_provider=provider, level=level)
    return handler


def setup_logging(level: str = 'INFO') -> None:
    """Configure structured logging with trace_id injection.

    Logs go to stdout (structured JSON) and, when OTEL_EXPORTER_OTLP_ENDPOINT
    is set, also to the OTel collector which forwards them to GreptimeDB.
    """
    root_logger = logging.getLogger()
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler (stdout, structured JSON)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.addFilter(TraceIdFilter())
    console_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(console_handler)

    # OTLP log export -> OTel Collector -> GreptimeDB
    otlp_handler = _setup_otlp_logging(log_level)
    if otlp_handler is not None:
        otlp_handler.addFilter(TraceIdFilter())
        root_logger.addHandler(otlp_handler)
