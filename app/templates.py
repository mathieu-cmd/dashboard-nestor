"""HTML-templates voor dashboard-nestor.

Inline strings i.p.v. Jinja2 — voor 3 pagina's volstaat dit. Per pagina
één render-functie die het body-fragment in een shared shell wikkelt.
"""

from __future__ import annotations

import html as _html
import json
from typing import Any


# ---------------------------------------------------------------------------
# Shared shell
# ---------------------------------------------------------------------------


_CSS = """
:root {
  --fg:#1f2328; --muted:#656d76; --bg:#fff; --panel:#f6f8fa;
  --border:#d0d7de; --accent:#0969da; --ok:#1a7f37; --err:#cf222e;
  --chart-bg:#fff;
}
* { box-sizing: border-box; }
body { font-family: -apple-system,"Segoe UI",system-ui,sans-serif;
       margin:0; color:var(--fg); background:var(--bg); font-size:14px; }
.nav { background:#fff; border-bottom:1px solid var(--border);
       padding:10px 20px; display:flex; gap:20px; align-items:center;
       position:sticky; top:0; z-index:10; }
.nav .brand { font-weight:700; font-size:16px; }
.nav a { color:var(--fg); text-decoration:none; padding:6px 10px;
         border-radius:6px; font-weight:500; }
.nav a:hover { background:var(--panel); }
.nav a.active { background:var(--panel); color:var(--accent); }
.nav .right { margin-left:auto; color:var(--muted); font-size:12px; }
.container { max-width:1280px; margin:0 auto; padding:20px; }
h1 { font-size:20px; margin:0 0 16px; }
h2 { font-size:14px; margin:24px 0 8px; color:var(--muted);
     text-transform:uppercase; letter-spacing:.5px; }
.panel { background:var(--panel); border:1px solid var(--border);
         border-radius:6px; padding:14px 16px; margin-bottom:16px; }
.grid { display:grid; grid-template-columns:repeat(2, 1fr); gap:10px 16px; }
@media (max-width:700px) { .grid { grid-template-columns:1fr; } }
label { display:block; font-weight:600; margin-bottom:4px; font-size:13px; }
.hint { color:var(--muted); font-weight:normal; font-size:12px; margin-left:6px; }
input[type=text], input[type=number], select {
  width:100%; padding:6px 8px; border:1px solid var(--border);
  border-radius:6px; font-size:13px; font-family:inherit; background:#fff;
}
input:focus, select:focus { outline:2px solid var(--accent); outline-offset:-1px; }
.actions { display:flex; gap:10px; margin:18px 0 8px; flex-wrap:wrap; }
button { padding:8px 16px; border:1px solid var(--border); background:#fff;
         border-radius:6px; font-size:14px; font-weight:600; cursor:pointer; }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
button.primary:hover { background:#0860ca; }
button.danger { color:var(--err); border-color:var(--err); background:#fff; }
button.danger:hover { background:#fff5f5; }
button:hover { background:#f3f4f6; }
button.primary:hover { background:#0860ca; }
button:disabled { opacity:.6; cursor:not-allowed; }
.status-row { display:flex; gap:24px; flex-wrap:wrap; }
.status-row > div { min-width:120px; }
.status-row .lbl { color:var(--muted); font-size:12px; }
.status-row .val { font-size:15px; font-weight:600; margin-top:2px; }
.ok { color:var(--ok); }
.err { color:var(--err); }
small { color:var(--muted); }
code { background:#eaeef2; padding:1px 5px; border-radius:3px; font-size:12px; }

/* Charts */
.charts-grid { display:grid; grid-template-columns:repeat(2, 1fr); gap:16px; }
@media (max-width:1000px) { .charts-grid { grid-template-columns:1fr; } }
.chart-card { background:var(--chart-bg); border:1px solid var(--border);
              border-radius:6px; padding:14px; position:relative; }
.chart-card h3 { font-size:14px; margin:0 0 12px; padding-right:80px; }
.chart-card .meta { color:var(--muted); font-size:11px; margin-bottom:8px; }
.chart-card .canvas-wrap { position:relative; height:280px; }
.chart-card canvas { max-height:280px !important; }
.chart-card .unpin { position:absolute; top:10px; right:10px;
                    padding:4px 8px; font-size:12px; }
.chart-card .empty { color:var(--muted); text-align:center; padding:60px 0; font-style:italic; }
.chart-card .loading { color:var(--muted); text-align:center; padding:60px 0; }
"""


