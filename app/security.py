"""Minimal security middleware voor dashboard-nestor.

Geen CSRF/auth/login (eerste versie heeft geen login). Wel:
  - security headers op elke response
  - request-size limiet om geheugen-DoS te voorkomen
  - simpele in-memory rate-limiter per IP voor de export-endpoints
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("dashboard-nestor.security")


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

_CSP_DIRECTIVES = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        h.setdefault("Content-Security-Policy", _CSP_DIRECTIVES)
        return response


# ---------------------------------------------------------------------------
# Request-size limiet
# ---------------------------------------------------------------------------

DEFAULT_MAX_REQUEST_BYTES = 50 * 1024 * 1024  # 50 MB


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int = DEFAULT_MAX_REQUEST_BYTES):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl:
            try:
                if int(cl) > self.max_bytes:
                    return Response(
                        f"Request body too large (max {self.max_bytes // (1024*1024)} MB).",
                        status_code=413,
                    )
            except ValueError:
                pass
        return await call_next(request)


# ---------------------------------------------------------------------------
# Eenvoudige rate-limiter per IP — bescherming tegen excessieve Prato-queries
# ---------------------------------------------------------------------------
#
# Geen auth = elke gebruiker kan de zware export-query triggeren. Beperk
# tot een redelijke frequentie zodat een rogue scriptje de Postgres niet
# kan platleggen.

_request_log: dict[str, list[float]] = defaultdict(list)
_RL_WINDOW_SEC = 60
_RL_MAX_REQ = 30  # 30 req per minuut per IP


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """30 requests per minuut per IP. Per-IP throttling, geen globale limiet."""

    def __init__(self, app, window_sec: int = _RL_WINDOW_SEC, max_req: int = _RL_MAX_REQ):
        super().__init__(app)
        self.window = window_sec
        self.max_req = max_req

    async def dispatch(self, request: Request, call_next):
        # /health uitsluiten van rate-limit (Railway healthcheck)
        if request.url.path == "/health":
            return await call_next(request)

        ip = _client_ip(request)
        now = time.time()
        cutoff = now - self.window
        recent = [t for t in _request_log[ip] if t > cutoff]
        _request_log[ip] = recent

        if len(recent) >= self.max_req:
            log.warning("Rate-limit hit voor %s (%d req in laatste %ds)", ip, len(recent), self.window)
            return Response(
                f"Rate limit overschreden — max {self.max_req} requests per {self.window}s per IP.",
                status_code=429,
                headers={"Retry-After": str(self.window)},
            )

        _request_log[ip].append(now)
        return await call_next(request)
