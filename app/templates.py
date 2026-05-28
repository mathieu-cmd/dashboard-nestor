"""HTML-templates voor Dashboard Nestor.

Sidebar links + main content rechts. KPI-cards bovenaan /dashboards.
Modernere kleuren (BI-tool look: licht thema, zachte schaduwen, indigo
accent). Multi-select autocomplete-filters via Tom-Select (CDN).
"""

from __future__ import annotations

import html as _html
import json
from typing import Any


_CSS = """
:root {
  --fg:#0f172a; --muted:#64748b; --bg:#f8fafc; --panel:#fff;
  --border:#e2e8f0; --accent:#4f46e5; --accent-soft:#eef2ff;
  --ok:#10b981; --err:#dc2626; --warn:#d97706;
  --sidebar-bg:#0f172a; --sidebar-fg:#cbd5e1; --sidebar-active:#1e293b;
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.05);
  --radius: 10px;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;height:100%}
body{font-family:-apple-system,"Segoe UI",system-ui,sans-serif;font-size:14px;
  color:var(--fg);background:var(--bg);min-height:100vh;
  display:grid;grid-template-columns:240px 1fr;grid-template-rows:1fr;}

/* Sidebar */
.sidebar{background:var(--sidebar-bg);color:var(--sidebar-fg);
  padding:24px 16px;display:flex;flex-direction:column;gap:8px;
  height:100vh;position:sticky;top:0;}
.brand{color:#fff;font-size:16px;font-weight:700;letter-spacing:.3px;
  padding:0 8px 16px;display:flex;align-items:center;gap:8px;
  border-bottom:1px solid #1e293b;margin-bottom:12px;}
.brand .dot{width:10px;height:10px;border-radius:50%;background:var(--accent);
  box-shadow:0 0 12px rgba(79,70,229,.6);}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:8px;
  color:var(--sidebar-fg);text-decoration:none;font-weight:500;font-size:13.5px;}
.nav-item:hover{background:#1e293b;color:#fff}
.nav-item.active{background:var(--sidebar-active);color:#fff;
  box-shadow:inset 3px 0 0 var(--accent)}
.nav-item .ic{width:18px;height:18px;display:inline-flex;justify-content:center;
  align-items:center;opacity:.8;font-size:14px}
.sidebar .spacer{flex:1}
.sidebar .footer{font-size:11px;color:#475569;padding:8px;line-height:1.5;
  border-top:1px solid #1e293b;margin-top:12px;}
.sidebar .footer .live{color:#10b981}
.sidebar .footer .err{color:#f87171}

/* Main */
main{padding:24px 28px;overflow-x:hidden;}
h1{font-size:22px;margin:0 0 4px;font-weight:700;letter-spacing:-.3px}
.subtitle{color:var(--muted);font-size:13px;margin:0 0 24px}
h2{font-size:13px;margin:24px 0 10px;color:var(--muted);
  text-transform:uppercase;letter-spacing:.6px;font-weight:600}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:18px}
.toolbar label{font-size:12px;color:var(--muted);font-weight:600;
  text-transform:uppercase;letter-spacing:.5px}
.toolbar select{padding:6px 10px;border:1px solid var(--border);border-radius:8px;
  background:#fff;font:inherit;font-size:13px;cursor:pointer}

/* Cards */
.card{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);
  box-shadow:var(--shadow-sm);padding:18px;}
.card h3{font-size:14px;margin:0 0 12px;font-weight:600;padding-right:80px}
.card .meta{color:var(--muted);font-size:11px;margin-bottom:10px;
  text-transform:uppercase;letter-spacing:.4px}

/* KPI row */
.kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px}
@media (max-width:1100px){.kpi-row{grid-template-columns:repeat(2,1fr)}}
.kpi{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);
  padding:16px 18px;box-shadow:var(--shadow-sm);position:relative;}
.kpi .lbl{color:var(--muted);font-size:11px;font-weight:600;
  text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.kpi .val{font-size:24px;font-weight:700;line-height:1.1;letter-spacing:-.5px}
.kpi .sub{color:var(--muted);font-size:11px;margin-top:8px}

/* Charts grid */
.charts-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
@media (max-width:1100px){.charts-grid{grid-template-columns:1fr}}
.chart-card{background:var(--panel);border:1px solid var(--border);
  border-radius:var(--radius);box-shadow:var(--shadow-sm);padding:16px 18px;
  position:relative}
.chart-card h3{font-size:14px;margin:0 0 4px;padding-right:80px}
.chart-card .meta{color:var(--muted);font-size:11px;margin-bottom:12px}
.chart-card .canvas-wrap{position:relative;height:260px}
.chart-card canvas{max-height:260px !important}
.chart-card .unpin{position:absolute;top:14px;right:14px;
  padding:4px 8px;font-size:11px;font-weight:600;background:#fff;
  border:1px solid var(--border);color:var(--err);border-radius:6px;
  cursor:pointer;opacity:.6}
.chart-card .unpin:hover{opacity:1;background:#fef2f2}
.chart-card .empty,.chart-card .loading{color:var(--muted);text-align:center;
  padding:80px 0;font-size:13px;font-style:italic}

/* Forms */
.panel{background:var(--panel);border:1px solid var(--border);
  border-radius:var(--radius);box-shadow:var(--shadow-sm);
  padding:18px;margin-bottom:16px}
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:12px 16px}
@media (max-width:700px){.grid2{grid-template-columns:1fr}}
label{display:block;font-weight:600;margin-bottom:5px;font-size:12.5px}
label .hint{color:var(--muted);font-weight:400;font-size:11px;margin-left:6px}
input[type=text],input[type=number],input[type=file],select,textarea{
  width:100%;padding:8px 10px;border:1px solid var(--border);
  border-radius:8px;font-size:13px;font-family:inherit;background:#fff}
input:focus,select:focus,textarea:focus{outline:2px solid var(--accent);
  outline-offset:-1px;border-color:transparent}
.actions{display:flex;gap:10px;margin:16px 0 0;flex-wrap:wrap}
button{padding:8px 16px;border:1px solid var(--border);background:#fff;
  border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;
  font-family:inherit;transition:all .12s}
button:hover{background:#f1f5f9}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent);
  box-shadow:0 1px 3px rgba(79,70,229,.3)}
button.primary:hover{background:#4338ca;box-shadow:0 2px 6px rgba(79,70,229,.4)}
button.danger{color:var(--err);border-color:var(--err)}
button.danger:hover{background:#fef2f2}
button:disabled{opacity:.5;cursor:not-allowed}

.status-row{display:flex;gap:24px;flex-wrap:wrap}
.status-row > div{min-width:140px}
.status-row .lbl{color:var(--muted);font-size:11px;text-transform:uppercase;
  font-weight:600;letter-spacing:.4px}
.status-row .val{font-size:15px;font-weight:600;margin-top:2px}
.ok{color:var(--ok)}.err{color:var(--err)}.warn{color:var(--warn)}
small{color:var(--muted)}
code{background:#f1f5f9;padding:1px 6px;border-radius:4px;font-size:12px;
  font-family:"SF Mono",Menlo,monospace}

/* Tom-Select theme overrides */
.ts-control{border:1px solid var(--border) !important;border-radius:8px !important;
  padding:6px 8px !important;font-size:13px !important;box-shadow:none !important;
  min-height:36px !important}
.ts-control.focus{outline:2px solid var(--accent);outline-offset:-1px}
.ts-dropdown{border:1px solid var(--border) !important;border-radius:8px !important;
  box-shadow:var(--shadow-md) !important;font-size:13px !important}
.ts-control .item{background:var(--accent-soft) !important;
  color:var(--accent) !important;border:none !important;
  border-radius:4px !important;padding:2px 8px !important;
  font-weight:500 !important}
"""


