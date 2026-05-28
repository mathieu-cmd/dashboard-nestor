"""Prato margelijst-export — CSV met filters en twee omzet-kolommen.

Endpoint: GET /prato/export.csv

Grain: één rij per (jaar, kwartaal, maand, week, vestiging, klant,
       persoon). Lonen sluiten wekelijks af, dus week is de natuurlijke
       grain voor Nestor.

Kolommen (in exact deze volgorde):

  Dimensies:
    jaar, kwartaal, maand, week,
    vestigingseenheidreferentieid,
    klantreferentieid, klantnaam,
    persoonreferentieid, familienaam, voornaam,

  Measures:
    loonkost, werkuitkering, bvvrijstellingen,
    rszwerkgeversbijdragen, rszverminderingen, provisies,
    omzet_gefactureerd        (uit facturatie.gefactureerdebedragen)
    omzet_te_factureren       (uit facturatie.tefacturerenbedragen)
    kost,
    verloonde_uren,
    marge                     = omzet_gefactureerd + omzet_te_factureren − kost
    margeperuur               = marge / verloonde_uren

Filters via query-parameters; multi-value door herhaling.

CSV-format: UTF-8 zonder BOM, semicolon, Belgische decimaalkomma,
ISO-datums (er staat eigenlijk geen datumkolom meer in de output).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Iterator, Optional

from .config import settings
from .prato_reporter import PratoNotConfigured, _MARGELIJST_SQL, is_configured

log = logging.getLogger("invoice-bundler.prato-export")


# ---------------------------------------------------------------------------
# CSV header — EXACT in Mathieu's gevraagde volgorde
# ---------------------------------------------------------------------------

EXPORT_COLUMNS: tuple[str, ...] = (
    "jaar", "kwartaal", "maand", "week",
    "vestigingseenheidreferentieid",
    "klantreferentieid", "klantnaam",
    "persoonreferentieid", "familienaam", "voornaam",
    "loonkost", "werkuitkering", "bvvrijstellingen",
    "rszwerkgeversbijdragen", "rszverminderingen", "provisies",
    "omzet_gefactureerd", "omzet_te_factureren",
    "kost", "verloonde_uren",
    "marge", "margeperuur",
)


# Filters die we accepteren als query-parameters.
# - INT_FILTERS: exact match, multi-value mogelijk (ANY(%s))
# - ID_FILTERS:  exact match op text, multi-value mogelijk
# - LIKE_FILTERS: case-insensitive LIKE met %term% wrap, single value
INT_FILTERS = ("jaar", "kwartaal", "maand", "week")
ID_FILTERS = ("vestigingseenheidreferentieid", "klantreferentieid", "persoonreferentieid")
LIKE_FILTERS = ("klantnaam", "familienaam", "voornaam")


# ---------------------------------------------------------------------------
# Connection helper — 30 min statement_timeout
# ---------------------------------------------------------------------------


@contextmanager
def _connect_long_running(timeout_ms: int = 1_800_000) -> Iterator[Any]:
    if not is_configured():
        raise PratoNotConfigured(
            "Prato DB-credentials ontbreken. Zet PRATO_DB_HOST, PRATO_DB_USER, "
            "PRATO_DB_PASSWORD en PRATO_DB_NAME in Railway -> Variables."
        )
    import psycopg

    log.info(
        "Prato connect (export) host=%s db=%s user=%s",
        settings.PRATO_DB_HOST,
        settings.PRATO_DB_NAME,
        settings.PRATO_DB_USER,
    )
    conn = psycopg.connect(
        host=settings.PRATO_DB_HOST,
        port=settings.PRATO_DB_PORT,
        user=settings.PRATO_DB_USER,
        password=settings.PRATO_DB_PASSWORD,
        dbname=settings.PRATO_DB_NAME,
        sslmode=settings.PRATO_DB_SSLMODE,
        connect_timeout=30,
        application_name="mathieus-agent-export-csv",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            cur.execute(f"SET statement_timeout = {int(timeout_ms)}")
        yield conn
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# SQL — basis (zonder WHERE) + filter-builder
# ---------------------------------------------------------------------------
#
# Strategie:
#   1. margelijst                = officiele query (per persoon, datum)
#   2. gfb_agg                   = per (persoon, datum): SUM(bedrag) + klantref
#                                  uit facturatie.gefactureerdebedragen
#   3. tfb_agg                   = idem uit facturatie.tefacturerenbedragen
#   4. klantmap_dedup            = (persoon, datum) -> één klantreferentieid,
#                                  UNION van beide bronnen
#   5. klant_data                = (klantreferentieid -> naam)
#   6. joined (per-dag rijen)    = margelijst.* + omzet_gefactureerd
#                                  + omzet_te_factureren + klantreferentieid
#                                  + klantnaam
#   7. final (per-week aggregaat) = GROUP BY de 10 dimensies, SUM van measures,
#                                   margeperuur herberekend
#
# WHERE-clause op de joined CTE bewust *voor* de aggregatie zodat filters
# correct effect hebben.

_BASE_SQL_TEMPLATE = f"""
WITH margelijst AS ({_MARGELIJST_SQL}),
margelijst_j AS (
    SELECT m.*,
           m.persoonreferentieid::text AS join_persoon,
           m.datum::date AS join_datum
    FROM margelijst m
),
gfb_agg AS (
    SELECT persoonreferentieid::text AS join_persoon,
           prestatiedatum::date AS join_datum,
           SUM(bedrag) AS bedrag_som,
           MAX(klantreferentieid::text) AS klantreferentieid
    FROM facturatie.gefactureerdebedragen
    WHERE persoonreferentieid IS NOT NULL AND prestatiedatum IS NOT NULL
    GROUP BY persoonreferentieid::text, prestatiedatum::date
),
tfb_agg AS (
    SELECT persoonreferentieid::text AS join_persoon,
           prestatiedatum::date AS join_datum,
           SUM(bedrag) AS bedrag_som,
           MAX(klantreferentieid::text) AS klantreferentieid
    FROM facturatie.tefacturerenbedragen
    WHERE persoonreferentieid IS NOT NULL AND prestatiedatum IS NOT NULL
    GROUP BY persoonreferentieid::text, prestatiedatum::date
),
klantmap AS (
    SELECT join_persoon, join_datum, klantreferentieid
    FROM gfb_agg WHERE klantreferentieid IS NOT NULL
    UNION
    SELECT join_persoon, join_datum, klantreferentieid
    FROM tfb_agg WHERE klantreferentieid IS NOT NULL
),
klantmap_dedup AS (
    SELECT join_persoon, join_datum,
           MAX(klantreferentieid) AS klantreferentieid
    FROM klantmap
    GROUP BY join_persoon, join_datum
),
klant_data AS (
    SELECT referentieid::text AS klant_join_id,
           naam AS klantnaam
    FROM facturatie.klant
),
joined AS (
    SELECT
        m.jaar::integer                          AS jaar,
        m.kwartaal::integer                      AS kwartaal,
        m.maand::integer                         AS maand,
        m.week::integer                          AS week,
        m.vestigingseenheidreferentieid::text    AS vestigingseenheidreferentieid,
        km.klantreferentieid                     AS klantreferentieid,
        k.klantnaam                              AS klantnaam,
        m.persoonreferentieid::text              AS persoonreferentieid,
        m.familienaam                            AS familienaam,
        m.voornaam                               AS voornaam,
        m.loonkost                               AS loonkost,
        m.werkuitkering                          AS werkuitkering,
        m.bvvrijstellingen                       AS bvvrijstellingen,
        m.rszwerkgeversbijdragen                 AS rszwerkgeversbijdragen,
        m.rszverminderingen                      AS rszverminderingen,
        m.provisies                              AS provisies,
        COALESCE(g.bedrag_som, 0)                AS omzet_gefactureerd,
        COALESCE(t.bedrag_som, 0)                AS omzet_te_factureren,
        m.kost                                   AS kost,
        m.verloonde_uren                         AS verloonde_uren
    FROM margelijst_j m
    LEFT JOIN klantmap_dedup km USING (join_persoon, join_datum)
    LEFT JOIN klant_data     k  ON k.klant_join_id = km.klantreferentieid
    LEFT JOIN gfb_agg        g  USING (join_persoon, join_datum)
    LEFT JOIN tfb_agg        t  USING (join_persoon, join_datum)
)
SELECT
    jaar, kwartaal, maand, week,
    vestigingseenheidreferentieid,
    klantreferentieid, klantnaam,
    persoonreferentieid, familienaam, voornaam,
    SUM(loonkost)                       AS loonkost,
    SUM(werkuitkering)                  AS werkuitkering,
    SUM(bvvrijstellingen)               AS bvvrijstellingen,
    SUM(rszwerkgeversbijdragen)         AS rszwerkgeversbijdragen,
    SUM(rszverminderingen)              AS rszverminderingen,
    SUM(provisies)                      AS provisies,
    SUM(omzet_gefactureerd)             AS omzet_gefactureerd,
    SUM(omzet_te_factureren)            AS omzet_te_factureren,
    SUM(kost)                           AS kost,
    SUM(verloonde_uren)                 AS verloonde_uren,
    (SUM(omzet_gefactureerd) + SUM(omzet_te_factureren) - SUM(kost))
                                        AS marge,
    CASE
        WHEN SUM(verloonde_uren) = 0::numeric THEN NULL::numeric
        ELSE ROUND(
            (SUM(omzet_gefactureerd) + SUM(omzet_te_factureren) - SUM(kost))
            / SUM(verloonde_uren),
            2
        )
    END                                  AS margeperuur
