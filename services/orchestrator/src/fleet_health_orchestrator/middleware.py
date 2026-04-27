"""Request/response middleware for Fleet Health Orchestrator.

This module provides:
- Correlation ID generation and propagation for request tracing
- Request/response logging with structured data
- Performance metrics (latency, status codes)
"""

import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from fleet_health_orchestrator.logging_config import (
    generate_correlation_id,
    get_correlation_id,
    log_with_context,
    set_correlation_id,
)

_log = logging.getLogger(__name__)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware that generates and propagates correlation IDs for request tracing."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and add correlation ID header to response."""
        # Get or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = generate_correlation_id()

        set_correlation_id(correlation_id)

        # Process request
        response = await call_next(request)

        # Add correlation ID to response header
        response.headers["X-Correlation-ID"] = correlation_id

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs incoming requests and outgoing responses."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request/response with timing and status information."""
        # Log incoming request
        log_with_context(
            _log,
            logging.INFO,
            f"Request: {request.method} {request.url.path}",
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params) if request.query_params else None,
            client_host=request.client.host if request.client else None,
        )

        # Time the request
        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = (time.time() - start_time) * 1000
            log_with_context(
                _log,
                logging.ERROR,
                f"Request error: {request.method} {request.url.path}",
                method=request.method,
                path=request.url.path,
                elapsed_ms=round(elapsed_ms, 2),
                exception=str(exc),
            )
            raise

        elapsed_ms = (time.time() - start_time) * 1000

        # Log response
        log_with_context(
            _log,
            logging.INFO,
            f"Response: {request.method} {request.url.path} -> {response.status_code}",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed_ms=round(elapsed_ms, 2),
        )

        return response


class DebugLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs request/response bodies in DEBUG mode."""

    def __init__(self, app: ASGIApp, enabled: bool = False):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request/response bodies if debugging is enabled."""
        if not self.enabled or _log.level > logging.DEBUG:
            return await call_next(request)

        # Log request body for POST/PUT/PATCH
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.body()
                if body:
                    log_with_context(
                        _log,
                        logging.DEBUG,
                        f"Request body: {request.method} {request.url.path}",
                        method=request.method,
                        path=request.url.path,
                        body_size=len(body),
                    )
            except Exception:
                pass  # Can't read body if it's already consumed

        response = await call_next(request)

        # Log response status
        log_with_context(
            _log,
            logging.DEBUG,
            f"Response status: {response.status_code}",
            status_code=response.status_code,
        )

        return response
