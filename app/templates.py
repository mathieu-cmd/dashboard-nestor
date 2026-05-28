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
  display:grid;grid-template-columns:180px 1fr;grid-template-rows:1fr;
  transition:grid-template-columns .15s ease;}
body.sidebar-collapsed{grid-template-columns:60px 1fr;}
body.sidebar-collapsed .sidebar{padding:16px 8px;}
body.sidebar-collapsed .brand{justify-content:center;font-size:0;padding:0 0 12px;}
body.sidebar-collapsed .brand .dot{width:14px;height:14px;}
body.sidebar-collapsed .nav-item{justify-content:center;padding:10px 6px;}
body.sidebar-collapsed .nav-item .label{display:none;}
body.sidebar-collapsed .footer{display:none;}

/* Mobile top-bar (alleen zichtbaar op smal scherm) */
.mobile-bar{display:none;background:var(--sidebar-bg);color:#fff;
  padding:12px 16px;align-items:center;gap:12px;
  position:sticky;top:0;z-index:30;}
.mobile-bar .ham{font-size:22px;background:none;border:none;color:#fff;
  cursor:pointer;padding:4px 8px;border-radius:6px}
.mobile-bar .ham:hover{background:#1e293b}
.mobile-bar .title{font-weight:700;font-size:15px}
.sidebar-backdrop{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);
  z-index:39}

/* Sidebar */
.sidebar{background:var(--sidebar-bg);color:var(--sidebar-fg);
  padding:24px 16px;display:flex;flex-direction:column;gap:8px;
  height:100vh;position:sticky;top:0;}
.brand{color:#fff;font-size:15px;font-weight:700;letter-spacing:.3px;
  padding:0 8px 12px;display:flex;align-items:center;gap:8px;
  border-bottom:1px solid #1e293b;margin-bottom:12px;cursor:pointer;
  user-select:none}
.brand:hover{opacity:.85}
.brand .toggle-hint{margin-left:auto;color:#475569;font-size:11px;font-weight:400}
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
main{padding:24px 28px;overflow-x:hidden;min-width:0;}

/* Mobile breakpoint */
@media (max-width: 760px) {
  body { grid-template-columns: 1fr; }
  .mobile-bar { display: flex; }
  .sidebar {
    position: fixed; top: 0; left: 0; bottom: 0;
    width: 260px; max-width: 80vw; z-index: 40;
    transform: translateX(-100%); transition: transform .2s;
    box-shadow: 2px 0 12px rgba(0,0,0,.3);
  }
  body.sidebar-open .sidebar { transform: translateX(0); }
  body.sidebar-open .sidebar-backdrop { display: block; }
  main { padding: 16px; }
  h1 { font-size: 18px; }
  .toolbar { gap: 8px; }
  .toolbar select { font-size: 12px; padding: 5px 8px; }
  .kpi-row { grid-template-columns: 1fr; gap: 10px; margin-bottom: 16px; }
  .kpi .val { font-size: 22px; }
  .charts-grid { grid-template-columns: 1fr; gap: 12px; }
  .chart-card { padding: 12px; }
  .chart-card .canvas-wrap { height: 220px; }
  .chart-card canvas { max-height: 220px !important; }
  #db-sync-bar, #ex-sync-bar { gap: 12px !important; padding: 12px !important; }
  #db-sync-bar button, #ex-sync-bar button { width: 100% !important; }
  .panel { padding: 12px; }
  .grid2 { grid-template-columns: 1fr; gap: 10px; }
  .status-row { gap: 12px; }
  .status-row > div { min-width: 100px; }
  .actions { gap: 8px; }
  .actions button { flex: 1; }
}
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

/* Charts grid — compactere gap zodat charts dichter bij elkaar staan */
.charts-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
@media (max-width:1100px){.charts-grid{grid-template-columns:1fr;gap:8px}}
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
.chart-card.clickable{cursor:zoom-in}
.chart-card.clickable:hover{box-shadow:var(--shadow-md);transform:translateY(-1px);transition:all .15s}

/* Period-override toolbar bovenaan dashboards */
.period-toolbar{background:var(--panel);border:1px solid var(--border);
  border-radius:var(--radius);padding:12px 16px;margin-bottom:16px;
  display:flex;align-items:center;gap:14px;flex-wrap:wrap;box-shadow:var(--shadow-sm)}
.period-toolbar label{font-size:12px;color:var(--muted);font-weight:600;
  text-transform:uppercase;letter-spacing:.5px;margin:0}
.period-toolbar select,.period-toolbar input{padding:6px 10px;border:1px solid var(--border);
  border-radius:8px;font:inherit;font-size:13px;background:#fff;min-width:160px}
.period-toolbar .group{display:flex;align-items:center;gap:8px}
.period-toolbar small{color:var(--muted);font-size:11px}

/* Modal voor vergrote chart */
.modal-overlay{position:fixed;inset:0;z-index:50;display:none;
  align-items:center;justify-content:center;padding:24px}
.modal-overlay.open{display:flex}
.modal-overlay .backdrop{position:absolute;inset:0;background:rgba(15,23,42,.7);
  backdrop-filter:blur(4px)}
.modal-content{position:relative;width:100%;max-width:1400px;height:95vh;max-height:1000px;
  background:#fff;border-radius:14px;padding:24px 28px;
  display:flex;flex-direction:column;box-shadow:0 25px 50px -12px rgba(0,0,0,.5);z-index:1}
.modal-content h3{margin:0 0 6px;font-size:22px;font-weight:800;
  padding-right:48px;letter-spacing:-.3px;color:var(--fg)}
.modal-content .modal-meta{color:var(--muted);font-size:13px;margin-bottom:18px}
.modal-canvas-wrap{flex:1;min-height:0;position:relative}
.modal-canvas-wrap canvas{max-height:none !important}
.modal-close{position:absolute;top:16px;right:16px;width:32px;height:32px;
  border:1px solid var(--border);background:#fff;border-radius:50%;cursor:pointer;
  font-size:18px;display:flex;align-items:center;justify-content:center;padding:0}
.modal-close:hover{background:var(--panel)}
@media (max-width:760px){
  .modal-overlay{padding:8px}
  .modal-content{padding:14px;height:90vh}
}

/* Forms */
.panel{background:var(--panel);border:1px solid var(--border);
  border-radius:var(--radius);box-shadow:var(--shadow-sm);
  padding:18px;margin-bottom:16px}
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:12px 16px}
@media (max-width:700px){.grid2{grid-template-columns:1fr}}
/* Compactere filter-grid (4 kolommen op desktop) */
.filter-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px 12px}
@media (max-width:1000px){.filter-grid{grid-template-columns:repeat(2,1fr)}}
@media (max-width:600px){.filter-grid{grid-template-columns:1fr}}
.filter-grid label{font-size:11.5px;margin-bottom:3px}
.filter-grid input[type=text]{font-size:12.5px;padding:6px 8px}
.filter-grid .ts-control{padding:3px 6px !important;min-height:30px !important;font-size:12.5px !important}
.filter-grid .ts-control .item{font-size:11.5px !important;padding:1px 6px !important}
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


