"""OpenTelemetry metrics for Graphiti.

Defines counters and histograms for monitoring business metrics.
All metrics follow low-cardinality principles (see spec §5.4).
"""

import logging

try:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

logger = logging.getLogger(__name__)

_meter = None


def setup_metrics() -> 'metrics.Meter | None':
    """Initialize OTel metrics and return a meter.
    
    Returns None if OTel is not installed or endpoint not configured.
    """
    global _meter
    
    if _meter is not None:
        return _meter
    
    if not OTEL_AVAILABLE:
        logger.info('OpenTelemetry not installed, metrics disabled')
        return None
    
    import os
    otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', '')
    service_name = os.getenv('OTEL_SERVICE_NAME', 'graphiti-server')
    
    if not otlp_endpoint:
        logger.info('OTEL_EXPORTER_OTLP_ENDPOINT not set, metrics disabled')
        return None
    
    exporter = OTLPMetricExporter(endpoint=f'{otlp_endpoint}/v1/metrics')
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=10000)
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    
    _meter = metrics.get_meter('graphiti-server', '1.0.0')
    logger.info(f'OTel metrics enabled, exporting to {otlp_endpoint}')
    return _meter


# ===== Episode Metrics =====
def create_episode_add_counter(meter):
    """Counter for episode additions."""
    return meter.create_counter(
        name='graphiti_episode_add_total',
        description='Total number of episodes added',
        unit='1',
    )


def create_episode_add_duration(meter):
    """Histogram for episode addition duration."""
    return meter.create_histogram(
        name='graphiti_episode_add_duration_ms',
        description='Duration of episode addition in milliseconds',
        unit='ms',
    )


# ===== Search Metrics =====
def create_search_counter(meter):
    """Counter for search operations."""
    return meter.create_counter(
        name='graphiti_search_total',
        description='Total number of search operations',
        unit='1',
    )


def create_search_duration(meter):
    """Histogram for search duration."""
    return meter.create_histogram(
        name='graphiti_search_duration_ms',
        description='Duration of search operations in milliseconds',
        unit='ms',
    )


def create_search_result_count(meter):
    """Histogram for search result counts."""
    return meter.create_histogram(
        name='graphiti_search_result_count',
        description='Number of results returned by search',
        unit='1',
    )


# ===== LLM Metrics =====
def create_llm_calls_counter(meter):
    """Counter for LLM calls."""
    return meter.create_counter(
        name='graphiti_llm_calls_total',
        description='Total number of LLM calls',
        unit='1',
    )


def create_llm_tokens_counter(meter):
    """Counter for LLM tokens."""
    return meter.create_counter(
        name='graphiti_llm_tokens_total',
        description='Total number of LLM tokens used',
        unit='1',
    )


def create_llm_latency(meter):
    """Histogram for LLM latency."""
    return meter.create_histogram(
        name='graphiti_llm_latency_ms',
        description='LLM call latency in milliseconds',
        unit='ms',
    )


# ===== DB Metrics =====
def create_db_query_counter(meter):
    """Counter for database queries."""
    return meter.create_counter(
        name='graphiti_db_query_total',
        description='Total number of database queries',
        unit='1',
    )


def create_db_query_duration(meter):
    """Histogram for database query duration."""
    return meter.create_histogram(
        name='graphiti_db_query_duration_ms',
        description='Database query duration in milliseconds',
        unit='ms',
    )
