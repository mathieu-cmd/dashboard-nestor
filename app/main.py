"""Dashboard Nestor — FastAPI entry point.

Pagina's:
  GET /                      → redirect /dashboards
  GET /dashboards            HTML met vastgepinde KPI-grafieken (Chart.js)
  GET /explorer              HTML met slicer voor ad-hoc grafiek + pin
  GET /export                HTML met filters + CSV-download

API:
  GET /api/status            JSON: cache size + laatste sync
  GET /api/metric            JSON-data voor één grafiek (parameters: metric,
                             segment, grain, period_mode, period_value, top_n)
  GET /api/segments          Lijst beschikbare segmenten
  GET /api/metrics           Lijst beschikbare metrics
  GET /api/pinned            Lijst vastgepinde grafieken
  POST /api/pinned           Voeg vastpin toe (JSON body)
  DELETE /api/pinned/{id}    Verwijder vastpin

  POST /sync/run             Trigger sync (background)
  GET  /sync/status          Status van meest recente sync

  GET /prato/test-connection Live check op Prato
  GET /prato/export/diag     Live introspectie van klant-bronnen
  GET /prato/export.csv      CSV-export uit cache met filters
  GET /health                Railway healthcheck

Auto-sync: dagelijks om 11:59 Europe/Brussels.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Body, FastAPI, File, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from .cache import (
    add_pinned_chart,
    cache_conn,
    confirm_klant_mapping,
    delete_pinned_chart,
    find_potential_klant_duplicates,
    get_last_sync,
    get_row_count,
    get_uren_extern_summary,
    import_uren_extern,
    init_schema,
    list_pinned_charts,
    reject_klant_mapping,
    reset_pinned_charts,
    seed_default_pinned,
    sync_from_prato,
)
from .import_historisch import (
    get_historisch_summary,
    get_sektie_mappings,
    import_csv_to_historisch,
)
from .metrics import METRIC_REGISTRY, compute, _combine, _period_filter
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
from .segments import SEGMENTS, all_segments, segment_label, segment_where
from .templates import admin_body, dashboards_body, explorer_body, export_body, shell

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("dashboard-nestor")


app = FastAPI(
    title="Dashboard Nestor",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)


# ---------------------------------------------------------------------------
# Scheduler — daily sync 11:59 Europe/Brussels
# ---------------------------------------------------------------------------

_scheduler: Optional[BackgroundScheduler] = None


@app.on_event("startup")
def _on_startup() -> None:
    try:
        init_schema()
        n_seeded = seed_default_pinned()
        if n_seeded:
            log.info("Default-pinned grafieken geseed: %d", n_seeded)
    except Exception:  # noqa: BLE001
        log.exception("init_schema/seed mislukt — cache mogelijk niet schrijfbaar")

    global _scheduler
    _scheduler = BackgroundScheduler(timezone="Europe/Brussels")
    _scheduler.add_job(
        sync_from_prato,
        trigger=CronTrigger(hour=11, minute=59, timezone="Europe/Brussels"),
        id="daily_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    log.info("Scheduler gestart — daily_sync elke dag om 11:59 Europe/Brussels")


@app.on_event("shutdown")
def _on_shutdown() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


# ---------------------------------------------------------------------------
# UI routes
# ---------------------------------------------------------------------------


@app.get("/")
def root_redirect():
    return RedirectResponse(url="/dashboards", status_code=302)


@app.get("/dashboards", response_class=HTMLResponse)
def page_dashboards():
    pinned = list_pinned_charts()
    for p in pinned:
        s = SEGMENTS.get(p["segment"], {})
        p["segment_label"] = s.get("label", p["segment"])
    body = dashboards_body(pinned, all_segments())
    return HTMLResponse(shell("Dashboards", "dashboards", body))


@app.get("/explorer", response_class=HTMLResponse)
def page_explorer():
    body = explorer_body(all_segments(), METRIC_REGISTRY)
    return HTMLResponse(shell("Explorer", "explorer", body))


@app.get("/export", response_class=HTMLResponse)
def page_export():
    return HTMLResponse(shell("Export", "export", export_body()))


@app.get("/admin", response_class=HTMLResponse)
def page_admin():
    summary = get_historisch_summary()
    return HTMLResponse(shell("Admin", "admin", admin_body(summary)))


# ---------------------------------------------------------------------------
# Basis-API
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/status")
def api_status():
    last = get_last_sync()
    return {
        "service": "dashboard.nestor.be",
        "prato_configured": prato_is_configured(),
        "rows_cached": get_row_count(),
        "last_sync": last,
    }


@app.get("/api/segments")
def api_segments():
    return {"segments": all_segments()}


@app.get("/api/metrics")
def api_metrics():
    return {"metrics": METRIC_REGISTRY}


# ---------------------------------------------------------------------------
# KPI summary — voor de cards bovenaan /dashboards
# ---------------------------------------------------------------------------


@app.get("/api/kpi")
def api_kpi(segment: str = Query(...), period_mode: str = Query("ltm")):
    """Geeft totale omzet, marge, marge%, medewerkers + klanten voor een
    segment + periode. Eén aggregate-query op v_margelijst."""
    if segment not in SEGMENTS:
        return JSONResponse(status_code=400, content={"error": f"Onbekend segment: {segment}"})

    seg_w, seg_p = segment_where(segment)
    try:
        per_w, per_p = _period_filter(period_mode, None)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    where, params = _combine([(seg_w, seg_p), (per_w, per_p)])

    sql = f"""
        SELECT
            SUM(omzet_gefactureerd + COALESCE(omzet_te_factureren,0)) AS omzet,
            SUM(marge) AS marge,
            SUM(verloonde_uren) AS uren,
            COUNT(DISTINCT persoonreferentieid) AS mw,
            COUNT(DISTINCT klantreferentieid) AS klanten
        FROM v_margelijst
        WHERE {where}
    """
    with cache_conn() as conn:
        row = conn.execute(sql, params).fetchone()

    omzet = float(row["omzet"] or 0)
    marge = float(row["marge"] or 0)
    marge_pct = (marge / omzet * 100) if omzet else None

    return {
        "segment": segment,
        "segment_label": segment_label(segment),
        "period_mode": period_mode,
        "omzet": round(omzet, 2),
        "marge": round(marge, 2),
        "marge_pct": round(marge_pct, 2) if marge_pct is not None else None,
        "uren": round(float(row["uren"] or 0), 2),
        "medewerkers": int(row["mw"] or 0),
        "klanten": int(row["klanten"] or 0),
    }


# ---------------------------------------------------------------------------
# Filter-values — autocomplete voor de Export-filters
# ---------------------------------------------------------------------------


_FILTER_FIELD_TO_COL = {
    "jaar": "jaar",
    "kwartaal": "kwartaal",
    "maand": "maand",
    "week": "week",
    "vestigingseenheidreferentieid": "vestigingseenheidreferentieid",
    "klantreferentieid": "klantreferentieid",
    "klantnaam": "klantnaam",
    "persoonreferentieid": "persoonreferentieid",
    "familienaam": "familienaam",
    "voornaam": "voornaam",
}


@app.get("/api/filter-values")
def api_filter_values(
    field: str = Query(...),
    q: str = Query("", description="Filter-prefix voor autocomplete"),
    limit: int = Query(50, ge=1, le=200),
):
    """Geeft distinct waarden uit v_margelijst voor een veld, optioneel
    gefilterd op zoekterm (LIKE %q%). Voor de Export-pagina-autocomplete.

    Speciaal: 'klant' returnt {value=klantreferentieid, label=klantnaam};
              'persoon' returnt {value=persoonreferentieid, label='Voornaam Familienaam'}.
    """
    init_schema()

    if field == "klant" or field == "klantreferentieid":
        sql = """
            SELECT DISTINCT klantreferentieid AS value,
                   COALESCE(klantnaam, '(zonder naam)') AS label
            FROM v_margelijst
            WHERE klantreferentieid IS NOT NULL
        """
        params: list = []
        if q:
            sql += " AND (LOWER(klantnaam) LIKE ? OR klantreferentieid LIKE ?)"
            params.extend([f"%{q.lower()}%", f"%{q}%"])
        sql += " ORDER BY label LIMIT ?"
        params.append(limit)
        with cache_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return {"values": [{"value": r["value"], "label": r["label"]} for r in rows]}

    if field == "persoon":
        sql = """
            SELECT DISTINCT persoonreferentieid AS value,
                   COALESCE(voornaam || ' ' || familienaam, familienaam, '(zonder naam)') AS label
            FROM v_margelijst
            WHERE persoonreferentieid IS NOT NULL
        """
        params = []
        if q:
            sql += " AND (LOWER(familienaam) LIKE ? OR LOWER(voornaam) LIKE ? OR persoonreferentieid LIKE ?)"
            params.extend([f"%{q.lower()}%", f"%{q.lower()}%", f"%{q}%"])
        sql += " ORDER BY label LIMIT ?"
        params.append(limit)
        with cache_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return {"values": [{"value": r["value"], "label": r["label"]} for r in rows]}

    col = _FILTER_FIELD_TO_COL.get(field)
    if not col:
        return JSONResponse(status_code=400, content={"error": f"Onbekend veld: {field}"})

    sql = f"SELECT DISTINCT {col} AS value FROM v_margelijst WHERE {col} IS NOT NULL"
    params = []
    if q:
        sql += f" AND CAST({col} AS TEXT) LIKE ?"
        params.append(f"%{q}%")
    sql += f" ORDER BY {col} LIMIT ?"
    params.append(limit)

    with cache_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"values": [{"value": str(r["value"]) if r["value"] is not None else ""} for r in rows]}


# ---------------------------------------------------------------------------
# Admin — historische CSV-upload + sektie-mapping
# ---------------------------------------------------------------------------


@app.post("/admin/import-historisch")
async def admin_import_historisch(file: UploadFile = File(...)):
    """Upload + import van een HIAnt-CSV. Overschrijft margelijst_historisch."""
    raw = await file.read()
    if not raw:
        return JSONResponse(status_code=400, content={"error": "leeg bestand"})
    log.info("AUDIT: import-historisch gestart, file=%s, size=%d", file.filename, len(raw))
    result = import_csv_to_historisch(raw, filename=file.filename or "")
    return result


@app.get("/api/sektie-mappings")
def api_sektie_mappings_list():
    return {"mappings": get_sektie_mappings()}


# POST /api/sektie-mappings is verwijderd: mappings worden hardcoded
# beheerd in app/mappings.py en bij init_schema() in de DB gezet.


@app.get("/api/historisch/summary")
def api_historisch_summary():
    return get_historisch_summary()


# ---------------------------------------------------------------------------
# Klant-merge: verwarrende-lijst + bevestig/verwerp
# ---------------------------------------------------------------------------


@app.get("/api/klant-duplicates")
def api_klant_duplicates(min_score: float = Query(0.70, ge=0.5, le=1.0)):
    """Lijst van klant-paren die mogelijk hetzelfde zijn (HIAnt ↔ Earnie),
    op basis van naam-similarity >= min_score."""
    return {"duplicates": find_potential_klant_duplicates(min_score=min_score, max_results=200)}


@app.post("/api/klant-mapping/confirm")
def api_klant_mapping_confirm(payload: dict = Body(...)):
    try:
        hiant = payload["hiant_klantref"]
        earnie = payload["earnie_klantref"]
    except KeyError as e:
        return JSONResponse(status_code=400, content={"error": f"Missing: {e}"})
    confirm_klant_mapping(str(hiant), str(earnie), payload.get("canonical_naam"))
    return {"ok": True}


@app.post("/api/klant-mapping/reject")
def api_klant_mapping_reject(payload: dict = Body(...)):
    try:
        hiant = payload["hiant_klantref"]
        earnie = payload["earnie_klantref"]
    except KeyError as e:
        return JSONResponse(status_code=400, content={"error": f"Missing: {e}"})
    reject_klant_mapping(str(hiant), str(earnie))
    return {"ok": True}


# ---------------------------------------------------------------------------
# uren_extern: CSV import + summary
# ---------------------------------------------------------------------------


@app.get("/api/uren-extern/summary")
def api_uren_extern_summary():
    return get_uren_extern_summary()


@app.post("/admin/import-uren-extern")
async def admin_import_uren_extern(file: UploadFile = File(...)):
    """CSV-import: jaar;week;segment;uren (BE-decimal, semicolon)."""
    import csv
    import io
    raw = await file.read()
    if not raw:
        return JSONResponse(status_code=400, content={"error": "leeg bestand"})
    log.info("AUDIT: import-uren-extern gestart file=%s size=%d", file.filename, len(raw))
    text = raw.decode("utf-8-sig", errors="replace")
    # Detect delimiter: semicolon (BE) of komma
    delim = ";" if text.count(";") > text.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    rows = []
    for r in reader:
        # Accept zowel hoofd- als kleinletters voor headers
        norm = {k.strip().lower(): v.strip() for k, v in r.items() if k}
        uren_str = norm.get("uren", "").replace(".", "").replace(",", ".") \
            if "," in norm.get("uren", "") else norm.get("uren", "")
        try:
            rows.append({
                "jaar": int(norm.get("jaar", "")),
                "week": int(norm.get("week", "")),
                "segment": norm.get("segment", "").strip().lower(),
                "uren": float(uren_str),
            })
        except (ValueError, TypeError):
            continue
    result = import_uren_extern(rows)
    return {"status": "ok", **result}


# ---------------------------------------------------------------------------
# Metric data — wordt door /dashboards en /explorer aangeroepen
# ---------------------------------------------------------------------------


@app.get("/api/metric")
def api_metric(
    metric: str = Query(...),
    segment: str = Query(...),
    grain: str = Query("month"),
    period_mode: str = Query("ltm"),
    period_value: Optional[str] = Query(None),
    top_n: int = Query(10, ge=1, le=100),
):
    try:
        data = compute(metric, segment, grain, period_mode, period_value, top_n)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:  # noqa: BLE001
        log.exception("metric compute faalde: %s", metric)
        return JSONResponse(
            status_code=503,
            content={"error": f"{type(e).__name__}: {str(e)[:200]}"},
        )

    info = METRIC_REGISTRY.get(metric, {})
    data["unit"] = info.get("unit", "")
    data["chart_type"] = info.get("chart", "line")
    return JSONResponse(content=data)


# ---------------------------------------------------------------------------
# Pinned charts
# ---------------------------------------------------------------------------


@app.get("/api/pinned")
def api_pinned_list():
    return {"pinned": list_pinned_charts()}


@app.post("/api/pinned")
def api_pinned_add(payload: dict = Body(...)):
    try:
        titel = payload["titel"]
        metric = payload["metric"]
        segment = payload["segment"]
    except KeyError as e:
        return JSONResponse(status_code=400, content={"error": f"Missing field: {e}"})

    chart_type = payload.get("chart_type", "line")
    grain = payload.get("grain", "month")
    period_mode = payload.get("period_mode", "ltm")
    period_value = payload.get("period_value")
    extra_options = payload.get("extra_options")
    series_json = payload.get("series_json")  # multi-series support

    # Bij single-series: metric + segment moeten geldig zijn.
    # Bij multi-series (series_json gezet): metric = 'multi' marker, individuele
    # specs binnen series_json worden door de frontend afgehandeld.
    if not series_json:
        if metric not in METRIC_REGISTRY:
            return JSONResponse(status_code=400, content={"error": f"Onbekende metric: {metric}"})
        if segment not in SEGMENTS:
            return JSONResponse(status_code=400, content={"error": f"Onbekend segment: {segment}"})

    new_id = add_pinned_chart(
        titel=titel,
        metric=metric,
        segment=segment,
        chart_type=chart_type,
        grain=grain,
        period_mode=period_mode,
        period_value=period_value,
        extra_options=extra_options,
        series_json=series_json,
    )
    log.info("AUDIT: pin toegevoegd id=%d titel=%r", new_id, titel)
    return {"ok": True, "id": new_id}


@app.post("/admin/reset-pins")
def admin_reset_pins():
    """Wis alle pinned charts en re-seed de defaults uit cache._DEFAULT_PINNED."""
    new_count = reset_pinned_charts()
    log.info("AUDIT: pinned charts gereset, %d nieuwe defaults geseed", new_count)
    return {"ok": True, "new_count": new_count}


@app.delete("/api/pinned/{chart_id}")
def api_pinned_delete(chart_id: int):
    ok = delete_pinned_chart(chart_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "not_found"})
    log.info("AUDIT: pin verwijderd id=%d", chart_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Sync — manuele trigger + status
# ---------------------------------------------------------------------------


@app.post("/sync/run")
def sync_run():
    if not prato_is_configured():
        return JSONResponse(status_code=503, content={"ok": False, "error": "configuration_missing"})
    if _scheduler is None:
        return JSONResponse(status_code=503, content={"ok": False, "error": "scheduler_not_running"})

    existing = _scheduler.get_job("manual_sync")
    if existing is not None and existing.next_run_time is not None:
        return {
            "ok": True,
            "status": "already_scheduled",
            "next_run_time": str(existing.next_run_time),
        }

    run_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    _scheduler.add_job(
        sync_from_prato,
        trigger="date",
        run_date=run_at,
        id="manual_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    log.info("AUDIT: manuele sync getriggerd")
    return {"ok": True, "status": "scheduled", "run_at": run_at.isoformat()}


@app.get("/sync/status")
def sync_status():
    return {"last_sync": get_last_sync(), "rows_cached": get_row_count()}


# ---------------------------------------------------------------------------
# Prato live endpoints (geen cache)
# ---------------------------------------------------------------------------


@app.get("/prato/test-connection")
def prato_test_connection():
    if not prato_is_configured():
        return JSONResponse(status_code=503, content={"ok": False, "error": "configuration_missing"})
    try:
        return test_connection()
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
    if not prato_is_configured():
        return JSONResponse(status_code=503, content={"ok": False, "error": "configuration_missing"})
    try:
        return {"ok": True, **diagnostic_summary()}
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
    jaar: list[int] = Query(default=[]),
    kwartaal: list[int] = Query(default=[]),
    maand: list[int] = Query(default=[]),
    week: list[int] = Query(default=[]),
    vestigingseenheidreferentieid: list[str] = Query(default=[]),
    klantreferentieid: list[str] = Query(default=[]),
    persoonreferentieid: list[str] = Query(default=[]),
    klantnaam: Optional[str] = None,
    familienaam: Optional[str] = None,
    voornaam: Optional[str] = None,
):
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
        "AUDIT: export.csv - ip=%s filters=%s",
        request.headers.get("x-forwarded-for", request.client.host if request.client else "?"),
        {k: v for k, v in filters.items() if v},
    )

    started = time.monotonic()

    def _generator():
        try:
            yield from stream_export_csv(filters)
        except Exception as e:  # noqa: BLE001
            log.exception("export-csv streaming gefaald")
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