FROM joined
{{WHERE_CLAUSE}}
GROUP BY jaar, kwartaal, maand, week,
         vestigingseenheidreferentieid,
         klantreferentieid, klantnaam,
         persoonreferentieid, familienaam, voornaam
ORDER BY jaar, kwartaal, maand, week, klantnaam, persoonreferentieid
"""


def build_export_sql(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    """Bouw de uiteindelijke SQL + params lijst op basis van filters.

    filters dict-keys mappen 1:1 op kolomnamen. Lege/None waarden worden
    overgeslagen. Lijsten geven multi-value filters."""
    where_parts: list[str] = []
    params: list[Any] = []

    for col in INT_FILTERS:
        v = filters.get(col)
        if v is None or (isinstance(v, list) and not v):
            continue
        vals = v if isinstance(v, list) else [v]
        try:
            int_vals = [int(x) for x in vals]
        except (TypeError, ValueError):
            log.warning("Skip ongeldige integer filter %s=%r", col, vals)
            continue
        where_parts.append(f"{col} = ANY(%s)")
        params.append(int_vals)

    for col in ID_FILTERS:
        v = filters.get(col)
        if v is None or (isinstance(v, list) and not v):
            continue
        vals = v if isinstance(v, list) else [v]
        str_vals = [str(x) for x in vals if x is not None and x != ""]
        if not str_vals:
            continue
        where_parts.append(f"{col} = ANY(%s)")
        params.append(str_vals)

    for col in LIKE_FILTERS:
        v = filters.get(col)
        if v is None or v == "":
            continue
        # Single value (eerste indien lijst meegegeven)
        val = v[0] if isinstance(v, list) else v
        where_parts.append(f"{col} ILIKE %s")
        params.append(f"%{val}%")

    where_clause = ""
    if where_parts:
        where_clause = "WHERE " + " AND ".join(where_parts)

    sql = _BASE_SQL_TEMPLATE.replace("{WHERE_CLAUSE}", where_clause)
    return sql, params


# ---------------------------------------------------------------------------
# CSV streaming
# ---------------------------------------------------------------------------


def _format_be_decimal(value: Any) -> str:
    """Format één cel als CSV-string in Belgische conventie."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, Decimal):
        return str(value).replace(".", ",")
    if isinstance(value, float):
        return f"{value}".replace(".", ",")
    if isinstance(value, int):
        return str(value)
    # date / datetime -> ISO
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()
    s = str(value)
    if ";" in s:
        s = s.replace(";", ",")
    if "\n" in s or "\r" in s:
        s = s.replace("\r", " ").replace("\n", " ")
    return s