def shell(title: str, active: str, body: str, status_html: str = "") -> str:
    """Wrapper voor elke pagina: HTML5 + nav + container."""
    def link(href: str, label: str, key: str) -> str:
        cls = "active" if key == active else ""
        return f'<a class="{cls}" href="{href}">{label}</a>'

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>{_html.escape(title)} — Dashboard Nestor</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>{_CSS}</style>
</head>
<body>
<nav class="nav">
  <span class="brand">Nestor</span>
  {link('/dashboards', 'Dashboards', 'dashboards')}
  {link('/explorer', 'Explorer', 'explorer')}
  {link('/export', 'Export', 'export')}
  <span class="right" id="nav-status">{status_html}</span>
</nav>
<div class="container">
{body}
</div>
<script>
// Globale helpers
window.fmtEur = (v) => v == null ? "—" :
  new Intl.NumberFormat("nl-BE", {{ style: "currency", currency: "EUR", maximumFractionDigits: 0 }}).format(v);
window.fmtNum = (v, dec=2) => v == null ? "—" :
  new Intl.NumberFormat("nl-BE", {{ minimumFractionDigits: dec, maximumFractionDigits: dec }}).format(v);
window.unitFormatter = (unit) => {{
  if (unit === "EUR") return window.fmtEur;
  if (unit === "uur" || unit === "uur/pers") return (v) => window.fmtNum(v, 1) + " " + unit;
  return (v) => window.fmtNum(v, 0);
}};