def sync_bar_html(prefix: str = "db") -> str:
    """Gedeelde sync-bar component — bovenaan dashboards EN export.

    `prefix` zorgt voor unieke element-ID's wanneer de bar twee keer op
    dezelfde pagina zou voorkomen (niet nu, maar veilig)."""
    return f"""
<div class="panel" id="{prefix}-sync-bar"
     style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;justify-content:space-between">
  <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
    <div>
      <div style="color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Laatste sync</div>
      <div id="{prefix}-last-sync" style="font-size:14px;font-weight:600;margin-top:2px">…</div>
    </div>
    <div>
      <div style="color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Status</div>
      <div id="{prefix}-sync-status" style="font-size:14px;font-weight:600;margin-top:2px">…</div>
    </div>
    <div>
      <div style="color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Rijen totaal</div>
      <div id="{prefix}-rows" style="font-size:14px;font-weight:600;margin-top:2px">…</div>
    </div>
    <div>
      <div style="color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Auto-sync</div>
      <div style="font-size:14px;font-weight:600;margin-top:2px">dagelijks 11:59</div>
    </div>
  </div>
  <button class="primary" id="{prefix}-sync-btn"
          style="font-size:14px;padding:10px 20px;box-shadow:0 2px 8px rgba(79,70,229,.35)">
    ↻ Sync Prato nu
  </button>
</div>

<script>
(function() {{
  const prefix = "{prefix}";
  async function refresh() {{
    try {{
      const r = await fetch("/api/status");
      const d = await r.json();
      document.getElementById(prefix + "-rows").textContent =
        (d.rows_cached || 0).toLocaleString("nl-BE");
      const last = d.last_sync;
      if (last) {{
        document.getElementById(prefix + "-last-sync").textContent =
          new Date(last.started_at).toLocaleString("nl-BE");
        const st = document.getElementById(prefix + "-sync-status");
        st.textContent = last.status;
        st.style.color =
          last.status === "ok" ? "var(--ok)" :
          last.status === "failed" ? "var(--err)" : "var(--warn)";
      }} else {{
        document.getElementById(prefix + "-last-sync").textContent = "—";
        document.getElementById(prefix + "-sync-status").textContent = "—";
      }}
    }} catch (e) {{}}
  }}
  document.getElementById(prefix + "-sync-btn").addEventListener("click", async function() {{
    const btn = this; btn.disabled = true;
    const orig = btn.textContent; btn.textContent = "Sync gepland…";
    try {{
      const r = await fetch("/sync/run", {{method: "POST"}});
      const d = await r.json();
      if (!r.ok) alert("Sync fout: " + (d.error || r.status));
    }} catch (e) {{ alert("Sync fout: " + e); }}
    finally {{ setTimeout(() => {{
      btn.disabled = false; btn.textContent = orig; refresh();
    }}, 2000); }}
  }});
  refresh();
  setInterval(refresh, 10000);
}})();
</script>
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
            f'<a class="{cls}" href="{href}" title="{_html.escape(label)}">'
            f'<span class="ic">{_icon(key)}</span>'
            f'<span class="label">{_html.escape(label)}</span></a>'
        )

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>{_html.escape(title)} — Dashboard Nestor</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://cdn.jsdelivr.net">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/css/tom-select.css">
<script src="https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/js/tom-select.complete.min.js"></script>
<style>{_CSS}</style>
</head>
<body>
<div class="mobile-bar">
  <button class="ham" onclick="document.body.classList.toggle('sidebar-open')" aria-label="Menu">☰</button>
  <div class="title">Dashboard Nestor</div>
</div>
<aside class="sidebar">
  <div class="brand" onclick="toggleSidebar()" title="Klik om in/uit te klappen">
    <span class="dot"></span><span class="label">Dashboard Nestor</span>
    <span class="toggle-hint">«</span>
  </div>
  {navlink('/dashboards', 'dashboards', 'Dashboards')}
  {navlink('/explorer', 'explorer', 'Explorer')}
  {navlink('/export', 'export', 'Export')}
  {navlink('/admin', 'admin', 'Admin')}
  <div class="spacer"></div>
  <div class="footer" id="footer-status">…</div>
</aside>
<div class="sidebar-backdrop" onclick="document.body.classList.remove('sidebar-open')"></div>
<main>{body}</main>
<script>
// Sluit sidebar bij klik op nav-link (mobile)
document.querySelectorAll(".sidebar .nav-item").forEach(a => {{
  a.addEventListener("click", () => document.body.classList.remove("sidebar-open"));
}});
// Sidebar collapse-toggle (desktop) — onthoud keuze in localStorage
function toggleSidebar() {{
  // op mobile: open/sluit overlay
  if (window.innerWidth <= 760) {{
    document.body.classList.toggle("sidebar-open");
    return;
  }}
  const collapsed = document.body.classList.toggle("sidebar-collapsed");
  try {{ localStorage.setItem("dn_sidebar_collapsed", collapsed ? "1" : "0"); }} catch (e) {{}}
}}
// Restore staat bij page-load
try {{
  if (localStorage.getItem("dn_sidebar_collapsed") === "1") {{
    document.body.classList.add("sidebar-collapsed");
  }}
}} catch (e) {{}}
</script>
<script>
window.fmtEur = (v) => v == null ? "—" :
  new Intl.NumberFormat("nl-BE", {{ style:"currency", currency:"EUR", maximumFractionDigits: 0 }}).format(v);
window.fmtNum = (v, dec=2) => v == null ? "—" :
  new Intl.NumberFormat("nl-BE", {{ minimumFractionDigits: dec, maximumFractionDigits: dec }}).format(v);

// Compact format voor datalabels — vermijdt drukke labels bij grote waarden.
window.fmtCompactEur = (v) => {{
  if (v == null) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e6) return "€" + (v/1e6).toLocaleString("nl-BE",
      {{maximumFractionDigits:2, minimumFractionDigits:1}}) + "M";
  if (abs >= 1e3) return "€" + (v/1e3).toLocaleString("nl-BE",
      {{maximumFractionDigits:0}}) + "k";
  return "€" + v.toLocaleString("nl-BE", {{maximumFractionDigits:0}});
}};
window.fmtCompactNum = (v, suffix="") => {{
  if (v == null) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e6) return (v/1e6).toLocaleString("nl-BE",
      {{maximumFractionDigits:2}}) + "M" + suffix;
  if (abs >= 1e3) return (v/1e3).toLocaleString("nl-BE",
      {{maximumFractionDigits:1}}) + "k" + suffix;
  return v.toLocaleString("nl-BE", {{maximumFractionDigits:0}}) + suffix;
}};
window.unitFormatter = (unit) => {{
  if (unit === "EUR") return window.fmtEur;
  if (unit === "uur" || unit === "uur/pers") return (v) => window.fmtNum(v, 1) + " " + unit;
  if (unit === "%") return (v) => window.fmtNum(v, 2) + "%";
  return (v) => window.fmtNum(v, 0);
}};
// Compact-versie voor datalabels: kortere tekst per datapunt.
window.unitFormatterCompact = (unit) => {{
  if (unit === "EUR") return window.fmtCompactEur;
  if (unit === "uur" || unit === "uur/pers") return (v) => window.fmtCompactNum(v, " " + unit);
  if (unit === "%") return (v) => window.fmtNum(v, 1) + "%";
  return (v) => window.fmtCompactNum(v);
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
<div class="chart-card clickable" data-id="{p['id']}" onclick="openChartModal({p['id']})">
  <h3>{_html.escape(p['titel'])}</h3>
  <div class="meta">{_html.escape(meta)}</div>
  <button class="unpin" onclick="event.stopPropagation();unpin({p['id']})">Verwijder</button>
  <div class="canvas-wrap"><canvas id="{chart_id}"></canvas></div>
</div>"""

    pinned_json = json.dumps([{
        "id": p["id"], "titel": p["titel"],
        "segment_label": p.get("segment_label", p["segment"]),
        "metric": p["metric"], "segment": p["segment"],
        "chart_type": p["chart_type"], "grain": p["grain"],
        "period_mode": p["period_mode"],
        "period_value": p.get("period_value"),
        "extra_options": p.get("extra_options"),
        "series_json": p.get("series_json"),
    } for p in pinned])

    return f"""
<h1>Dashboards</h1>
<p class="subtitle">Vastgepinde grafieken — klik op een grafiek om 'm te vergroten.</p>

{sync_bar_html('db')}

<div class="period-toolbar">
  <div class="group">
    <label for="period-override">Periode</label>
    <select id="period-override">
      <option value="">Per grafiek behouden</option>
      <option value="since:2025-01">Sinds 2025-01</option>
      <option value="since:2024-01">Sinds 2024-01</option>
      <option value="since:2023-01">Sinds 2023-01</option>
      <option value="ltm">Laatste 12 maanden</option>
      <option value="ytd">Year-to-date</option>
      <option value="all">Volledige historiek</option>
      <option value="year:2026">2026</option>
      <option value="year:2025">2025</option>
      <option value="year:2024">2024</option>
      <option value="year:2023">2023</option>
    </select>
  </div>
  <small>LTM-rolling grafieken negeren deze filter (= rolling 12 mo is altijd 'huidig')</small>
</div>

<div class="charts-grid">
{cards_html}
</div>

<div class="modal-overlay" id="chart-modal">
  <div class="backdrop" onclick="closeChartModal()"></div>
  <div class="modal-content">
    <button class="modal-close" onclick="closeChartModal()">×</button>
    <h3 id="modal-title">…</h3>
    <div class="modal-meta" id="modal-meta">…</div>
    <div class="modal-canvas-wrap"><canvas id="modal-canvas"></canvas></div>
  </div>
</div>

<script>
const PINNED = {pinned_json};

// Cache voor de gerenderde Chart-instances per pin-id (voor unpin + modal).
const CHART_INSTANCES = {{}};
const CHART_LAST_DATA = {{}};  // gegevens nodig voor modal-render

const SERIES_COLORS = ["#4f46e5", "#10b981", "#f97316", "#ec4899", "#06b6d4", "#a855f7"];

function chartCardEl(id) {{ return document.getElementById("chart-" + id); }}
function showChartError(id, msg) {{
  const c = chartCardEl(id); if (!c) return;
  c.parentNode.innerHTML = '<div class="empty" style="color:var(--err);font-style:normal">'
    + (msg || "Fout bij laden") + '</div>';
}}
function showChartEmpty(id, msg) {{
  const c = chartCardEl(id); if (!c) return;
  c.parentNode.innerHTML = '<div class="empty">' + (msg || "Geen data.") + '</div>';
}}

// Period-override: lees keuze uit dropdown, applieer per pinned spec.
function effectivePeriod(p) {{
  const ov = (document.getElementById("period-override") || {{}}).value || "";
  if (!ov) return {{period_mode: p.period_mode, period_value: p.period_value}};
  if (ov === "ltm")  return {{period_mode: "ltm", period_value: null}};
  if (ov === "ytd")  return {{period_mode: "ytd", period_value: null}};
  if (ov === "all")  return {{period_mode: "all", period_value: null}};
  if (ov.startsWith("since:")) return {{period_mode: "since", period_value: ov.substring(6)}};
  if (ov.startsWith("year:"))  return {{period_mode: "year", period_value: ov.substring(5)}};
  return {{period_mode: p.period_mode, period_value: p.period_value}};
}}
function safeParse(s, fb) {{ try {{ return JSON.parse(s); }} catch (e) {{ return fb; }} }}

async function fetchSeries(spec, p, effPeriod) {{
  const params = new URLSearchParams({{
    metric: spec.metric, segment: spec.segment, grain: p.grain,
    period_mode: effPeriod.period_mode
  }});
  if (effPeriod.period_value) params.append("period_value", effPeriod.period_value);
  if (p.extra_options) {{
    const eo = safeParse(p.extra_options, {{}});
    if (eo.top_n) params.append("top_n", eo.top_n);
  }}
  const r = await fetch("/api/metric?" + params.toString());
  if (!r.ok) {{
    const err = await r.json().catch(() => ({{}}));
    throw new Error("API " + r.status + ": " + (err.error || ""));
  }}
  const d = await r.json();
  return {{
    labels: d.labels || [], values: d.values || [], unit: d.unit || "",
    label: spec.label || (spec.metric + " — " + (d.segment_label || spec.segment)),
    axis: spec.axis || "left",
  }};
}}

function combineSeries(seriesList, chart_type) {{
  const labelSet = new Set();
  for (const s of seriesList) for (const l of s.labels) labelSet.add(l);
  const labels = [...labelSet].sort();
  const datasets = seriesList.map((s, i) => {{
    const color = SERIES_COLORS[i % SERIES_COLORS.length];
    const m = new Map(s.labels.map((l, j) => [l, s.values[j]]));
    return {{
      label: s.label,
      data: labels.map(l => m.has(l) ? m.get(l) : null),
      yAxisID: s.axis === "right" ? "y2" : "y",
      _unit: s.unit,
      borderColor: color,
      backgroundColor: chart_type === "bar" ? color : (color + "1a"),
      fill: false, tension: 0, borderWidth: 2,
      pointRadius: 3, pointHoverRadius: 6, spanGaps: true,
    }};
  }});
  return {{ labels, datasets }};
}}

// Deterministische label-sampler: zorgt dat labels NOOIT overlappen.
// Strategie:
//  - eerste en laatste datapunt ALTIJD tonen
//  - tussenliggende labels: evenredig verdeeld, max N per dataset
//  - per dataset offset zodat twee series op DIFFERENT indexen tonen
//    -> labels van series A en B vallen nooit op dezelfde x-positie
function makeLabelDisplay(maxLabels) {{
  return (ctx) => {{
    const n = ctx.dataset.data.length;
    if (n <= 2) return true;
    // dataset-index in de chart (0 = eerste series, 1 = tweede, ...)
    const dsIdx = ctx.datasetIndex || 0;
    // Hoeveel labels deze series mag tonen (incl. eerste/laatste)
    const want = Math.min(n, Math.max(2, maxLabels));
    if (want >= n) return true;
    // Eerste & laatste ALTIJD
    if (ctx.dataIndex === 0 || ctx.dataIndex === n - 1) return true;
    // Step zo gekozen dat we ~want labels tonen
    const step = (n - 1) / (want - 1);
    // Offset per dataset: tweede series schuift een halve step op,
    // zodat labels van series A en series B NIET op dezelfde x staan.
    const offset = (dsIdx * step) / 2;
    // Zit dit datapunt op een sample-positie?
    for (let k = 1; k < want - 1; k++) {{
      const target = Math.round(k * step + offset);
      if (target === ctx.dataIndex) return true;
    }}
    return false;
  }};
}}

function buildChartConfig(p, combined, seriesList, showDataLabels, isModal) {{
  const hasRightAxis = seriesList.some(s => s.axis === "right");
  const leftUnit  = (seriesList.find(s => s.axis !== "right") || seriesList[0]).unit;
  const rightUnit = (seriesList.find(s => s.axis === "right") || seriesList[0]).unit;
  const fmtLeft  = window.unitFormatter(leftUnit);
  const fmtRight = window.unitFormatter(rightUnit);
  const fmtFor   = (ds) => ds.yAxisID === "y2" ? fmtRight : fmtLeft;

  const scales = {{
    y:  {{ type: "linear", position: "left",
           ticks: {{ callback: (v) => fmtLeft(v) }},
           grid: {{ color: "rgba(0,0,0,0.05)" }} }},
    x:  {{ grid: {{ display: false }} }}
  }};
  if (hasRightAxis) {{
    scales.y2 = {{ type: "linear", position: "right",
                   ticks: {{ callback: (v) => fmtRight(v) }},
                   grid: {{ drawOnChartArea: false }} }};

    // Dynamische schaling zodat de twee curves NIET over elkaar liggen.
    // Omzet en marge volgen typisch dezelfde trend; default-padding zou
    // ze in dezelfde band tonen. We dwingen de marge-as visueel naar
    // onderaan door extra ruimte boven de marge-max te reserveren.
    const leftVals = combined.datasets
      .filter(ds => ds.yAxisID !== "y2")
      .flatMap(ds => ds.data)
      .filter(v => v != null && !isNaN(v));
    const rightVals = combined.datasets
      .filter(ds => ds.yAxisID === "y2")
      .flatMap(ds => ds.data)
      .filter(v => v != null && !isNaN(v));
    if (leftVals.length && rightVals.length) {{
      const lMin = Math.min(...leftVals), lMax = Math.max(...leftVals);
      const rMin = Math.min(...rightVals), rMax = Math.max(...rightVals);
      const lRange = (lMax - lMin) || Math.abs(lMax) || 1;
      const rRange = (rMax - rMin) || Math.abs(rMax) || 1;
      // Linker as (= omzet): klein paddinkje boven, lichte zoom-in onder
      // (lift de omzet-curve visueel naar het bovenste deel van canvas).
      scales.y.suggestedMin = Math.max(0, lMin - lRange * 0.2);
      scales.y.suggestedMax = lMax + lRange * 0.10;
      // Rechter as (= marge): GROTE padding boven (factor 2x), zodat de
      // werkelijke datalijn fysiek in de onderste helft van canvas zit.
      scales.y2.suggestedMin = Math.max(0, rMin - rRange * 0.30);
      scales.y2.suggestedMax = rMax + rRange * 2.00;
    }}
  }}

  return {{
    type: p.chart_type,
    data: combined,
    options: {{
      responsive: true, maintainAspectRatio: false,
      interaction: {{ mode: "index", intersect: false }},
      // Extra padding zodat datalabels op de meest-rechtse en bovenste
      // punten niet door de as-rand worden afgekapt.
      layout: {{ padding: {{ left: 4, right: 20, top: 24, bottom: 4 }} }},
      plugins: {{
        legend: {{ display: combined.datasets.length > 1, position: "top",
                   align: "center",
                   labels: {{ boxWidth: 14, padding: 14,
                              font: {{ size: 12, weight: "600" }} }} }},
        tooltip: {{
          callbacks: {{
            label: (ctx) => ctx.dataset.label + ": " + fmtFor(ctx.dataset)(ctx.parsed.y ?? ctx.parsed)
          }}
        }},
        datalabels: showDataLabels ? {{
          // Deterministische sampling i.p.v. 'auto' — voorkomt dat labels
          // elkaar overschrijven én dat ze willekeurig verdwijnen.
          display: makeLabelDisplay(isModal ? 14 : 7),
          // Smart positioning per dataset:
          //  - laatste punt -> label LINKS (anders valt het buiten canvas)
          //  - eerste punt  -> label RECHTS
          //  - omzet (links-as)   -> label BOVEN de lijn
          //  - marge (rechts-as)  -> label ONDER de lijn (visueel apart)
          align: (ctx) => {{
            const n = ctx.dataset.data.length;
            if (ctx.dataIndex === n - 1) return "start";
            if (ctx.dataIndex === 0) return "end";
            return ctx.dataset.yAxisID === "y2" ? "bottom" : "top";
          }},
          anchor: "center",
          offset: 10,
          clip: false,
          backgroundColor: (ctx) => ctx.dataset.borderColor,
          color: "#fff",
          padding: {{ left: 5, right: 5, top: 2, bottom: 2 }},
          borderRadius: 4,
          font: {{ size: 10, weight: "700" }},
          // Compact format (k/M) zodat datalabels niet te lang worden
          formatter: (v, ctx) => {{
            if (v == null) return "";
            const compact = window.unitFormatterCompact(ctx.dataset._unit || "");
            return compact(v);
          }},
        }} : false
      }},
      scales
    }},
    plugins: showDataLabels ? [ChartDataLabels] : []
  }};
}}

async function renderChart(p) {{
  const id = p.id;
  let specs;
  if (p.series_json) {{
    specs = safeParse(p.series_json, null);
    if (!Array.isArray(specs) || !specs.length) {{
      showChartError(id, "Ongeldige series_json"); return;
    }}
  }} else {{
    specs = [{{ metric: p.metric, segment: p.segment }}];
  }}

  try {{
    const effPeriod = effectivePeriod(p);
    const seriesList = await Promise.all(specs.map(s => fetchSeries(s, p, effPeriod)));
    const totalPoints = seriesList.reduce((a, s) => a + s.values.length, 0);
    if (totalPoints === 0) {{ showChartEmpty(id); return; }}

    const combined = combineSeries(seriesList, p.chart_type);
    // Datalabels ALTIJD tonen — sampling zorgt voor non-overlap.
    const cfg = buildChartConfig(p, combined, seriesList, true, false);

    if (CHART_INSTANCES[id]) {{
      try {{ CHART_INSTANCES[id].destroy(); }} catch (e) {{}}
    }}
    const canvas = chartCardEl(id);
    if (!canvas) return;
    canvas.parentNode.style.display = "";
    if (canvas.parentNode.tagName !== "DIV" || !canvas.parentNode.classList.contains("canvas-wrap")) {{
      // Bij eerdere error werd canvas-wrap vervangen door .empty. Herstellen.
      const card = document.querySelector('.chart-card[data-id="' + id + '"]');
      if (card) {{
        const oldEmpty = card.querySelector(".empty");
        if (oldEmpty) {{
          const wrap = document.createElement("div");
          wrap.className = "canvas-wrap";
          const c = document.createElement("canvas"); c.id = "chart-" + id;
          wrap.appendChild(c); oldEmpty.replaceWith(wrap);
        }}
      }}
    }}
    CHART_INSTANCES[id] = new Chart(chartCardEl(id), cfg);
    CHART_LAST_DATA[id] = {{ p, specs, seriesList, combined }};
  }} catch (e) {{
    console.error("chart " + id + " gefaald", e);
    showChartError(id, "Fout: " + (e.message || e));
  }}
}}

// Modal — vergrote versie van dezelfde chart
let MODAL_CHART = null;
function openChartModal(id) {{
  const data = CHART_LAST_DATA[id];
  if (!data) return;
  const pinned = PINNED.find(x => x.id === id);
  document.getElementById("modal-title").textContent =
    (pinned && pinned.titel) ? pinned.titel : ("Grafiek #" + id);
  const metaBits = [];
  if (pinned && pinned.segment_label) metaBits.push(pinned.segment_label);
  if (pinned && pinned.period_mode) {{
    let per = pinned.period_mode;
    if (pinned.period_value) per += ": " + pinned.period_value;
    metaBits.push(per);
  }}
  document.getElementById("modal-meta").textContent = metaBits.join(" · ");
  const cfg = buildChartConfig(data.p, data.combined, data.seriesList, true, true);
  // Modal-versie: grotere fonts + ruime padding zodat datalabels op
  // randpunten niet door de Y-as worden afgekapt.
  cfg.options.plugins.legend.labels.font = {{ size: 14, weight: "600" }};
  cfg.options.layout.padding = {{ left: 16, right: 60, top: 40, bottom: 12 }};
  if (cfg.options.plugins.datalabels) {{
    cfg.options.plugins.datalabels.font = {{ size: 13, weight: "700" }};
    cfg.options.plugins.datalabels.padding = {{ left: 8, right: 8, top: 4, bottom: 4 }};
    cfg.options.plugins.datalabels.offset = 14;
    // Display blijft sampler (makeLabelDisplay met max=14) — voorkomt
    // overlap. Formatter wordt volledig (geen 'k'-suffix) want er is
    // ruimte genoeg in de modal.
    cfg.options.plugins.datalabels.formatter = (v, ctx) => {{
      if (v == null) return "";
      const fmt = window.unitFormatter(ctx.dataset._unit || "");
      return fmt(v);
    }};
  }}
  document.getElementById("chart-modal").classList.add("open");
  if (MODAL_CHART) {{ try {{ MODAL_CHART.destroy(); }} catch (e) {{}} }}
  MODAL_CHART = new Chart(document.getElementById("modal-canvas"), cfg);
}}
function closeChartModal() {{
  document.getElementById("chart-modal").classList.remove("open");
  if (MODAL_CHART) {{ try {{ MODAL_CHART.destroy(); }} catch (e) {{}} MODAL_CHART = null; }}
}}
document.addEventListener("keydown", (e) => {{
  if (e.key === "Escape") closeChartModal();
}});

// Period-override: bij wijziging herrender alle pinned charts
document.getElementById("period-override").addEventListener("change", () => {{
  PINNED.forEach(renderChart);
}});

async function unpin(id) {{
  if (!confirm("Deze grafiek verwijderen?")) return;
  const r = await fetch("/api/pinned/" + id, {{method:"DELETE"}});
  if (r.ok) location.reload();
}}

if (typeof Chart === "undefined") {{
  console.error("Chart.js is niet geladen");
  document.querySelectorAll(".chart-card").forEach(card => {{
    const empty = card.querySelector(".canvas-wrap");
    if (empty) empty.innerHTML = '<div class="empty" style="color:var(--err)">Chart.js niet geladen</div>';
  }});
}} else {{
  PINNED.forEach(renderChart);
}}
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
    return ("""
