"""Custom middleware: security headers and per-request logging context.

CORS is configured in :mod:`backend.main` via Starlette's ``CORSMiddleware`` so
that allowed origins/methods/headers stay in one place.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Static transport-security headers applied to every response.
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self' wss:; frame-ancestors 'none'"
    ),
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers on every response.

    Adds ``Cache-Control: no-store, no-cache, must-revalidate`` additionally on
    ``/auth/*`` responses so credentials are never cached.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers[key] = value
        if request.url.path.startswith("/auth"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request ID + client IP into structlog context and time the request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        client_ip = request.client.host if request.client else "unknown"
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, ip=client_ip)
        request.state.request_id = request_id
        request.state.client_ip = client_ip

        start = time.time()
        log = structlog.get_logger("backend.request")
        try:
            response = await call_next(request)
        except Exception:
            log.error("request.unhandled", path=request.url.path)
            raise
        response.headers["X-Request-ID"] = request_id
        log.info(
            "request.complete",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.time() - start) * 1000, 1),
        )
        return response