// Periodieke status-refresh op nav
async function refreshNavStatus() {{
  try {{
    const r = await fetch("/api/status");
    const d = await r.json();
    const last = d.last_sync;
    const rows = (d.rows_cached || 0).toLocaleString("nl-BE");
    let info = rows + " rijen · ";
    if (last) {{
      const when = new Date(last.started_at);
      info += "laatst: " + when.toLocaleString("nl-BE", {{
        month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'
      }}) + " · " + last.status;
    }} else {{
      info += "nog geen sync";
    }}
    document.getElementById("nav-status").textContent = info;
  }} catch (e) {{}}
}}
refreshNavStatus();
setInterval(refreshNavStatus, 15000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------


def dashboards_body(pinned: list[dict[str, Any]]) -> str:
    """Rendert de /dashboards pagina met N pinned charts."""
    if not pinned:
        return """
<h1>Dashboards</h1>
<div class="panel">
  <p>Nog geen vastgepinde grafieken.</p>
  <p>Ga naar <a href="/explorer">Explorer</a> om grafieken te genereren en
  toe te voegen.</p>
</div>
"""

    cards = []
    for p in pinned:
        chart_id = f"chart-{p['id']}"
        meta_bits = [p.get("segment_label", p["segment"])]
        if p.get("period_mode"):
            meta_bits.append(p["period_mode"])
        meta = " · ".join(meta_bits)
        cards.append(f"""
<div class="chart-card" data-id="{p['id']}">
  <h3>{_html.escape(p['titel'])}</h3>
  <div class="meta">{_html.escape(meta)}</div>
  <button class="unpin" onclick="unpin({p['id']})">Verwijder</button>
  <div class="canvas-wrap"><canvas id="{chart_id}"></canvas></div>
</div>
""")

    pinned_json = json.dumps([{
        "id": p["id"],
        "metric": p["metric"],
        "segment": p["segment"],
        "chart_type": p["chart_type"],
        "grain": p["grain"],
        "period_mode": p["period_mode"],
        "period_value": p.get("period_value"),
        "extra_options": p.get("extra_options"),
    } for p in pinned])

    return f"""
<h1>Dashboards</h1>
<div class="charts-grid">
{"".join(cards)}
</div>

<script>
const PINNED = {pinned_json};

async function renderChart(p) {{
  const params = new URLSearchParams({{
    metric: p.metric, segment: p.segment, grain: p.grain,
    period_mode: p.period_mode,
  }});
  if (p.period_value) params.append("period_value", p.period_value);
  if (p.extra_options) {{
    try {{
      const eo = JSON.parse(p.extra_options);
      if (eo.top_n) params.append("top_n", eo.top_n);
    }} catch (e) {{}}
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
      data: {{
        labels: d.labels,
        datasets: [{{
          label: d.metric,
          data: d.values,
          borderColor: "#0969da",
          backgroundColor: p.chart_type === "bar" ? "#0969da" : "rgba(9,105,218,0.1)",
          fill: p.chart_type === "line",
          tension: 0.2,
          borderWidth: 2,
        }}],
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{ callbacks: {{ label: (ctx) => fmt(ctx.parsed.y ?? ctx.parsed) }} }},
        }},
        scales: {{
          y: {{ ticks: {{ callback: (v) => fmt(v) }} }},
        }},
      }},
    }});
  }} catch (e) {{
    console.error("chart load failed", p.id, e);
    const canvas = document.getElementById("chart-" + p.id);
    if (canvas) canvas.parentNode.innerHTML = '<div class="empty">Fout bij laden.</div>';
  }}
}}

async function unpin(id) {{
  if (!confirm("Deze grafiek verwijderen uit het dashboard?")) return;
  const r = await fetch("/api/pinned/" + id, {{ method: "DELETE" }});
  if (r.ok) location.reload();
}}

PINNED.forEach(renderChart);
</script>
"""


# ---------------------------------------------------------------------------
# Explorer
# ---------------------------------------------------------------------------


def explorer_body(segments: list[dict], metrics: dict[str, dict]) -> str:
    """Form voor ad-hoc grafiek + pin-knop."""
    seg_opts = "\n".join(
        f'<option value="{s["key"]}">{_html.escape(s["label"])}</option>' for s in segments
    )
    metric_opts = "\n".join(
        f'<option value="{k}" data-type="{v["type"]}" data-chart="{v["chart"]}" data-unit="{v["unit"]}" data-needs-top-n="{int(v.get("needs_top_n", False))}">{_html.escape(v["label"])}</option>'
        for k, v in metrics.items()
    )

    return f"""
<h1>Explorer</h1>
<div class="panel">
  <h2 style="margin-top:0">Maak een grafiek</h2>
  <div class="grid">
    <div>
      <label>Metric</label>
      <select id="m-metric">{metric_opts}</select>
    </div>
    <div>
      <label>Segment</label>
      <select id="m-segment">{seg_opts}</select>
    </div>
    <div>
      <label>Grain</label>
      <select id="m-grain">
        <option value="month">Maand</option>
        <option value="week">Week</option>
        <option value="year">Jaar</option>
      </select>
    </div>
    <div>
      <label>Periode</label>
      <select id="m-period">
        <option value="ltm" selected>Laatste 12 maanden</option>
        <option value="ytd">Year-to-date</option>
        <option value="year">Specifiek jaar</option>
        <option value="all">Volledige historiek</option>
      </select>
    </div>
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
    <button class="primary" id="btn-generate">Genereer grafiek</button>
    <button id="btn-pin" disabled>Vastpinnen op dashboard</button>
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
const btnGenerate = document.getElementById("btn-generate");
const btnPin = document.getElementById("btn-pin");
const segmentSel = document.getElementById("m-segment");
const resultDiv = document.getElementById("result");

let currentChart = null;
let lastSpec = null;

function updateMetricUI() {{
  const opt = metricSel.options[metricSel.selectedIndex];
  const type = opt.dataset.type;
  const needsTopN = opt.dataset.needsTopN === "1";
  topNWrap.style.display = needsTopN ? "" : "none";
  // LTM rolling negeert grain en periode
  if (type === "ltm_rolling") {{
    grainSel.disabled = true;
    periodSel.disabled = true;
  }} else {{
    grainSel.disabled = false;
    periodSel.disabled = false;
  }}
}}
function updatePeriodUI() {{
  periodYearWrap.style.display = periodSel.value === "year" ? "" : "none";
}}
metricSel.addEventListener("change", updateMetricUI);
periodSel.addEventListener("change", updatePeriodUI);
updateMetricUI(); updatePeriodUI();

btnGenerate.addEventListener("click", async () => {{
  const metric = metricSel.value;
  const segment = segmentSel.value;
  const grain = grainSel.value;
  const period_mode = periodSel.value;
  const period_value = periodSel.value === "year" ? periodYearInp.value : null;
  const top_n = topNInp.value || 10;
  const opt = metricSel.options[metricSel.selectedIndex];
  const chart_type = opt.dataset.chart;
  const unit = opt.dataset.unit;
  const needsTopN = opt.dataset.needsTopN === "1";

  const params = new URLSearchParams({{ metric, segment, grain, period_mode }});
  if (period_value) params.append("period_value", period_value);
  if (needsTopN) params.append("top_n", top_n);

  resultDiv.innerHTML = '<div class="panel"><div class="loading">Genereren…</div></div>';
  try {{
    const r = await fetch("/api/metric?" + params.toString());
    if (!r.ok) {{
      const err = await r.json().catch(() => ({{}}));
      resultDiv.innerHTML = '<div class="panel err">Fout: ' + (err.error || r.status) + '</div>';
      return;
    }}
    const d = await r.json();
    lastSpec = {{ metric, segment, grain, period_mode, period_value, chart_type, top_n: needsTopN ? top_n : null, unit, segment_label: d.segment_label, metric_label: opt.text }};

    resultDiv.innerHTML = `
      <div class="panel">
        <h2 style="margin-top:0">${{opt.text}} — ${{d.segment_label}}</h2>
        <div class="canvas-wrap" style="height:380px"><canvas id="explorer-chart"></canvas></div>
      </div>`;
    const canvas = document.getElementById("explorer-chart");
    const fmt = window.unitFormatter(unit);
    if (!d.labels || d.labels.length === 0) {{
      canvas.parentNode.innerHTML = '<div class="empty">Geen data voor deze selectie.</div>';
      btnPin.disabled = false;
      return;
    }}
    currentChart = new Chart(canvas, {{
      type: chart_type,
      data: {{ labels: d.labels, datasets: [{{
        label: opt.text,
        data: d.values,
        borderColor: "#0969da",
        backgroundColor: chart_type === "bar" ? "#0969da" : "rgba(9,105,218,0.1)",
        fill: chart_type === "line",
        tension: 0.2, borderWidth: 2,
      }}] }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{ callbacks: {{ label: (ctx) => fmt(ctx.parsed.y ?? ctx.parsed) }} }},
        }},
        scales: {{ y: {{ ticks: {{ callback: (v) => fmt(v) }} }} }},
      }},
    }});
    btnPin.disabled = false;
  }} catch (e) {{
    resultDiv.innerHTML = '<div class="panel err">Fout: ' + e + '</div>';
  }}
}});

btnPin.addEventListener("click", async () => {{
  if (!lastSpec) return;
  const default_titel = `${{lastSpec.metric_label}} — ${{lastSpec.segment_label}}`;
  const titel = prompt("Titel voor het dashboard:", default_titel);
  if (!titel) return;
  const payload = {{
    titel,
    metric: lastSpec.metric,
    segment: lastSpec.segment,
    chart_type: lastSpec.chart_type,
    grain: lastSpec.grain,
    period_mode: lastSpec.period_mode,
    period_value: lastSpec.period_value || null,
  }};
  if (lastSpec.top_n) {{
    payload.extra_options = JSON.stringify({{ top_n: parseInt(lastSpec.top_n, 10) }});
  }}
  const r = await fetch("/api/pinned", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify(payload),
  }});
  if (r.ok) {{
    alert("Vastgepind. Bekijk in Dashboards.");
  }} else {{
    const err = await r.json().catch(() => ({{}}));
    alert("Fout: " + (err.error || r.status));
  }}
}});
</script>
"""


# ---------------------------------------------------------------------------
# Export — preview + filter form + download
# ---------------------------------------------------------------------------


def export_body() -> str:
    return """
<h1>Margelijst — Export</h1>

<div class="panel" id="status-panel">
  <h2 style="margin-top:0">Cache-status</h2>
  <div class="status-row">
    <div><div class="lbl">Rijen in cache</div><div class="val" id="rows">…</div></div>
    <div><div class="lbl">Laatste sync</div><div class="val" id="last-sync">…</div></div>
    <div><div class="lbl">Status</div><div class="val" id="sync-status">…</div></div>
    <div><div class="lbl">Volgende auto-sync</div><div class="val">elke dag 11:59 (Europe/Brussels)</div></div>
  </div>
  <div class="actions">
    <button type="button" id="sync-btn">Sync nu</button>
    <small style="align-self:center">handmatig de cache overschrijven met Prato-data</small>
  </div>
</div>

<form id="export-form" method="get" action="/prato/export.csv">
  <h2>Filters</h2>
  <div class="panel">
    <div class="grid">
      <div><label>jaar <span class="hint">meerdere = komma's</span></label>
           <input type="text" name="jaar" placeholder="2026"></div>
      <div><label>kwartaal <span class="hint">1-4</span></label>
           <input type="text" name="kwartaal"></div>
      <div><label>maand <span class="hint">1-12</span></label>
           <input type="text" name="maand"></div>
      <div><label>week <span class="hint">1-53</span></label>
           <input type="text" name="week"></div>
      <div><label>vestigingseenheidreferentieid</label>
           <input type="text" name="vestigingseenheidreferentieid"></div>
      <div><label>klantreferentieid</label>
           <input type="text" name="klantreferentieid"></div>
      <div><label>klantnaam <span class="hint">deel-match</span></label>
           <input type="text" name="klantnaam" placeholder="bv. Smartmat"></div>
      <div><label>persoonreferentieid</label>
           <input type="text" name="persoonreferentieid"></div>
      <div><label>familienaam <span class="hint">deel-match</span></label>
           <input type="text" name="familienaam"></div>
      <div><label>voornaam <span class="hint">deel-match</span></label>
           <input type="text" name="voornaam"></div>
    </div>
    <div class="actions">
      <button type="submit" class="primary">Download CSV</button>
      <button type="reset">Filters wissen</button>
    </div>
  </div>
</form>

<small>22 kolommen — UTF-8 zonder BOM, semicolon, Belgische decimaalkomma.</small>

<script>
const MULTI_FIELDS = ["jaar","kwartaal","maand","week","vestigingseenheidreferentieid","klantreferentieid","persoonreferentieid"];

document.getElementById("export-form").addEventListener("submit", function(e) {
  e.preventDefault();
  const params = new URLSearchParams();
  for (const el of e.target.elements) {
    if (!el.name || !el.value) continue;
    if (MULTI_FIELDS.includes(el.name)) {
      el.value.split(",").map(s => s.trim()).filter(Boolean).forEach(v => params.append(el.name, v));
    } else {
      params.append(el.name, el.value.trim());
    }
  }
  window.location.href = "/prato/export.csv?" + params.toString();
});

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
  } catch (e) {}
}

document.getElementById("sync-btn").addEventListener("click", async function() {
  const btn = this; btn.disabled = true; btn.textContent = "Sync gepland…";
  try {
    const r = await fetch("/sync/run", { method: "POST" });
    const d = await r.json();
    if (!r.ok) alert("Sync fout: " + (d.error || r.status));
  } catch (e) { alert("Sync fout: " + e); }
  finally { setTimeout(() => { btn.disabled = false; btn.textContent = "Sync nu"; refreshStatus(); }, 2000); }
});

refreshStatus(); setInterval(refreshStatus, 10000);
</script>
"""
