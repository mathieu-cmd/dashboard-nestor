"""Dashboard Nestor — FastAPI entry point.

Minimale eerste versie:
  GET /health                  Railway healthcheck
  GET /                        info-blob met endpoint-lijst
  GET /prato/test-connection   sanity check op de Prato Postgres
  GET /prato/export/diag       introspectie van klant-bronnen
  GET /prato/export.csv        margelijst-export met filters

Geen authenticatie in deze versie — URL discreet houden.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .prato_export import (
    EXPORT_COLUMNS,
    diagnostic_summary,
    stream_export_csv,
)
from .prato_reporter import (
    PratoNotConfigured,
    is_configured as prato_is_configured,
    test_connection,
)
from .security import (
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("dashboard-nestor")


app = FastAPI(
    title="Dashboard Nestor",
    # Geen publieke docs — we hebben er niet niets, en het is gevoelige data
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Middleware-volgorde: laatst toegevoegde = eerst uitgevoerd op inkomend
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)


# ---------------------------------------------------------------------------
# Basis-endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    """Railway healthcheck — geen auth, geen DB-call."""
    return {"status": "ok"}


@app.get("/")
def root():
    return {
        "service": "dashboard.nestor.be",
        "version": "0.1.0",
        "endpoints": [
            "/health",
            "/prato/test-connection",
            "/prato/export/diag",
            "/prato/export.csv (filters: jaar, kwartaal, maand, week, "
            "vestigingseenheidreferentieid, klantreferentieid, "
            "persoonreferentieid, klantnaam, familienaam, voornaam)",
        ],
        "prato_configured": prato_is_configured(),
    }


# ---------------------------------------------------------------------------
# Prato-endpoints
# ---------------------------------------------------------------------------


@app.get("/prato/test-connection")
def prato_test_connection():
    """Snelle health-check op de Prato Postgres.

    Bedoeld om te valideren dat:
      - de IP-whitelist door Prato is opengezet voor dit Railway-service's
        outbound IPs,
      - credentials kloppen,
      - SSL werkt.
    """
    if not prato_is_configured():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "configuration_missing",
                "message": (
                    "Prato DB-credentials ontbreken. Zet PRATO_DB_HOST, "
                    "PRATO_DB_USER, PRATO_DB_PASSWORD en PRATO_DB_NAME "
                    "in Railway -> Variables."
                ),
            },
        )
    try:
        result = test_connection()
        return JSONResponse(content=result)
    except PratoNotConfigured as e:
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "configuration_missing", "message": str(e)},
        )
    except Exception as e:  # noqa: BLE001
        log.exception("test-connection mislukt")
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "connection_failed",
                "exception_type": type(e).__name__,
                "message": str(e)[:500],
            },
        )


@app.get("/prato/export/diag")
def prato_export_diag():
    """Korte introspectie — hoeveel rijen in de betrokken klant-bronnen?"""
    if not prato_is_configured():
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "configuration_missing"},
        )
    try:
        return JSONResponse(content={"ok": True, **diagnostic_summary()})
    except Exception as e:  # noqa: BLE001
        log.exception("diag faalde")
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "diag_failed",
                "exception_type": type(e).__name__,
                "message": str(e)[:500],
            },
        )


@app.get("/prato/export.csv")
def prato_export_csv(
    request: Request,
    # Periode-filters — multi-value mogelijk
    jaar: list[int] = Query(default=[]),
    kwartaal: list[int] = Query(default=[]),
    maand: list[int] = Query(default=[]),
    week: list[int] = Query(default=[]),
    # ID-filters — multi-value
    vestigingseenheidreferentieid: list[str] = Query(default=[]),
    klantreferentieid: list[str] = Query(default=[]),
    persoonreferentieid: list[str] = Query(default=[]),
    # Naam-filters — single value, ILIKE
    klantnaam: Optional[str] = None,
    familienaam: Optional[str] = None,
    voornaam: Optional[str] = None,
):
    """Stream de margelijst-export als CSV.

    Geen verplichte parameters. Lege filters = volledige historiek.
    Multi-value query-parameters (zoals ?jaar=2025&jaar=2026) gelden
    als OR binnen die dimensie; verschillende dimensies zijn AND.

    Format: UTF-8 zonder BOM, semicolon, Belgische decimaalkomma.
    """
    if not prato_is_configured():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "configuration_missing",
                "message": (
                    "Prato DB-credentials ontbreken in Railway -> Variables."
                ),
            },
        )

    filters = {
        "jaar": jaar,
        "kwartaal": kwartaal,
        "maand": maand,
        "week": week,
        "vestigingseenheidreferentieid": vestigingseenheidreferentieid,
        "klantreferentieid": klantreferentieid,
        "persoonreferentieid": persoonreferentieid,
        "klantnaam": klantnaam,
        "familienaam": familienaam,
        "voornaam": voornaam,
    }

    log.info(
        "AUDIT: export.csv gestart - ip=%s filters=%s",
        request.headers.get("x-forwarded-for", request.client.host if request.client else "?"),
        {k: v for k, v in filters.items() if v},
    )

    started = time.monotonic()

    def _generator():
        try:
            yield from stream_export_csv(filters)
        except PratoNotConfigured as e:
            log.exception("export-csv: Prato niet geconfigureerd")
            yield f"ERROR;{e}\n".encode("utf-8")
        except Exception as e:  # noqa: BLE001
            log.exception("export-csv tijdens streaming gefaald")
            yield f"ERROR;{type(e).__name__};{str(e)[:200]}\n".encode("utf-8")
        finally:
            log.info("export-csv afgerond na %ds", int(time.monotonic() - started))

    filename = f"margelijst_{date.today().isoformat()}.csv"
    return StreamingResponse(
        _generator(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Format": "csv-semicolon-utf8-be-decimal",
            "X-Columns": str(len(EXPORT_COLUMNS)),
        },
    )
