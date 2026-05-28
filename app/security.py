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
    # Chart.js + Tom-Select worden van jsdelivr geladen — moet expliciet
    # in script-src en style-src staan, anders blokkeert CSP ze.
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
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
_RL_MAX_REQ = 300  # ruim genoeg voor een dashboard met 12+ async calls per page-load

# Paden die NOOIT rate-limited worden (lichtgewicht of cruciaal).
_RL_BYPASS_PATHS = ("/health",)
_RL_BYPASS_PREFIXES = ("/api/",)

# Paden die STRENGER rate-limited worden (zware queries / writes).
_RL_STRICT_PATHS = {"/sync/run", "/admin/import-historisch"}
_RL_STRICT_MAX_PER_MIN = 5


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate-limiting met drie zones:
       - bypass:  /health en /api/*  (geen limit — interne UI-calls)
       - strict:  /sync/run, /admin/import-*  (5 req/min — voorkomt misbruik)
       - default: alle andere paden  (300 req/min)
    """

    def __init__(self, app, window_sec: int = _RL_WINDOW_SEC, max_req: int = _RL_MAX_REQ):
        super().__init__(app)
        self.window = window_sec
        self.max_req = max_req

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 1. Bypass-paden (geen limit)
        if path in _RL_BYPASS_PATHS:
            return await call_next(request)
        if any(path.startswith(pref) for pref in _RL_BYPASS_PREFIXES):
            return await call_next(request)

        ip = _client_ip(request)
        now = time.time()
        cutoff = now - self.window
        recent = [t for t in _request_log[ip] if t > cutoff]
        _request_log[ip] = recent

        # 2. Strict-paden (apart geteld om writes te beperken)
        if path in _RL_STRICT_PATHS:
            strict_recent = [t for t in recent[-_RL_STRICT_MAX_PER_MIN * 3:] if t > cutoff]
            if len(strict_recent) >= _RL_STRICT_MAX_PER_MIN:
                log.warning("Strict rate-limit hit voor %s op %s", ip, path)
                return Response(
                    f"Rate limit voor {path} overschreden — max {_RL_STRICT_MAX_PER_MIN} per minuut.",
                    status_code=429,
                    headers={"Retry-After": str(self.window)},
                )

        # 3. Default-limit
        if len(recent) >= self.max_req:
            log.warning("Rate-limit hit voor %s (%d req in laatste %ds)", ip, len(recent), self.window)
            return Response(
                f"Rate limit overschreden — max {self.max_req} requests per {self.window}s per IP.",
                status_code=429,
                headers={"Retry-After": str(self.window)},
            )

        _request_log[ip].append(now)
        return await call_next(request)
