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
