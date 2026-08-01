"""OpenTelemetry tracing setup for the Graphiti server.

Initializes a TracerProvider with OTLP export to the collector,
and returns a tracer that gets injected into Graphiti.
"""

import logging
import os

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

logger = logging.getLogger(__name__)

_tracer_instance = None


def setup_tracing() -> 'trace.Tracer | None':
    """Initialize OTel tracing and return a tracer.

    Returns None if OTel is not installed or if the endpoint is not configured,
    in which case Graphiti will use its NoOpTracer (zero overhead).
    """
    global _tracer_instance

    if _tracer_instance is not None:
        return _tracer_instance

    if not OTEL_AVAILABLE:
        logger.info('OpenTelemetry not installed, tracing disabled')
        return None

    otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', '')
    service_name = os.getenv('OTEL_SERVICE_NAME', 'graphiti-server')

    # Read version from package metadata
    try:
        import importlib.metadata

        service_version = importlib.metadata.version('graphiti-core')
    except Exception:
        service_version = os.getenv('OTEL_SERVICE_VERSION', 'unknown')

    deployment_env = os.getenv('DEPLOYMENT_ENVIRONMENT', 'development')

    resource = Resource.create(
        {
            'service.name': service_name,
            'service.version': service_version,
            'deployment.environment': deployment_env,
        }
    )

    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=f'{otlp_endpoint}/v1/traces')
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info(f'OTel tracing enabled, exporting to {otlp_endpoint}')
    else:
        logger.info('OTEL_EXPORTER_OTLP_ENDPOINT not set, tracing disabled (NoOpTracer)')
        return None

    trace.set_tracer_provider(provider)
    _tracer_instance = trace.get_tracer('graphiti-server')
    return _tracer_instance


# ===== Metrics Setup =====
try:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

_meter = None
_api_request_counter = None
_api_request_duration = None


def setup_metrics() -> 'metrics.Meter | None':
    """Initialize OTel metrics and return a meter."""
    global _meter, _api_request_counter, _api_request_duration

    if _meter is not None:
        return _meter

    if not METRICS_AVAILABLE:
        logger.info('OpenTelemetry metrics not installed, metrics disabled')
        return None

    otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', '')
    service_name = os.getenv('OTEL_SERVICE_NAME', 'graphiti-server')

    if not otlp_endpoint:
        logger.info('OTEL_EXPORTER_OTLP_ENDPOINT not set, metrics disabled')
        return None

    exporter = OTLPMetricExporter(endpoint=f'{otlp_endpoint}/v1/metrics')
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=10000)
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)

    _meter = metrics.get_meter('graphiti-server')

    # Create API-level metrics
    _api_request_counter = _meter.create_counter(
        name='graphiti_api_requests_total',
        description='Total number of API requests',
        unit='1',
    )
    _api_request_duration = _meter.create_histogram(
        name='graphiti_api_request_duration_ms',
        description='API request duration in milliseconds',
        unit='ms',
    )

    logger.info(f'OTel metrics enabled, exporting to {otlp_endpoint}')
    return _meter


def record_api_request(method: str, route: str, status_code: int, duration_ms: float):
    """Record an API request metric."""
    if _api_request_counter and _api_request_duration:
        attributes = {
            'method': method,
            'route': route,
            'status_code': status_code,
        }
        _api_request_counter.add(1, attributes)
        _api_request_duration.record(duration_ms, attributes)