<h1>Margelijst — Export</h1>
<p class="subtitle">Filter de cache en download de exacte CSV. Sync staat op Dashboards.</p>

<form id="export-form" method="get" action="/prato/export.csv">
  <h2>Filters</h2>
  <div class="panel">
    <div class="filter-grid">
      <div><label>jaar</label>
        <select multiple id="f-jaar" name="jaar"></select></div>
      <div><label>kwartaal</label>
        <select multiple id="f-kwartaal" name="kwartaal"></select></div>
      <div><label>maand</label>
        <select multiple id="f-maand" name="maand"></select></div>
      <div><label>week</label>
        <select multiple id="f-week" name="week"></select></div>
      <div><label>vestiging</label>
        <select multiple id="f-vest" name="vestigingseenheidreferentieid"></select></div>
      <div><label>klant</label>
        <select multiple id="f-klant" name="klantreferentieid"></select></div>
      <div><label>persoon</label>
        <select multiple id="f-persoon-naam"></select></div>
      <div><label>klantnaam <span class="hint">vrij (LIKE)</span></label>
        <input type="text" name="klantnaam" placeholder="bv. Smartmat"></div>
    </div>
    <div class="actions">
      <button type="submit" class="primary">Download CSV</button>
      <button type="reset" id="btn-reset">Wissen</button>
    </div>
  </div>