def _icon(name: str) -> str:
    return {
        "dashboards": "📊",
        "explorer": "🔍",
        "export": "⬇",
        "admin": "⚙",
    }.get(name, "•")


def shell(title: str, active: str, body: str) -> str:
    def navlink(href: str, key: str, label: str) -> str:
        cls = "nav-item active" if key == active else "nav-item"
        return (
            f'<a class="{cls}" href="{href}">'
            f'<span class="ic">{_icon(key)}</span>{label}</a>'
        )

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>{_html.escape(title)} — Dashboard Nestor</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://cdn.jsdelivr.net">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/css/tom-select.css">
<script src="https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/js/tom-select.complete.min.js"></script>
<style>{_CSS}</style>
</head>
<body>
<aside class="sidebar">
  <div class="brand"><span class="dot"></span>Dashboard Nestor</div>
  {navlink('/dashboards', 'dashboards', 'Dashboards')}
  {navlink('/explorer', 'explorer', 'Explorer')}
  {navlink('/export', 'export', 'Export')}
  {navlink('/admin', 'admin', 'Admin')}
  <div class="spacer"></div>
  <div class="footer" id="footer-status">…</div>
</aside>
<main>{body}</main>
<script>
window.fmtEur = (v) => v == null ? "—" :
  new Intl.NumberFormat("nl-BE", {{ style:"currency", currency:"EUR", maximumFractionDigits: 0 }}).format(v);
window.fmtNum = (v, dec=2) => v == null ? "—" :
  new Intl.NumberFormat("nl-BE", {{ minimumFractionDigits: dec, maximumFractionDigits: dec }}).format(v);
window.unitFormatter = (unit) => {{
  if (unit === "EUR") return window.fmtEur;
  if (unit === "uur" || unit === "uur/pers") return (v) => window.fmtNum(v, 1) + " " + unit;
  if (unit === "%") return (v) => window.fmtNum(v, 2) + "%";
  return (v) => window.fmtNum(v, 0);
}};

