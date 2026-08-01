"""ASGI middleware that creates http.server.request spans and propagates
group_id/user_id via OTel Baggage.

Uses a pure ASGI wrapper (not Starlette BaseHTTPMiddleware) because
BaseHTTPMiddleware runs the downstream app in a separate task, which
breaks OTel context propagation. The pure ASGI approach keeps the span
and baggage in the same context as the route handler.
"""

import contextlib
import logging

try:
    from opentelemetry import baggage, context, trace
    from opentelemetry.trace.status import StatusCode

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

logger = logging.getLogger(__name__)

_GROUP_HEADER = 'x-graphiti-group-id'
_USER_HEADER = 'x-graphiti-user-id'


class TracingMiddleware:
    """Pure ASGI middleware for http.server.request spans + baggage."""

    def __init__(self, app):
        self.app = app
        self.tracer = trace.get_tracer('graphiti-server') if OTEL_AVAILABLE else None

    async def __call__(self, scope, receive, send):
        if not OTEL_AVAILABLE or scope.get('type') != 'http':
            await self.app(scope, receive, send)
            return

        headers = _parse_headers(scope.get('headers', []))
        group_id = headers.get(_GROUP_HEADER, '')
        user_id = headers.get(_USER_HEADER, 'anonymous')

        ctx = context.get_current()
        if group_id:
            ctx = baggage.set_baggage('group_id', group_id, context=ctx)
        ctx = baggage.set_baggage('user_id', user_id, context=ctx)
        token = context.attach(ctx)

        method = scope.get('method', 'UNKNOWN')
        route = scope.get('path', 'UNKNOWN')

        try:
            with self.tracer.start_as_current_span(
                'http.server.request',
                attributes={
                    'http.method': method,
                    'http.route': route,
                },
            ) as span:
                status_code = {'value': 0}

                async def send_wrapper(message):
                    if message['type'] == 'http.response.start':
                        status_code['value'] = message.get('status', 0)
                    await send(message)

                await self.app(scope, receive, send_wrapper)

                if status_code['value']:
                    span.set_attribute('http.status_code', status_code['value'])
                    if status_code['value'] >= 500:
                        span.set_status(StatusCode.ERROR)
        finally:
            context.detach(token)


def _parse_headers(raw_headers):
    """Convert ASGI raw header tuples to a lowercase-key dict."""
    result = {}
    for key, value in raw_headers:
        with contextlib.suppress(Exception):
            result[key.decode('latin-1').lower()] = value.decode('latin-1')
    return result