</form>

<small>22 kolommen — UTF-8 zonder BOM, semicolon, Belgische decimaalkomma.</small>

<script>
// Wikkel alle Tom-Select init in DOMContentLoaded zodat we niet runnen
// vóór de <select>-elementen + Tom-Select bibliotheek beschikbaar zijn.
(function setupExportFilters() {
  function init() {
    if (typeof TomSelect === "undefined") {
      console.error("TomSelect niet geladen — filters blijven gewone HTML selects");
      return;
    }

    function initStatic(id, options) {
      return new TomSelect("#" + id, {
        plugins: ["remove_button"],
        options: options.map(o => ({value: String(o), text: String(o)})),
        maxItems: null, hideSelected: true,
        placeholder: "Alles", dropdownParent: "body",
      });
    }
    const tsJaar = initStatic("f-jaar", []);
    const tsKw   = initStatic("f-kwartaal", [1,2,3,4]);
    const tsMnd  = initStatic("f-maand", [1,2,3,4,5,6,7,8,9,10,11,12]);
    const tsWk   = initStatic("f-week", Array.from({length:53}, (_,i)=>i+1));

    function initAutocomplete(id, field, labelField=null) {
      return new TomSelect("#" + id, {
        plugins: ["remove_button"],
        valueField: "value", labelField: labelField || "value",
        searchField: labelField ? ["value", labelField] : ["value"],
        maxItems: null, hideSelected: true,
        placeholder: "Type 2 letters…", dropdownParent: "body",
        load: async function(query, callback) {
          if (!query || query.length < 2) { callback(); return; }
          try {
            const r = await fetch("/api/filter-values?field=" + encodeURIComponent(field)
                                  + "&q=" + encodeURIComponent(query));
            const d = await r.json();
            callback(d.values || []);
          } catch (e) { callback(); }
        },
        create: false,
      });
    }
    // Vestiging: gewone multi-select met alle 4 waarden in de dropdown
    // (geen autocomplete-typen nodig — er zijn maar enkele vestigingen).
    const tsVest = initStatic("f-vest", []);
    const tsKlant = initAutocomplete("f-klant", "klant", "label");
    const tsPersoon = initAutocomplete("f-persoon-naam", "persoon", "label");

    // Pre-vul jaar en vestiging dynamisch (geen query nodig — distinct lijst)
    fetch("/api/filter-values?field=jaar&q=")
      .then(r => r.json())
      .then(d => {
        (d.values || []).forEach(v =>
          tsJaar.addOption({value: String(v.value), text: String(v.value)}));
      })
      .catch(e => console.warn("jaar-options laden mislukt", e));

    fetch("/api/filter-values?field=vestigingseenheidreferentieid&q=")
      .then(r => r.json())
      .then(d => {
        (d.values || []).forEach(v =>
          tsVest.addOption({value: String(v.value), text: String(v.value)}));
      })
      .catch(e => console.warn("vestiging-options laden mislukt", e));

    // Submit-handler: bouw multi-value URL en navigeer
    document.getElementById("export-form").addEventListener("submit", function(e) {
      e.preventDefault();
      const params = new URLSearchParams();
      const f = e.target;
      [tsJaar, tsKw, tsMnd, tsWk, tsVest, tsKlant].forEach(ts => {
        const name = ts.input.name;
        ts.getValue().forEach(v => params.append(name, v));
      });
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
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
</script>
""")


# ---------------------------------------------------------------------------
# Admin — historisch import, sektie mapping
# ---------------------------------------------------------------------------


def admin_body(historisch_summary: dict[str, Any]) -> str:
    from .mappings import SEKTIE_KENGETAL, SEKTIE_OMSCHRIJVING, KENGETAL_OMSCHRIJVING

    # Tabel met top sekties uit de historische data + mapping (uit Python)
    sektie_counts = {
        s["code"]: s["count"]
        for s in (historisch_summary.get("sekties_top20") or [])
    }
    all_sektie_codes = sorted(set(list(sektie_counts.keys()) + list(SEKTIE_KENGETAL.keys())))

    def _row_for_sektie(code: str) -> str:
        count = sektie_counts.get(code, 0)
        kg = SEKTIE_KENGETAL.get(code, "")
        kg_label = KENGETAL_OMSCHRIJVING.get(kg, "") if kg else ""
        sek_label = SEKTIE_OMSCHRIJVING.get(code, "")
        unmapped_cls = "" if kg else ' style="color:var(--warn)"'
        kg_cell = f'<code>{_html.escape(kg)}</code> {_html.escape(kg_label)}' if kg else '<small style="color:var(--warn)">geen mapping</small>'
        return (
            f"<tr{unmapped_cls}>"
            f'<td style="padding:6px 12px 6px 0"><code>{_html.escape(code)}</code></td>'
            f'<td style="padding:6px 12px 6px 0">{_html.escape(sek_label)}</td>'
            f'<td style="padding:6px 12px 6px 0">{kg_cell}</td>'
            f'<td style="padding:6px 0;text-align:right">{count:,}</td>'
            f"</tr>"
        ).replace(",", ".")
    sektie_rows = "\n".join(_row_for_sektie(c) for c in all_sektie_codes)

    # Kengetal-tabel
    kg_rows = "\n".join(
        f"<tr><td style='padding:4px 12px 4px 0'><code>{_html.escape(c)}</code></td>"
        f"<td style='padding:4px 0'>{_html.escape(l)}</td></tr>"
        for c, l in KENGETAL_OMSCHRIJVING.items()
    )

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

<h2>Uren per week — extern aangeleverd</h2>
<div class="panel">
  <p style="margin:0 0 10px;color:var(--muted);font-size:13px">
    Eenmalige CSV-import voor de Nestor Core + Smartmat uren per week
    (historie tot maart 2026 — voor de live periode vanaf april 2026 gebruiken
    we Prato-data).
    Format: <code>jaar;week;segment;uren</code> · UTF-8 · semicolon · Belgische komma.
    Segment-waarden: <code>nestor_core</code> of <code>smartmat</code>.
  </p>
  <form id="uren-import-form" enctype="multipart/form-data">
    <input type="file" id="uren-file" name="file" accept=".csv,text/csv" required>
    <div class="actions">
      <button type="submit" class="primary" id="uren-import-btn">Importeren (overschrijft)</button>
      <small id="uren-import-status" style="align-self:center"></small>
    </div>
  </form>
</div>

<h2>Verwarrende klanten — koppelen of negeren</h2>
<div class="panel">
  <p style="margin:0 0 10px;color:var(--muted);font-size:13px">
    Klanten die <em>bijna</em> dezelfde naam hebben tussen HIAnt en Earnie
    maar niet exact. Bevestig om te koppelen (= worden 1 klant), of
    negeer om ze apart te houden.
  </p>
  <div id="dups-table"><small>laden…</small></div>
</div>

<h2>Dashboards</h2>
<div class="panel">
  <p style="margin:0 0 10px;color:var(--muted);font-size:13px">
    Reset alle vastgepinde grafieken en herstel de defaults uit
    <code>cache._DEFAULT_PINNED</code> en <code>cache._DEFAULT_PINNED_MULTI</code>.
  </p>
  <div class="actions">
    <button type="button" class="danger" id="reset-pins-btn">Reset pinned charts</button>
    <small id="reset-pins-status" style="align-self:center"></small>
  </div>
</div>
<script>
// Uren-import
document.getElementById("uren-import-form").addEventListener("submit", async (e) => {{
  e.preventDefault();
  const file = document.getElementById("uren-file").files[0];
  if (!file) return;
  const btn = document.getElementById("uren-import-btn");
  const stat = document.getElementById("uren-import-status");
  btn.disabled = true; stat.textContent = "Bezig…";
  const fd = new FormData(); fd.append("file", file);
  try {{
    const r = await fetch("/admin/import-uren-extern", {{method:"POST", body:fd}});
    const d = await r.json();
    if (r.ok && d.status === "ok") {{
      stat.innerHTML = `<span class="ok">${{d.rows_loaded}} rijen geladen.</span>`;
    }} else {{
      stat.innerHTML = `<span class="err">Fout: ${{d.error || r.status}}</span>`;
    }}
  }} catch (err) {{
    stat.innerHTML = `<span class="err">${{err}}</span>`;
  }} finally {{ btn.disabled = false; }}
}});

// Verwarrende klanten
async function loadDuplicates() {{
  const wrap = document.getElementById("dups-table");
  wrap.innerHTML = "<small>laden…</small>";
  try {{
    const r = await fetch("/api/klant-duplicates");
    const d = await r.json();
    const dups = d.duplicates || [];
    if (!dups.length) {{
      wrap.innerHTML = '<small style="color:var(--ok)">Geen verwarrende klanten gevonden.</small>';
      return;
    }}
    const rows = dups.map(c => `
      <tr data-h="${{c.hiant_klantref}}" data-e="${{c.earnie_klantref}}">
        <td style="padding:6px 12px 6px 0"><code>${{c.hiant_klantref}}</code></td>
        <td style="padding:6px 12px 6px 0">${{c.hiant_klantnaam}}</td>
        <td style="padding:6px 12px 6px 0;color:var(--muted)">→</td>
        <td style="padding:6px 12px 6px 0"><code>${{c.earnie_klantref}}</code></td>
        <td style="padding:6px 12px 6px 0">${{c.earnie_klantnaam}}</td>
        <td style="padding:6px 12px 6px 0;text-align:right;color:var(--muted)">${{(c.score*100).toFixed(0)}}%</td>
        <td style="padding:6px 0;text-align:right">
          <button class="primary" onclick="confirmDup(this)">Koppel</button>
          <button class="danger" onclick="rejectDup(this)">Negeer</button>
        </td>
      </tr>`).join("");
    wrap.innerHTML = `<table style="border-collapse:collapse;font-size:13px;width:100%">
      <thead><tr style="text-align:left;color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase">
        <th>HIAnt id</th><th>HIAnt naam</th><th></th><th>Earnie id</th><th>Earnie naam</th>
        <th style="text-align:right">Match</th><th></th>
      </tr></thead><tbody>${{rows}}</tbody></table>`;
  }} catch (e) {{
    wrap.innerHTML = `<small class="err">Fout: ${{e}}</small>`;
  }}
}}
async function confirmDup(btn) {{
  const tr = btn.closest("tr");
  const h = tr.dataset.h, eRef = tr.dataset.e;
  await fetch("/api/klant-mapping/confirm", {{
    method:"POST", headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{hiant_klantref: h, earnie_klantref: eRef}})
  }});
  tr.style.opacity = "0.4";
  setTimeout(loadDuplicates, 300);
}}
async function rejectDup(btn) {{
  const tr = btn.closest("tr");
  const h = tr.dataset.h, eRef = tr.dataset.e;
  await fetch("/api/klant-mapping/reject", {{
    method:"POST", headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{hiant_klantref: h, earnie_klantref: eRef}})
  }});
  tr.style.opacity = "0.4";
  setTimeout(loadDuplicates, 300);
}}
loadDuplicates();

document.getElementById("reset-pins-btn").addEventListener("click", async () => {{
  if (!confirm("Alle vastgepinde grafieken worden verwijderd en de defaults opnieuw geplaatst. Doorgaan?")) return;
  const s = document.getElementById("reset-pins-status");
  s.textContent = "Bezig…";
  try {{
    const r = await fetch("/admin/reset-pins", {{method:"POST"}});
    const d = await r.json();
    if (r.ok) s.innerHTML = `<span class="ok">${{d.new_count}} defaults geseed.</span>`;
    else s.innerHTML = `<span class="err">Fout: ${{d.error||r.status}}</span>`;
  }} catch (e) {{ s.innerHTML = `<span class="err">${{e}}</span>`; }}
}});
</script>

<h2>Sektie → werknemerskengetal mapping</h2>
<div class="panel">
  <p style="margin:0 0 12px;color:var(--muted);font-size:13px">
    Mappings staan <strong>hardgecodeerd in <code>app/mappings.py</code></strong>.
    Wijzig daar en commit + push om de mapping aan te passen. Hieronder de
    actuele combinatie van wat in de historische CSV voorkomt en wat
    momenteel gemapt is.
  </p>

  <table style="border-collapse:collapse;width:100%;font-size:13px;margin-top:10px">
    <thead><tr style="text-align:left;color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase">
      <th style="padding:6px 12px 6px 0">Sektie</th>
      <th style="padding:6px 12px 6px 0">Sektie-naam</th>
      <th style="padding:6px 12px 6px 0">→ Kengetal</th>
      <th style="text-align:right;padding:6px 0">Rijen in historiek</th>
    </tr></thead>
    <tbody>{sektie_rows}</tbody>
  </table>
</div>

<h2>RSZ-werknemerskengetal — namen</h2>
<div class="panel">
  <p style="margin:0 0 12px;color:var(--muted);font-size:13px">
    Leesbare namen voor de codes uit de Prato-live-data, geconfigureerd in
    <code>app/mappings.py</code> → <code>KENGETAL_OMSCHRIJVING</code>.
  </p>
  <table style="border-collapse:collapse;font-size:13px">
    <thead><tr style="text-align:left;color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase">
      <th style="padding:6px 12px 6px 0">Code</th><th>Naam</th>
    </tr></thead>
    <tbody>{kg_rows}</tbody>
  </table>
</div>

<script>
document.getElementById("import-form").addEventListener("submit", async (e) => {{
  e.preventDefault();
  const file = document.getElementById("csv-file").files[0];
  if (!file) return;
  if (!confirm("Bestaande historische data wordt overschreven. Doorgaan?")) return;
  const btn = document.getElementById("import-btn");
  const stat = document.getElementById("import-status");
  btn.disabled = true; stat.textContent = "Bezig met importeren…";
  const fd = new FormData(); fd.append("file", file);
  try {{
    const r = await fetch("/admin/import-historisch", {{method:"POST", body:fd}});
    const d = await r.json();
    if (r.ok && d.status === "ok") {{
      stat.innerHTML = `<span class="ok">${{d.rows_loaded}} rijen geladen in ${{d.duration_ms}} ms.</span>`;
      setTimeout(() => location.reload(), 1500);
    }} else {{
      stat.innerHTML = `<span class="err">Fout: ${{d.error || d.status || r.status}}</span>`;
    }}
  }} catch (err) {{
    stat.innerHTML = `<span class="err">${{err}}</span>`;
  }} finally {{
    btn.disabled = false;
  }}
}});
</script>
"""