async function refreshFooter() {{
  try {{
    const r = await fetch("/api/status");
    const d = await r.json();
    const last = d.last_sync;
    const rows = (d.rows_cached || 0).toLocaleString("nl-BE");
    let st = "—";
    if (last) {{
      const cls = last.status === "ok" ? "live" : last.status === "failed" ? "err" : "";
      const when = new Date(last.started_at);
      st = `<span class="${{cls}}">${{last.status}}</span> · ` +
           when.toLocaleString("nl-BE", {{month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}});
    }}
    document.getElementById("footer-status").innerHTML =
      `<div><strong>${{rows}}</strong> rijen in cache</div><div>${{st}}</div>`;
  }} catch (e) {{}}
}}
refreshFooter();
setInterval(refreshFooter, 15000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------


def dashboards_body(pinned: list[dict[str, Any]], segments: list[dict]) -> str:
    seg_opts = "\n".join(
        f'<option value="{s["key"]}">{_html.escape(s["label"])}</option>' for s in segments
    )

    cards_html = "" if pinned else """
<div class="card"><p style="margin:0">Nog geen vastgepinde grafieken.
Ga naar <a href="/explorer" style="color:var(--accent);font-weight:600">Explorer</a>
om er toe te voegen.</p></div>"""

    for p in pinned:
        chart_id = f"chart-{p['id']}"
        meta_bits = [p.get("segment_label", p["segment"])]
        if p.get("period_mode"):
            meta_bits.append(p["period_mode"])
        meta = " · ".join(meta_bits)
        cards_html += f"""
<div class="chart-card" data-id="{p['id']}">
  <h3>{_html.escape(p['titel'])}</h3>
  <div class="meta">{_html.escape(meta)}</div>
  <button class="unpin" onclick="unpin({p['id']})">Verwijder</button>
  <div class="canvas-wrap"><canvas id="{chart_id}"></canvas></div>
</div>"""

    pinned_json = json.dumps([{
        "id": p["id"], "metric": p["metric"], "segment": p["segment"],
        "chart_type": p["chart_type"], "grain": p["grain"],
        "period_mode": p["period_mode"],
        "period_value": p.get("period_value"),
        "extra_options": p.get("extra_options"),
    } for p in pinned])

    return f"""
<h1>Dashboards</h1>
<p class="subtitle">Vastgepinde KPI-grafieken — vernieuwen automatisch bij elke sync.</p>

<div class="panel" id="sync-bar"
     style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;justify-content:space-between">
  <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
    <div>
      <div class="lbl" style="color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Laatste sync</div>
      <div class="val" id="db-last-sync" style="font-size:14px;font-weight:600;margin-top:2px">…</div>
    </div>
    <div>
      <div class="lbl" style="color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Status</div>
      <div class="val" id="db-sync-status" style="font-size:14px;font-weight:600;margin-top:2px">…</div>
    </div>
    <div>
      <div class="lbl" style="color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Rijen in cache</div>
      <div class="val" id="db-rows" style="font-size:14px;font-weight:600;margin-top:2px">…</div>
    </div>
    <div>
      <div class="lbl" style="color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Auto-sync</div>
      <div class="val" style="font-size:14px;font-weight:600;margin-top:2px">dagelijks 11:59</div>
    </div>
  </div>
  <button class="primary" id="db-sync-btn"
          style="font-size:14px;padding:10px 20px;box-shadow:0 2px 8px rgba(79,70,229,.35)">
    ↻ Sync Prato nu
  </button>
</div>

<div class="kpi-row" id="kpi-row">
  <div class="kpi"><div class="lbl">Omzet (LTM, Nestor Core)</div><div class="val" id="kpi-omzet">…</div></div>
  <div class="kpi"><div class="lbl">Bruto marge (LTM)</div><div class="val" id="kpi-marge">…</div></div>
  <div class="kpi"><div class="lbl">Marge %</div><div class="val" id="kpi-margepct">…</div></div>
  <div class="kpi"><div class="lbl">Actieve medewerkers</div><div class="val" id="kpi-mw">…</div></div>
</div>

<h2>Grafieken</h2>
<div class="charts-grid">
{cards_html}
</div>

<script>
const PINNED = {pinned_json};
async function renderChart(p) {{
  const params = new URLSearchParams({{
    metric:p.metric, segment:p.segment, grain:p.grain, period_mode:p.period_mode
  }});
  if (p.period_value) params.append("period_value", p.period_value);
  if (p.extra_options) {{
    try {{ const eo = JSON.parse(p.extra_options);
           if (eo.top_n) params.append("top_n", eo.top_n); }} catch (e) {{}}
  }}
  try {{
    const r = await fetch("/api/metric?" + params.toString());
    const d = await r.json();
    const canvas = document.getElementById("chart-" + p.id);
    if (!d.labels || d.labels.length === 0) {{
      canvas.parentNode.innerHTML = '<div class="empty">Geen data voor deze selectie.</div>';
      return;
    }}
    const fmt = window.unitFormatter(d.unit || "");
    new Chart(canvas, {{
      type: p.chart_type,
      data: {{ labels:d.labels, datasets:[{{
        label:d.metric, data:d.values,
        borderColor:"#4f46e5",
        backgroundColor: p.chart_type==="bar" ? "#4f46e5" : "rgba(79,70,229,0.1)",
        fill: p.chart_type==="line", tension:0.25, borderWidth:2,
        pointRadius:3, pointHoverRadius:5,
      }}] }},
      options: {{ responsive:true, maintainAspectRatio:false,
        plugins:{{ legend:{{display:false}},
          tooltip:{{callbacks:{{label:(ctx)=>fmt(ctx.parsed.y??ctx.parsed)}}}}}},
        scales:{{ y:{{ticks:{{callback:(v)=>fmt(v)}}}}, x:{{grid:{{display:false}}}}}}
      }}
    }});
  }} catch (e) {{
    console.error("chart load failed", p.id, e);
    document.getElementById("chart-"+p.id).parentNode.innerHTML =
      '<div class="empty">Fout bij laden.</div>';
  }}
}}
async function unpin(id) {{
  if (!confirm("Deze grafiek verwijderen?")) return;
  const r = await fetch("/api/pinned/" + id, {{method:"DELETE"}});
  if (r.ok) location.reload();
}}

// Vaste KPI: Nestor Core, laatste 12 maanden
async function refreshKpis() {{
  try {{
    const r = await fetch("/api/kpi?segment=nestor_core&period_mode=ltm");
    const d = await r.json();
    document.getElementById("kpi-omzet").textContent = window.fmtEur(d.omzet);
    document.getElementById("kpi-marge").textContent = window.fmtEur(d.marge);
    document.getElementById("kpi-margepct").textContent =
      d.marge_pct == null ? "—" : window.fmtNum(d.marge_pct, 2) + "%";
    document.getElementById("kpi-mw").textContent =
      (d.medewerkers || 0).toLocaleString("nl-BE");
  }} catch (e) {{ console.error("kpi", e); }}
}}

// Sync-bar status
async function refreshSyncBar() {{
  try {{
    const r = await fetch("/api/status");
    const d = await r.json();
    document.getElementById("db-rows").textContent =
      (d.rows_cached || 0).toLocaleString("nl-BE");
    const last = d.last_sync;
    if (last) {{
      document.getElementById("db-last-sync").textContent =
        new Date(last.started_at).toLocaleString("nl-BE");
      const st = document.getElementById("db-sync-status");
      st.textContent = last.status;
      st.className = "val " + (last.status === "ok" ? "ok" : last.status === "failed" ? "err" : "warn");
    }} else {{
      document.getElementById("db-last-sync").textContent = "—";
      document.getElementById("db-sync-status").textContent = "—";
    }}
  }} catch (e) {{}}
}}

// Sync-knop
document.getElementById("db-sync-btn").addEventListener("click", async function() {{
  const btn = this; btn.disabled = true;
  const orig = btn.textContent; btn.textContent = "Sync gepland…";
  try {{
    const r = await fetch("/sync/run", {{method:"POST"}});
    const d = await r.json();
    if (!r.ok) alert("Sync fout: " + (d.error || r.status));
  }} catch (e) {{ alert("Sync fout: " + e); }}
  finally {{
    setTimeout(() => {{ btn.disabled = false; btn.textContent = orig; refreshSyncBar(); refreshKpis(); }}, 2000);
  }}
}});

refreshSyncBar(); refreshKpis();
setInterval(refreshSyncBar, 10000);
PINNED.forEach(renderChart);
</script>
"""


# ---------------------------------------------------------------------------
# Explorer
# ---------------------------------------------------------------------------


def explorer_body(segments: list[dict], metrics: dict[str, dict]) -> str:
    seg_opts = "\n".join(
        f'<option value="{s["key"]}">{_html.escape(s["label"])}</option>' for s in segments
    )
    metric_opts = "\n".join(
        f'<option value="{k}" data-type="{v["type"]}" data-chart="{v["chart"]}" '
        f'data-unit="{v["unit"]}" data-needs-top-n="{int(v.get("needs_top_n", False))}">{_html.escape(v["label"])}</option>'
        for k, v in metrics.items()
    )

    return f"""
<h1>Explorer</h1>
<p class="subtitle">Genereer ad-hoc grafieken; pin ze om in het dashboard te bewaren.</p>

<div class="panel">
  <h2 style="margin-top:0">Configuratie</h2>
  <div class="grid2">
    <div><label>Metric</label><select id="m-metric">{metric_opts}</select></div>
    <div><label>Segment</label><select id="m-segment">{seg_opts}</select></div>
    <div><label>Grain</label><select id="m-grain">
      <option value="month">Maand</option>
      <option value="week">Week</option>
      <option value="year">Jaar</option>
    </select></div>
    <div><label>Periode</label><select id="m-period">
      <option value="ltm" selected>Laatste 12 maanden</option>
      <option value="ytd">Year-to-date</option>
      <option value="year">Specifiek jaar</option>
      <option value="all">Volledige historiek</option>
    </select></div>
    <div id="m-period-year-wrap" style="display:none">
      <label>Jaar <span class="hint">bv. 2026</span></label>
      <input type="number" id="m-period-year" min="2000" max="2100">
    </div>
    <div id="m-top-n-wrap" style="display:none">
      <label>Top N</label>
      <input type="number" id="m-top-n" min="3" max="50" value="10">
    </div>
  </div>
  <div class="actions">
    <button class="primary" id="btn-generate">Genereer</button>
    <button id="btn-pin" disabled>Pin op dashboard</button>
  </div>
</div>

<div id="result"></div>

<script>
const metricSel = document.getElementById("m-metric");
const grainSel = document.getElementById("m-grain");
const periodSel = document.getElementById("m-period");
const periodYearWrap = document.getElementById("m-period-year-wrap");
const periodYearInp = document.getElementById("m-period-year");
const topNWrap = document.getElementById("m-top-n-wrap");
const topNInp = document.getElementById("m-top-n");
const segmentSel = document.getElementById("m-segment");
const btnGenerate = document.getElementById("btn-generate");
const btnPin = document.getElementById("btn-pin");
const resultDiv = document.getElementById("result");

let lastSpec = null;
let currentChart = null;

function updateMetricUI() {{
  const opt = metricSel.options[metricSel.selectedIndex];
  topNWrap.style.display = opt.dataset.needsTopN === "1" ? "" : "none";
  const isLtmRolling = opt.dataset.type === "ltm_rolling";
  grainSel.disabled = isLtmRolling;
  periodSel.disabled = isLtmRolling;
}}
function updatePeriodUI() {{
  periodYearWrap.style.display = periodSel.value === "year" ? "" : "none";
}}
metricSel.addEventListener("change", updateMetricUI);
periodSel.addEventListener("change", updatePeriodUI);
updateMetricUI(); updatePeriodUI();

btnGenerate.addEventListener("click", async () => {{
  const opt = metricSel.options[metricSel.selectedIndex];
  const metric = metricSel.value, segment = segmentSel.value;
  const grain = grainSel.value, period_mode = periodSel.value;
  const period_value = periodSel.value === "year" ? periodYearInp.value : null;
  const chart_type = opt.dataset.chart, unit = opt.dataset.unit;
  const needsTopN = opt.dataset.needsTopN === "1";

  const params = new URLSearchParams({{metric, segment, grain, period_mode}});
  if (period_value) params.append("period_value", period_value);
  if (needsTopN) params.append("top_n", topNInp.value || 10);

  resultDiv.innerHTML = '<div class="card"><div class="loading">Genereren…</div></div>';
  try {{
    const r = await fetch("/api/metric?" + params.toString());
    if (!r.ok) {{
      const err = await r.json().catch(()=>({{}}));
      resultDiv.innerHTML = '<div class="card err">Fout: ' + (err.error||r.status) + '</div>';
      return;
    }}
    const d = await r.json();
    lastSpec = {{ metric, segment, grain, period_mode, period_value, chart_type,
                  top_n: needsTopN ? topNInp.value : null, unit,
                  segment_label: d.segment_label, metric_label: opt.text }};

    resultDiv.innerHTML = `<div class="card">
      <h3>${{opt.text}} — ${{d.segment_label}}</h3>
      <div class="canvas-wrap" style="height:380px"><canvas id="explorer-chart"></canvas></div>
    </div>`;
    const canvas = document.getElementById("explorer-chart");
    const fmt = window.unitFormatter(unit);
    if (!d.labels || d.labels.length === 0) {{
      canvas.parentNode.innerHTML = '<div class="empty">Geen data.</div>';
      btnPin.disabled = false;
      return;
    }}
    currentChart = new Chart(canvas, {{
      type: chart_type,
      data: {{ labels:d.labels, datasets:[{{
        label:opt.text, data:d.values,
        borderColor:"#4f46e5",
        backgroundColor: chart_type==="bar" ? "#4f46e5" : "rgba(79,70,229,0.1)",
        fill: chart_type==="line", tension:0.25, borderWidth:2,
      }}] }},
      options: {{ responsive:true, maintainAspectRatio:false,
        plugins:{{legend:{{display:false}},
          tooltip:{{callbacks:{{label:(ctx)=>fmt(ctx.parsed.y??ctx.parsed)}}}}}},
        scales:{{y:{{ticks:{{callback:(v)=>fmt(v)}}}}, x:{{grid:{{display:false}}}}}}
      }}
    }});
    btnPin.disabled = false;
  }} catch (e) {{ resultDiv.innerHTML = '<div class="card err">'+e+'</div>'; }}
}});

btnPin.addEventListener("click", async () => {{
  if (!lastSpec) return;
  const defT = `${{lastSpec.metric_label}} — ${{lastSpec.segment_label}}`;
  const titel = prompt("Titel:", defT);
  if (!titel) return;
  const payload = {{
    titel, metric: lastSpec.metric, segment: lastSpec.segment,
    chart_type: lastSpec.chart_type, grain: lastSpec.grain,
    period_mode: lastSpec.period_mode, period_value: lastSpec.period_value || null,
  }};
  if (lastSpec.top_n) payload.extra_options = JSON.stringify({{top_n:parseInt(lastSpec.top_n,10)}});
  const r = await fetch("/api/pinned", {{
    method:"POST", headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify(payload)
  }});
  if (r.ok) alert("Vastgepind. Zie Dashboards.");
  else {{ const err = await r.json().catch(()=>({{}})); alert("Fout: "+(err.error||r.status)); }}
}});
</script>
"""


# ---------------------------------------------------------------------------
# Export — autocomplete-filters via Tom-Select
# ---------------------------------------------------------------------------


def export_body() -> str:
    return """
<h1>Margelijst — Export</h1>
<p class="subtitle">Filter de cache en download de exacte CSV.</p>

<div class="panel" id="status-panel">
  <h2 style="margin-top:0">Cache-status</h2>
  <div class="status-row">
    <div><div class="lbl">Rijen</div><div class="val" id="rows">…</div></div>
    <div><div class="lbl">Laatste sync</div><div class="val" id="last-sync">…</div></div>
    <div><div class="lbl">Status</div><div class="val" id="sync-status">…</div></div>
    <div><div class="lbl">Auto-sync</div><div class="val">dagelijks 11:59 Europe/Brussels</div></div>
  </div>
  <div class="actions">
    <button id="sync-btn">Sync nu</button>
    <small style="align-self:center">overschrijft cache met live Prato-data</small>
  </div>
</div>

<form id="export-form" method="get" action="/prato/export.csv">
  <h2>Filters</h2>
  <div class="panel">
    <div class="grid2">
      <div><label>jaar <span class="hint">multi-select</span></label>
        <select multiple id="f-jaar" name="jaar"></select></div>
      <div><label>kwartaal</label>
        <select multiple id="f-kwartaal" name="kwartaal"></select></div>
      <div><label>maand</label>
        <select multiple id="f-maand" name="maand"></select></div>
      <div><label>week</label>
        <select multiple id="f-week" name="week"></select></div>
      <div><label>vestiging</label>
        <select multiple id="f-vest" name="vestigingseenheidreferentieid"></select></div>
      <div><label>klant <span class="hint">type om te zoeken</span></label>
        <select multiple id="f-klant" name="klantreferentieid"></select></div>
      <div><label>persoon — naam <span class="hint">type om te zoeken</span></label>
        <select multiple id="f-persoon-naam"></select>
        <input type="hidden" id="f-familienaam" name="familienaam">
        <input type="hidden" id="f-voornaam" name="voornaam">
      </div>
      <div><label>klantnaam <span class="hint">vrij tekstveld (LIKE)</span></label>
        <input type="text" name="klantnaam" placeholder="bv. Smartmat"></div>
    </div>
    <div class="actions">
      <button type="submit" class="primary">Download CSV</button>
      <button type="reset" id="btn-reset">Filters wissen</button>
    </div>
  </div>
</form>

<small>22 kolommen — UTF-8 zonder BOM, semicolon, Belgische decimaalkomma.</small>

<script>
// Multi-select autocomplete via Tom-Select voor elk veld.
// Periode-velden (jaar/kwartaal/maand/week) krijgen statische opties.
function initStatic(id, options) {
  return new TomSelect("#" + id, {
    plugins: ["remove_button"],
    options: options.map(o => ({value: o, text: o})),
    maxItems: null, hideSelected: true,
    placeholder: "Alles",
  });
}
const tsJaar = initStatic("f-jaar", []);
const tsKw   = initStatic("f-kwartaal", [1,2,3,4]);
const tsMnd  = initStatic("f-maand", [1,2,3,4,5,6,7,8,9,10,11,12]);
const tsWk   = initStatic("f-week", Array.from({length:53}, (_,i)=>i+1));

// Vestiging, klant, persoon: autocomplete via /api/filter-values
function initAutocomplete(id, field, labelField=null) {
  return new TomSelect("#" + id, {
    plugins: ["remove_button"],
    valueField: "value", labelField: labelField || "value",
    searchField: labelField ? ["value", labelField] : ["value"],
    maxItems: null, hideSelected: true,
    placeholder: "Type 2 letters om te zoeken…",
    load: async function(query, callback) {
      if (!query || query.length < 2) { callback(); return; }
      try {
        const r = await fetch(`/api/filter-values?field=${field}&q=` + encodeURIComponent(query));
        const d = await r.json();
        callback(d.values || []);
      } catch (e) { callback(); }
    },
    create: false,
  });
}
const tsVest = initAutocomplete("f-vest", "vestigingseenheidreferentieid");
const tsKlant = initAutocomplete("f-klant", "klantreferentieid", "label");
const tsPersoon = initAutocomplete("f-persoon-naam", "persoon", "label");

// Vul jaar-opties dynamisch
fetch("/api/filter-values?field=jaar&q=").then(r=>r.json()).then(d=>{
  (d.values || []).forEach(v => tsJaar.addOption({value: v.value, text: v.value}));
});

// Bij submit: bouw URL met multi-value params + familienaam/voornaam uit persoon-keuze
document.getElementById("export-form").addEventListener("submit", function(e) {
  e.preventDefault();
  const params = new URLSearchParams();
  const f = e.target;
  [tsJaar, tsKw, tsMnd, tsWk, tsVest, tsKlant].forEach(ts => {
    const name = ts.input.name;
    ts.getValue().forEach(v => params.append(name, v));
  });
  // Persoon: gekozen items zijn refs. Geen aparte familienaam/voornaam parsing nodig
  // tenzij gebruiker zelf een tekst typt — dan vallen we terug op klantnaam-stijl LIKE.
  // Hier vragen we ipv multi-value persoonreferentieid:
  tsPersoon.getValue().forEach(v => params.append("persoonreferentieid", v));
  const klantnaam = f.elements["klantnaam"].value.trim();
  if (klantnaam) params.append("klantnaam", klantnaam);
  window.location.href = "/prato/export.csv?" + params.toString();
});

document.getElementById("btn-reset").addEventListener("click", () => {
  setTimeout(() => {
    [tsJaar, tsKw, tsMnd, tsWk, tsVest, tsKlant, tsPersoon].forEach(ts => ts.clear());
  }, 10);
});

// Status panel
async function refreshStatus() {
  try {
    const r = await fetch("/api/status");
    const d = await r.json();
    document.getElementById("rows").textContent = d.rows_cached.toLocaleString("nl-BE");
    const last = d.last_sync;
    if (last) {
      document.getElementById("last-sync").textContent =
        new Date(last.started_at).toLocaleString("nl-BE");
      const st = document.getElementById("sync-status");
      st.textContent = last.status;
      st.className = "val " + (last.status === "ok" ? "ok" : last.status === "failed" ? "err" : "");
    } else {
      document.getElementById("last-sync").textContent = "—";
      document.getElementById("sync-status").textContent = "—";
    }
  } catch (e) {}
}
document.getElementById("sync-btn").addEventListener("click", async function() {
  const btn = this; btn.disabled = true; btn.textContent = "Sync gepland…";
  try {
    const r = await fetch("/sync/run", {method:"POST"});
    const d = await r.json();
    if (!r.ok) alert("Sync fout: " + (d.error || r.status));
  } catch (e) { alert("Sync fout: " + e); }
  finally { setTimeout(()=>{btn.disabled=false; btn.textContent="Sync nu"; refreshStatus();}, 2000); }
});
refreshStatus(); setInterval(refreshStatus, 10000);
</script>
"""


# ---------------------------------------------------------------------------
# Admin — historisch import, sektie mapping
# ---------------------------------------------------------------------------


def admin_body(historisch_summary: dict[str, Any]) -> str:
    sektie_rows = "".join(
        f"<tr><td><code>{_html.escape(s['code'])}</code></td>"
        f"<td>{s['count']:,}</td></tr>"
        for s in (historisch_summary.get("sekties_top20") or [])
    ).replace(",", ".")

    last_imp = historisch_summary.get("last_import")
    last_imp_html = "—"
    if last_imp:
        last_imp_html = (
            f"{last_imp.get('status')} · "
            f"{last_imp.get('rows_loaded','?')} rijen · "
            f"{last_imp.get('started_at','')[:19]}"
        )

    return f"""
<h1>Admin</h1>
<p class="subtitle">Beheer van historische data en sektie-mapping.</p>

<h2>Historische data</h2>
<div class="panel">
  <div class="status-row">
    <div><div class="lbl">Rijen historisch</div><div class="val">{historisch_summary.get('rows', 0):,}</div></div>
    <div><div class="lbl">Periode</div><div class="val">{historisch_summary.get('periode_van') or '—'} → {historisch_summary.get('periode_tot') or '—'}</div></div>
    <div><div class="lbl">Sekties gemapped</div><div class="val">{historisch_summary.get('sekties_mapped', 0)} <small>van {len(historisch_summary.get('sekties_top20') or [])} top-codes</small></div></div>
    <div><div class="lbl">Laatste import</div><div class="val">{_html.escape(last_imp_html)}</div></div>
  </div>
</div>

<div class="panel">
  <h2 style="margin-top:0">Historische CSV uploaden</h2>
  <form id="import-form" enctype="multipart/form-data">
    <label>CSV-bestand <span class="hint">HIAnt-formaat (de geleverde bijlage)</span></label>
    <input type="file" id="csv-file" name="file" accept=".csv,text/csv" required>
    <div class="actions">
      <button type="submit" class="primary" id="import-btn">Importeren (overschrijft historiek)</button>
      <small id="import-status" style="align-self:center"></small>
    </div>
  </form>
</div>

<h2>Sektie → werknemerskengetal mapping</h2>
<div class="panel">
  <p style="margin:0 0 12px;color:var(--muted);font-size:13px">
    De historische CSV gebruikt sektie-codes die niet 1-op-1 mappen op de
    Prato-kengetallen (015, 050, 450, …). Maak hieronder de mapping aan
    zodat segmenteringen op statuut ook voor historische data werken.
  </p>

  <h3 style="font-size:13px;margin:16px 0 8px">Sektie-codes in de historiek (top 20)</h3>
  <table style="border-collapse:collapse;width:auto;font-size:13px">
    <thead><tr style="text-align:left;color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase">
      <th style="padding:4px 12px 4px 0">code</th><th>rijen</th></tr></thead>
    <tbody>{sektie_rows}</tbody>
  </table>

  <h3 style="font-size:13px;margin:20px 0 8px">Mappings bewerken</h3>
  <div id="mappings-table"></div>
  <div class="actions">
    <button type="button" id="add-row">+ Regel toevoegen</button>
    <button type="button" class="primary" id="save-mappings">Mappings opslaan</button>
    <small id="map-status" style="align-self:center"></small>
  </div>
</div>

<script>
const importBtn = document.getElementById("import-btn");
const importStatus = document.getElementById("import-status");
document.getElementById("import-form").addEventListener("submit", async (e) => {{
  e.preventDefault();
  const file = document.getElementById("csv-file").files[0];
  if (!file) return;
  if (!confirm("Bestaande historische data wordt overschreven. Doorgaan?")) return;
  importBtn.disabled = true; importStatus.textContent = "Bezig met importeren…";
  const fd = new FormData(); fd.append("file", file);
  try {{
    const r = await fetch("/admin/import-historisch", {{method:"POST", body:fd}});
    const d = await r.json();
    if (r.ok && d.status === "ok") {{
      importStatus.innerHTML = `<span class="ok">${{d.rows_loaded}} rijen geladen in ${{d.duration_ms}} ms.</span>`;
      setTimeout(() => location.reload(), 1500);
    }} else {{
      importStatus.innerHTML = `<span class="err">Fout: ${{d.error || d.status || r.status}}</span>`;
    }}
  }} catch (err) {{
    importStatus.innerHTML = `<span class="err">${{err}}</span>`;
  }} finally {{
    importBtn.disabled = false;
  }}
}});

// Sektie-mapping
function rowHtml(idx, sek, kg, om) {{
  return `<tr data-idx="${{idx}}">
    <td><input type="text" class="m-sek" value="${{sek||''}}" placeholder="7115" style="width:80px"></td>
    <td><input type="text" class="m-kg" value="${{kg||''}}" placeholder="015" style="width:80px"></td>
    <td><input type="text" class="m-om" value="${{om||''}}" placeholder="Arbeider" style="width:200px"></td>
    <td><button type="button" class="danger m-del">×</button></td>
  </tr>`;
}}
const mapDiv = document.getElementById("mappings-table");
async function loadMappings() {{
  const r = await fetch("/api/sektie-mappings"); const d = await r.json();
  const rows = (d.mappings || []).map((m,i) =>
    rowHtml(i, m.sektie_origineel, m.werknemerskengetal, m.omschrijving));
  mapDiv.innerHTML = `<table style="border-collapse:collapse;font-size:13px">
    <thead><tr style="text-align:left;font-size:11px;color:var(--muted);text-transform:uppercase">
      <th style="padding:4px 8px 4px 0">sektie</th><th>kengetal</th><th>omschrijving</th><th></th>
    </tr></thead><tbody>${{rows.join('') || rowHtml(0)}}</tbody></table>`;
  attachRowHandlers();
}}
function attachRowHandlers() {{
  mapDiv.querySelectorAll(".m-del").forEach(b => b.onclick = e =>
    e.target.closest("tr").remove());
}}
document.getElementById("add-row").addEventListener("click", () => {{
  const tbody = mapDiv.querySelector("tbody");
  tbody.insertAdjacentHTML("beforeend", rowHtml(tbody.children.length));
  attachRowHandlers();
}});
document.getElementById("save-mappings").addEventListener("click", async () => {{
  const mappings = [];
  mapDiv.querySelectorAll("tbody tr").forEach(tr => {{
    const sek = tr.querySelector(".m-sek").value.trim();
    const kg = tr.querySelector(".m-kg").value.trim();
    const om = tr.querySelector(".m-om").value.trim();
    if (sek && kg) mappings.push({{sektie_origineel: sek, werknemerskengetal: kg, omschrijving: om || null}});
  }});
  const r = await fetch("/api/sektie-mappings", {{
    method:"POST", headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{mappings}})
  }});
  const d = await r.json();
  const s = document.getElementById("map-status");
  if (r.ok) s.innerHTML = `<span class="ok">${{d.updated}} regels opgeslagen.</span>`;
  else s.innerHTML = `<span class="err">Fout: ${{d.error || r.status}}</span>`;
}});
loadMappings();
</script>
"""
