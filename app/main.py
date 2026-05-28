"""Dashboard Nestor — FastAPI entry point.

Endpoints:

  GET  /                           HTML-form met filters + Download + Sync-knop
  GET  /health                     Railway healthcheck
  GET  /api/status                 JSON: laatste sync, aantal rijen
  POST /sync/run                   Trigger manuele sync (background-job)
  GET  /sync/status                JSON: voortgang van eventuele lopende sync
  GET  /prato/test-connection      Live check op Prato Postgres
  GET  /prato/export/diag          Live introspectie van klant-bronnen
  GET  /prato/export.csv           CSV-export uit de SQLite-cache (NIET live)

Auto-sync: APScheduler draait elke dag om 11:59 Europe/Brussels en
overschrijft de cache.

Geen authenticatie in deze versie — URL discreet houden.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from .cache import get_last_sync, get_row_count, init_schema, sync_from_prato
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
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)


# ---------------------------------------------------------------------------
# APScheduler — daily sync at 11:59 Europe/Brussels
# ---------------------------------------------------------------------------

_scheduler: Optional[BackgroundScheduler] = None


@app.on_event("startup")
def _on_startup() -> None:
    """Init cache-schema + start scheduler."""
    try:
        init_schema()
    except Exception:  # noqa: BLE001
        log.exception("init_schema mislukt — cache mogelijk niet schrijfbaar")

    global _scheduler
    _scheduler = BackgroundScheduler(timezone="Europe/Brussels")
    _scheduler.add_job(
        sync_from_prato,
        trigger=CronTrigger(hour=11, minute=59, timezone="Europe/Brussels"),
        id="daily_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,  # 1 uur tolerantie als de container herstart rond 11:59
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
# Basis-endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    """Railway healthcheck — geen auth, geen DB-call."""
    return {"status": "ok"}


@app.get("/api/status")
def api_status():
    """JSON-overzicht voor de UI: configuratie + laatste sync + row count."""
    last = get_last_sync()
    return {
        "service": "dashboard.nestor.be",
        "prato_configured": prato_is_configured(),
        "rows_cached": get_row_count(),
        "last_sync": last,
    }


# ---------------------------------------------------------------------------
# Sync — manuele trigger + status
# ---------------------------------------------------------------------------


@app.post("/sync/run")
def sync_run():
    """Schedule een immediate sync. Returnt direct; sync draait in background."""
    if not prato_is_configured():
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "configuration_missing"},
        )
    if _scheduler is None:
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "scheduler_not_running"},
        )

    # Check of er al een manueel sync-job loopt
    existing = _scheduler.get_job("manual_sync")
    if existing is not None and existing.next_run_time is not None:
        return JSONResponse(
            content={
                "ok": True,
                "status": "already_scheduled",
                "next_run_time": str(existing.next_run_time),
            }
        )

    # Schedule immediate run
    from datetime import timedelta
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
    return JSONResponse(content={"ok": True, "status": "scheduled", "run_at": run_at.isoformat()})


@app.get("/sync/status")
def sync_status():
    """Status van de meest recente sync (running / ok / failed)."""
    last = get_last_sync()
    return {"last_sync": last, "rows_cached": get_row_count()}


# ---------------------------------------------------------------------------
# Prato-endpoints (live, geen cache)
# ---------------------------------------------------------------------------


@app.get("/prato/test-connection")
def prato_test_connection():
    """Snelle live check op de Prato Postgres."""
    if not prato_is_configured():
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "configuration_missing"},
        )
    try:
        return JSONResponse(content=test_connection())
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
    """Live introspectie — hoeveel rijen in de Prato-bronnen?"""
    if not prato_is_configured():
        return JSONResponse(status_code=503, content={"ok": False, "error": "configuration_missing"})
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
    """Stream de margelijst-export als CSV uit de lokale cache.

    Geen Prato-roundtrip. Cache wordt elke dag om 11:59 ververst, of
    handmatig via POST /sync/run.

    Filters: alle 10 dimensies; ID's en periode-onderdelen multi-value
    via herhaalde query-parameters, namen via LIKE.

    Format: UTF-8 zonder BOM, semicolon, Belgische decimaalkomma.
    """
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


# ---------------------------------------------------------------------------
# UI — inline HTML op /
# ---------------------------------------------------------------------------


_UI_HTML = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>Dashboard Nestor — margelijst</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root {
    --fg:#1f2328; --muted:#656d76; --bg:#fff; --panel:#f6f8fa;
    --border:#d0d7de; --accent:#0969da; --ok:#1a7f37; --err:#cf222e;
  }
  * { box-sizing:border-box; }
  body { font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
         margin:0; padding:20px; color:var(--fg); background:var(--bg);
         font-size:14px; }
  h1 { font-size:20px; margin:0 0 16px; }
  h2 { font-size:14px; margin:24px 0 8px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; }
  .container { max-width:980px; margin:0 auto; }
  .panel { background:var(--panel); border:1px solid var(--border);
           border-radius:6px; padding:14px 16px; margin-bottom:16px; }
  .grid { display:grid; grid-template-columns:repeat(2, 1fr); gap:10px 16px; }
  @media (max-width:600px) { .grid { grid-template-columns:1fr; } }
  label { display:block; font-weight:600; margin-bottom:4px; font-size:13px; }
  .hint { color:var(--muted); font-weight:normal; font-size:12px; margin-left:6px; }
  input[type=text], input[type=number] {
    width:100%; padding:6px 8px; border:1px solid var(--border);
    border-radius:6px; font-size:13px; font-family:inherit;
  }
  input:focus { outline:2px solid var(--accent); outline-offset:-1px; }
  .actions { display:flex; gap:10px; margin:18px 0 8px; }
  button { padding:8px 16px; border:1px solid var(--border); background:#fff;
           border-radius:6px; font-size:14px; font-weight:600; cursor:pointer; }
  button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
  button.primary:hover { background:#0860ca; }
  button:hover { background:#f3f4f6; }
  button.primary:hover { background:#0860ca; }
  .status-row { display:flex; gap:24px; flex-wrap:wrap; }
  .status-row > div { min-width:120px; }
  .status-row .lbl { color:var(--muted); font-size:12px; }
  .status-row .val { font-size:15px; font-weight:600; margin-top:2px; }
  .ok { color:var(--ok); }
  .err { color:var(--err); }
  small { color:var(--muted); }
  code { background:#eaeef2; padding:1px 5px; border-radius:3px; font-size:12px; }
</style>
</head>
<body>
<div class="container">
  <h1>Margelijst Nestor</h1>

  <div class="panel" id="status">
    <h2 style="margin-top:0">Status</h2>
    <div class="status-row">
      <div><div class="lbl">Rijen in cache</div><div class="val" id="rows">…</div></div>
      <div><div class="lbl">Laatste sync</div><div class="val" id="last-sync">…</div></div>
      <div><div class="lbl">Sync-status</div><div class="val" id="sync-status">…</div></div>
      <div><div class="lbl">Volgende auto-sync</div><div class="val">elke dag om 11:59 (Europe/Brussels)</div></div>
    </div>
    <div class="actions">
      <button type="button" id="sync-btn">Sync nu</button>
      <small style="align-self:center;">handmatig overschrijven van de cache met Prato-data</small>
    </div>
  </div>

  <form id="export-form" method="get" action="/prato/export.csv">
    <h2>Filters</h2>
    <div class="panel">
      <div class="grid">
        <div>
          <label>jaar <span class="hint">meerdere mogelijk, komma's</span></label>
          <input type="text" name="jaar" id="f-jaar" placeholder="2026">
        </div>
        <div>
          <label>kwartaal <span class="hint">1-4</span></label>
          <input type="text" name="kwartaal" id="f-kwartaal" placeholder="">
        </div>
        <div>
          <label>maand <span class="hint">1-12</span></label>
          <input type="text" name="maand" id="f-maand" placeholder="">
        </div>
        <div>
          <label>week <span class="hint">1-53</span></label>
          <input type="text" name="week" id="f-week" placeholder="">
        </div>
        <div>
          <label>vestigingseenheidreferentieid</label>
          <input type="text" name="vestigingseenheidreferentieid" id="f-vest" placeholder="">
        </div>
        <div>
          <label>klantreferentieid</label>
          <input type="text" name="klantreferentieid" id="f-klantref" placeholder="">
        </div>
        <div>
          <label>klantnaam <span class="hint">deel-match</span></label>
          <input type="text" name="klantnaam" id="f-klantnaam" placeholder="bv. Smartmat">
        </div>
        <div>
          <label>persoonreferentieid</label>
          <input type="text" name="persoonreferentieid" id="f-persoonref" placeholder="">
        </div>
        <div>
          <label>familienaam <span class="hint">deel-match</span></label>
          <input type="text" name="familienaam" id="f-familienaam" placeholder="">
        </div>
        <div>
          <label>voornaam <span class="hint">deel-match</span></label>
          <input type="text" name="voornaam" id="f-voornaam" placeholder="">
        </div>
      </div>
      <div class="actions">
        <button type="submit" class="primary">Download CSV</button>
        <button type="reset">Filters wissen</button>
      </div>
    </div>
  </form>

  <small>
    Output: 22 kolommen in vaste volgorde — UTF-8 (geen BOM), semicolon,
    Belgische decimaalkomma. Marge = omzet_gefactureerd + omzet_te_factureren − kost.
  </small>
</div>

<script>
// Multi-value: een veld met "2025,2026" splitsen we naar twee query-parameters.
// Voor de filters in INT_FILTERS + ID_FILTERS (= alle filters behalve klantnaam/familienaam/voornaam).
const MULTI_FIELDS = ["jaar","kwartaal","maand","week","vestigingseenheidreferentieid","klantreferentieid","persoonreferentieid"];

document.getElementById("export-form").addEventListener("submit", function(e) {
  e.preventDefault();
  const params = new URLSearchParams();
  const form = e.target;
  for (const el of form.elements) {
    if (!el.name || !el.value) continue;
    if (MULTI_FIELDS.includes(el.name)) {
      el.value.split(",").map(s => s.trim()).filter(Boolean).forEach(v => params.append(el.name, v));
    } else {
      params.append(el.name, el.value.trim());
    }
  }
  window.location.href = "/prato/export.csv?" + params.toString();
});

// Status panel
async function refreshStatus() {
  try {
    const r = await fetch("/api/status");
    const d = await r.json();
    document.getElementById("rows").textContent = d.rows_cached.toLocaleString("nl-BE");
    const last = d.last_sync;
    if (last) {
      const when = new Date(last.started_at);
      document.getElementById("last-sync").textContent = when.toLocaleString("nl-BE");
      const st = document.getElementById("sync-status");
      st.textContent = last.status;
      st.className = "val " + (last.status === "ok" ? "ok" : last.status === "failed" ? "err" : "");
    } else {
      document.getElementById("last-sync").textContent = "—";
      document.getElementById("sync-status").textContent = "geen sync uitgevoerd";
    }
  } catch (e) {
    console.error("status fetch failed", e);
  }
}

document.getElementById("sync-btn").addEventListener("click", async function() {
  const btn = this;
  btn.disabled = true;
  btn.textContent = "Sync gepland…";
  try {
    const r = await fetch("/sync/run", { method: "POST" });
    const d = await r.json();
    if (!r.ok) { alert("Sync fout: " + (d.error || r.status)); return; }
  } catch (e) {
    alert("Sync fout: " + e);
  } finally {
    setTimeout(() => { btn.disabled = false; btn.textContent = "Sync nu"; refreshStatus(); }, 2000);
  }
});

refreshStatus();
// Poll elke 10s zodat een lopende sync zichtbaar wordt
setInterval(refreshStatus, 10000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def root_ui():
    return HTMLResponse(content=_UI_HTML)