def _row_to_csv_line(row_dict: dict[str, Any]) -> bytes:
    cells = [_format_be_decimal(row_dict.get(col)) for col in EXPORT_COLUMNS]
    return (";".join(cells) + "\n").encode("utf-8")


def stream_export_csv(filters: dict[str, Any]) -> Iterator[bytes]:
    """Yield de CSV regel-per-regel als bytes.

    Eerste yield is de header. Daarna server-side cursor over de query."""
    sql, params = build_export_sql(filters)
    log.info("export-csv: sql length=%d, filter-params=%d, applying filters=%s",
             len(sql), len(params), {k: v for k, v in filters.items() if v})

    yield (";".join(EXPORT_COLUMNS) + "\n").encode("utf-8")

    with _connect_long_running() as conn:
        with conn.cursor(name="export_csv") as cur:
            cur.itersize = 5000
            cur.execute(sql, params)
            cols = [d.name for d in cur.description] if cur.description else []

            row_count = 0
            for raw_row in cur:
                rec = dict(zip(cols, raw_row))
                yield _row_to_csv_line(rec)
                row_count += 1
                if row_count % 10_000 == 0:
                    log.info("export-csv: %d rijen", row_count)

            log.info("export-csv: klaar — %d rijen", row_count)


# ---------------------------------------------------------------------------
# Diagnose-helper (blijft behouden, handig voor introspectie)
# ---------------------------------------------------------------------------


def _count_in_view(conn: Any, schema: str, table: str, where: str = "") -> int:
    sql = f"SELECT COUNT(*) FROM {schema}.{table}"
    if where:
        sql += f" WHERE {where}"
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()[0]
    except Exception:  # noqa: BLE001
        log.exception("count faalde: %s", sql)
        return -1


def diagnostic_summary() -> dict[str, Any]:
    out: dict[str, Any] = {}
    joinable_where = (
        "persoonreferentieid IS NOT NULL "
        "AND prestatiedatum IS NOT NULL "
        "AND klantreferentieid IS NOT NULL"
    )
    with _connect_long_running(timeout_ms=60_000) as conn:
        out["facturatie.gefactureerdebedragen"] = {
            "total_rows": _count_in_view(conn, "facturatie", "gefactureerdebedragen"),
            "joinable_rows": _count_in_view(
                conn, "facturatie", "gefactureerdebedragen", joinable_where
            ),
        }
        out["facturatie.tefacturerenbedragen"] = {
            "total_rows": _count_in_view(conn, "facturatie", "tefacturerenbedragen"),
            "joinable_rows": _count_in_view(
                conn, "facturatie", "tefacturerenbedragen", joinable_where
            ),
        }
        out["facturatie.klant"] = {
            "total_rows": _count_in_view(conn, "facturatie", "klant"),
        }
    return out
