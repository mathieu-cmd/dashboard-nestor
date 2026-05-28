"""KPI-berekeningen op de SQLite-cache.

Elke metric-functie geeft een Chart.js-vriendelijk dict terug:
    {
        "labels": ["2025-06", "2025-07", ...],
        "values": [12345.67, ...],
        "metric": "omzet",
        "segment": "nestor_core",
        "segment_label": "Nestor Core",
        "grain": "month",
        "period_mode": "ltm",
        "meta": [...]      # optioneel, extra info per datapunt
    }

Beschikbare metrics (zie METRIC_REGISTRY onderaan):
    - omzet, marge, loonkost, kost, uren, medewerkers, klanten
    - omzet_ltm, marge_ltm, uren_ltm   (rolling 12-mo)
    - top_klanten_omzet, top_klanten_marge, top_klanten_uren
    - uren_per_medewerker              (gem. uren / medewerker per klant)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from .cache import cache_conn
from .segments import segment_label, segment_where

log = logging.getLogger("dashboard-nestor.metrics")


# ---------------------------------------------------------------------------
# Period filter
# ---------------------------------------------------------------------------


def _period_filter(period_mode: str, period_value: Optional[str] = None) -> tuple[str, list]:
    """SQL filter voor (jaar, maand)-kolommen, op basis van mode.

    Modes:
      - 'all':  geen filter
      - 'ltm':  laatste 12 maanden ending bij huidige maand
      - 'ytd':  1 jan van huidig jaar t/m vandaag
      - 'year': specifiek jaar via period_value
    """
    today = date.today()

    if period_mode == "all":
        return "1=1", []

    if period_mode == "ltm":
        # 12 maanden ending current month. Bv. nu = 2026-05, dan vanaf 2025-06.
        start_y = today.year - 1
        start_m = today.month + 1
        if start_m > 12:
            start_m -= 12
            start_y += 1
        return "(jaar*100 + maand) >= ?", [start_y * 100 + start_m]

    if period_mode == "ytd":
        return "jaar = ?", [today.year]

    if period_mode == "year":
        if not period_value:
            raise ValueError("period_value vereist bij period_mode='year'")
        return "jaar = ?", [int(period_value)]

    if period_mode == "range":
        # period_value-formaat: "YYYY-MM..YYYY-MM" (inclusive aan beide kanten)
        if not period_value or ".." not in period_value:
            raise ValueError("period_value moet 'YYYY-MM..YYYY-MM' zijn bij period_mode='range'")
        start_str, end_str = period_value.split("..", 1)
        try:
            sy, sm = int(start_str[:4]), int(start_str[5:7])
            ey, em = int(end_str[:4]), int(end_str[5:7])
        except (ValueError, IndexError):
            raise ValueError("period_value moet 'YYYY-MM..YYYY-MM' zijn (bv. '2024-01..2025-06')")
        return "(jaar*100 + maand) BETWEEN ? AND ?", [sy * 100 + sm, ey * 100 + em]

    raise ValueError(f"Onbekende period_mode: {period_mode}")


def _combine(parts: list[tuple[str, list]]) -> tuple[str, list]:
    """AND-combineer meerdere (where, params)."""
    effective = []
    all_params: list = []
    for w, p in parts:
        if w and w != "1=1":
            effective.append(f"({w})")
            all_params.extend(p)
    if not effective:
        return "1=1", []
    return " AND ".join(effective), all_params


# ---------------------------------------------------------------------------
# Time-series metrics (sum / count per grain)
# ---------------------------------------------------------------------------


_SUM_METRIC_EXPR = {
    # COALESCE rondom omzet_te_factureren omdat NULL bij historische data
    # anders SUM uit NULL maakt (SQL: x + NULL = NULL).
    "omzet": "SUM(COALESCE(omzet_gefactureerd,0) + COALESCE(omzet_te_factureren,0))",
    "marge": "SUM(COALESCE(marge,0))",
    "loonkost": "SUM(COALESCE(loonkost,0))",
    "kost": "SUM(COALESCE(kost,0))",
    "uren": "SUM(COALESCE(verloonde_uren,0))",
    "medewerkers": "COUNT(DISTINCT persoonreferentieid)",
    "klanten": "COUNT(DISTINCT klantreferentieid)",
}


def time_series(
    metric: str,
    segment: str,
    grain: str = "month",
    period_mode: str = "ltm",
    period_value: Optional[str] = None,
) -> dict[str, Any]:
    """SUM/COUNT van metric over tijd, gegroepeerd per grain."""
    if metric not in _SUM_METRIC_EXPR:
        raise ValueError(f"Onbekende time-series metric: {metric}")

    expr = _SUM_METRIC_EXPR[metric]

    if grain == "month":
        group_expr = "jaar, maand"
        label_expr = "jaar || '-' || printf('%02d', maand)"
    elif grain == "week":
        group_expr = "jaar, week"
        label_expr = "jaar || '-W' || printf('%02d', week)"
    elif grain == "year":
        group_expr = "jaar"
        label_expr = "CAST(jaar AS TEXT)"
    else:
        raise ValueError(f"Onbekende grain: {grain}")

    seg_w, seg_p = segment_where(segment)
    per_w, per_p = _period_filter(period_mode, period_value)
    where, params = _combine([(seg_w, seg_p), (per_w, per_p)])

    sql = (
        f"SELECT {label_expr} AS lbl, {expr} AS val "
        f"FROM v_margelijst "
        f"WHERE {where} "
        f"GROUP BY {group_expr} "
        f"ORDER BY {group_expr}"
    )

    with cache_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    return {
        "labels": [r[0] for r in rows],
        "values": [_to_number(r[1]) for r in rows],
        "metric": metric,
        "segment": segment,
        "segment_label": segment_label(segment),
        "grain": grain,
        "period_mode": period_mode,
        "period_value": period_value,
    }


# ---------------------------------------------------------------------------
# LTM rolling — voor elke maand X = som metric over [X-11 ... X]
# ---------------------------------------------------------------------------


_LTM_VALUE_EXPR = {
    # COALESCE-veiliger voor de historische data (omzet_te_factureren = NULL)
    "omzet": "COALESCE(omzet_gefactureerd,0) + COALESCE(omzet_te_factureren,0)",
    "marge": "COALESCE(marge,0)",
    "loonkost": "COALESCE(loonkost,0)",
    "kost": "COALESCE(kost,0)",
    "uren": "COALESCE(verloonde_uren,0)",
}


def ltm_rolling(metric: str, segment: str) -> dict[str, Any]:
    """Voortschrijdend 12-maands totaal — geeft 'gladde' LTM-grafiek.

    Vereist SQLite >= 3.25 (window functions). Railway nixpacks heeft moderne sqlite.
    """
    if metric not in _LTM_VALUE_EXPR:
        raise ValueError(f"Geen LTM voor metric: {metric}")

    val_expr = _LTM_VALUE_EXPR[metric]
    seg_w, seg_p = segment_where(segment)

    sql = f"""
        WITH monthly AS (
            SELECT jaar, maand, SUM({val_expr}) AS m_sum
            FROM v_margelijst
            WHERE {seg_w}
            GROUP BY jaar, maand
        ),
        ordered AS (
            SELECT jaar, maand, m_sum,
                   SUM(m_sum) OVER (
                       ORDER BY jaar, maand
                       ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
                   ) AS ltm_sum,
                   COUNT(*) OVER (
                       ORDER BY jaar, maand
                       ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
                   ) AS n_months
            FROM monthly
        )
        SELECT jaar || '-' || printf('%02d', maand) AS lbl,
               ltm_sum AS val
        FROM ordered
        WHERE n_months = 12
        ORDER BY jaar, maand
    """

    with cache_conn() as conn:
        rows = conn.execute(sql, seg_p).fetchall()

    return {
        "labels": [r[0] for r in rows],
        "values": [_to_number(r[1]) for r in rows],
        "metric": f"{metric}_ltm",
        "segment": segment,
        "segment_label": segment_label(segment),
        "grain": "month",
        "period_mode": "ltm_rolling",
        "period_value": None,
    }


# ---------------------------------------------------------------------------
# Top-N klanten op metric
# ---------------------------------------------------------------------------


def top_klanten(
    metric: str,
    segment: str,
    period_mode: str = "ltm",
    period_value: Optional[str] = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """Top N klanten op metric voor segment + periode."""
    if metric not in _SUM_METRIC_EXPR:
        raise ValueError(f"Onbekende top_klanten-metric: {metric}")

    expr = _SUM_METRIC_EXPR[metric]
    seg_w, seg_p = segment_where(segment)
    per_w, per_p = _period_filter(period_mode, period_value)
    where, params = _combine([(seg_w, seg_p), (per_w, per_p)])

    sql = (
        f"SELECT COALESCE(klantnaam, '(zonder klant)') AS lbl, "
        f"       {expr} AS val "
        f"FROM v_margelijst "
        f"WHERE {where} "
        f"GROUP BY klantnaam "
        f"ORDER BY val DESC "
        f"LIMIT ?"
    )
    params_full = params + [int(top_n)]

    with cache_conn() as conn:
        rows = conn.execute(sql, params_full).fetchall()

    return {
        "labels": [r[0] for r in rows],
        "values": [_to_number(r[1]) for r in rows],
        "metric": f"top_klanten_{metric}",
        "segment": segment,
        "segment_label": segment_label(segment),
        "grain": "klant",
        "period_mode": period_mode,
        "period_value": period_value,
    }


# ---------------------------------------------------------------------------
# Gem. uren / medewerker per klant
# ---------------------------------------------------------------------------


def uren_per_medewerker(
    segment: str,
    period_mode: str = "ltm",
    period_value: Optional[str] = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """Per klant: SUM(verloonde_uren) / COUNT(DISTINCT persoonreferentieid).

    Top N op die ratio, gefilterd op segment + periode."""
    seg_w, seg_p = segment_where(segment)
    per_w, per_p = _period_filter(period_mode, period_value)
    where, params = _combine([(seg_w, seg_p), (per_w, per_p)])

    sql = (
        "SELECT COALESCE(klantnaam, '(zonder klant)') AS lbl, "
        "       CASE WHEN COUNT(DISTINCT persoonreferentieid) = 0 THEN 0 "
        "            ELSE SUM(verloonde_uren) * 1.0 / COUNT(DISTINCT persoonreferentieid) "
        "       END AS val, "
        "       COUNT(DISTINCT persoonreferentieid) AS n_pers, "
        "       SUM(verloonde_uren) AS tot_uren "
        "FROM v_margelijst "
        f"WHERE {where} "
        "GROUP BY klantnaam "
        "HAVING COUNT(DISTINCT persoonreferentieid) > 0 "
        "ORDER BY val DESC "
        "LIMIT ?"
    )
    params_full = params + [int(top_n)]

    with cache_conn() as conn:
        rows = conn.execute(sql, params_full).fetchall()

    return {
        "labels": [r[0] for r in rows],
        "values": [round(float(r[1] or 0), 2) for r in rows],
        "meta": [{"n_medewerkers": r[2], "tot_uren": _to_number(r[3])} for r in rows],
        "metric": "uren_per_medewerker",
        "segment": segment,
        "segment_label": segment_label(segment),
        "grain": "klant",
        "period_mode": period_mode,
        "period_value": period_value,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_number(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Registry — wat de explorer en /api/metric-router weet aanbieden
# ---------------------------------------------------------------------------


# Beschrijving van wat elke metric-key doet, voor de UI dropdown.
METRIC_REGISTRY: dict[str, dict[str, Any]] = {
    "omzet": {"label": "Omzet (gefactureerd + te factureren)", "type": "time_series", "chart": "line", "unit": "EUR"},
    "marge": {"label": "Bruto marge", "type": "time_series", "chart": "line", "unit": "EUR"},
    "loonkost": {"label": "Loonkost", "type": "time_series", "chart": "line", "unit": "EUR"},
    "kost": {"label": "Totale kost", "type": "time_series", "chart": "line", "unit": "EUR"},
    "uren": {"label": "Verloonde uren", "type": "time_series", "chart": "line", "unit": "uur"},
    "medewerkers": {"label": "Actieve medewerkers (uniek)", "type": "time_series", "chart": "line", "unit": "personen"},
    "klanten": {"label": "Actieve klanten (uniek)", "type": "time_series", "chart": "line", "unit": "klanten"},
    "omzet_ltm": {"label": "Omzet LTM (rolling 12 mo)", "type": "ltm_rolling", "chart": "line", "unit": "EUR"},
    "marge_ltm": {"label": "Bruto marge LTM (rolling 12 mo)", "type": "ltm_rolling", "chart": "line", "unit": "EUR"},
    "loonkost_ltm": {"label": "Loonkost LTM (rolling 12 mo)", "type": "ltm_rolling", "chart": "line", "unit": "EUR"},
    "kost_ltm": {"label": "Kost LTM (rolling 12 mo)", "type": "ltm_rolling", "chart": "line", "unit": "EUR"},
    "uren_ltm": {"label": "Verloonde uren LTM (rolling 12 mo)", "type": "ltm_rolling", "chart": "line", "unit": "uur"},
    "top_klanten_omzet": {"label": "Top N klanten op omzet", "type": "top_klanten", "chart": "bar", "unit": "EUR", "needs_top_n": True},
    "top_klanten_marge": {"label": "Top N klanten op bruto marge", "type": "top_klanten", "chart": "bar", "unit": "EUR", "needs_top_n": True},
    "top_klanten_uren": {"label": "Top N klanten op verloonde uren", "type": "top_klanten", "chart": "bar", "unit": "uur", "needs_top_n": True},
    "uren_per_medewerker": {"label": "Gem. uren / medewerker per klant", "type": "uren_per_medewerker", "chart": "bar", "unit": "uur/pers", "needs_top_n": True},
}


def compute(
    metric: str,
    segment: str,
    grain: str = "month",
    period_mode: str = "ltm",
    period_value: Optional[str] = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """Dispatch op metric — geeft Chart.js-vriendelijk dict terug."""
    info = METRIC_REGISTRY.get(metric)
    if not info:
        raise ValueError(f"Onbekende metric: {metric}")

    typ = info["type"]
    if typ == "time_series":
        return time_series(metric, segment, grain, period_mode, period_value)
    if typ == "ltm_rolling":
        base = metric[: -len("_ltm")]  # 'omzet_ltm' -> 'omzet'
        return ltm_rolling(base, segment)
    if typ == "top_klanten":
        base = metric[len("top_klanten_"):]
        return top_klanten(base, segment, period_mode, period_value, top_n)
    if typ == "uren_per_medewerker":
        return uren_per_medewerker(segment, period_mode, period_value, top_n)
    raise ValueError(f"Geen handler voor metric-type: {typ}")
