"""SQLite cache layer voor de margelijst-data.

De volledige Prato-export wordt in een lokale SQLite-DB opgeslagen onder
DATA_DIR (= /data op Railway, op het Volume). Bij elke sync wordt de
volledige `margelijst`-tabel overschreven (DELETE + INSERT). Mathieu's
expliciete keuze: geen incrementele logica, geen merge.

Filters in de webapp lezen uit deze SQLite — geen live Prato-roundtrip
meer per request. Daardoor zijn filter-queries op de webapp instant,
ook bij honderdduizenden rijen.

Sync-schedule:
  - cron: elke dag om 11:59 Europe/Brussels
  - manueel: POST /sync/run

Schema:
  margelijst   — 22 kolommen, exact zoals EXPORT_COLUMNS
  sync_meta    — log per sync-run (started_at, status, rows_loaded, ...)
"""

from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Optional

from .config import settings

log = logging.getLogger("dashboard-nestor.cache")


CACHE_DB_FILENAME = "margelijst.sqlite"


def cache_db_path() -> Path:
    """Path naar de cache-database. Zorgt dat DATA_DIR bestaat."""
    data_dir = Path(settings.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / CACHE_DB_FILENAME


@contextmanager
def cache_conn() -> Iterator[sqlite3.Connection]:
    """SQLite verbinding, autocommit, row_factory=Row voor dict-achtige toegang.

    SQLite-verbindingen zijn per-thread — we openen een nieuwe per call
    zodat APScheduler-threads + FastAPI-handlers veilig naast elkaar werken.
    """
    conn = sqlite3.connect(
        str(cache_db_path()),
        isolation_level=None,  # autocommit; we beheren BEGIN/COMMIT zelf bij sync
        timeout=30.0,           # wait up to 30s on database locks
    )
    conn.row_factory = sqlite3.Row
    try:
        # WAL mode is veiliger bij concurrent reads tijdens een schrijvende sync
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        yield conn
    finally:
        conn.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS margelijst (
    jaar INTEGER,
    kwartaal INTEGER,
    maand INTEGER,
    week INTEGER,
    vestigingseenheidreferentieid TEXT,
    klantreferentieid TEXT,
    klantnaam TEXT,
    persoonreferentieid TEXT,
    familienaam TEXT,
    voornaam TEXT,
    loonkost REAL,
    werkuitkering REAL,
    bvvrijstellingen REAL,
    rszwerkgeversbijdragen REAL,
    rszverminderingen REAL,
    provisies REAL,
    omzet_gefactureerd REAL,
    omzet_te_factureren REAL,
    kost REAL,
    verloonde_uren REAL,
    marge REAL,
    margeperuur REAL
);

CREATE INDEX IF NOT EXISTS idx_jaar ON margelijst(jaar);
CREATE INDEX IF NOT EXISTS idx_klant ON margelijst(klantreferentieid);
CREATE INDEX IF NOT EXISTS idx_persoon ON margelijst(persoonreferentieid);
CREATE INDEX IF NOT EXISTS idx_periode ON margelijst(jaar, maand, week);
CREATE INDEX IF NOT EXISTS idx_klantnaam ON margelijst(klantnaam);
CREATE INDEX IF NOT EXISTS idx_familienaam ON margelijst(familienaam);
CREATE INDEX IF NOT EXISTS idx_voornaam ON margelijst(voornaam);

CREATE TABLE IF NOT EXISTS margelijst_historisch (
    jaar INTEGER,
    kwartaal INTEGER,
    maand INTEGER,
    week INTEGER,                     -- altijd NULL voor historisch (= maand-grain)
    vestigingseenheidreferentieid TEXT,
    klantreferentieid TEXT,
    klantnaam TEXT,
    persoonreferentieid TEXT,
    familienaam TEXT,                 -- volledige naam (niet gesplitst, '' voor voornaam)
    voornaam TEXT,
    loonkost REAL,                    -- = Kost in CSV (gegroepeerde loonkost)
    werkuitkering REAL,
    bvvrijstellingen REAL,            -- = BVVerm
    rszwerkgeversbijdragen REAL,      -- = RSZ_SV (RSZ_Andere wordt apart bewaard)
    rszverminderingen REAL,
    provisies REAL,                   -- = AutoProv
    omzet_gefactureerd REAL,          -- = 'Totale omzet' (historisch is alles 'gefactureerd')
    omzet_te_factureren REAL,         -- NULL voor historisch
    kost REAL,                        -- = TotaleKost
    verloonde_uren REAL,              -- = 'Totale uren'
    marge REAL,
    margeperuur REAL,                 -- afgeleid: marge / verloonde_uren

    -- Historiek-only kolommen (raw bewaard)
    bruto_loon REAL,                  -- = Bruto
    rsz_andere REAL,                  -- = RSZ_Andere (geen equivalent in live)
    margeprocent REAL,                -- = 'Marge%' (live heeft margeperuur)
    sektie_origineel TEXT,            -- = Sektie (HIAnt code, niet 1-op-1 mapbaar)
    type_origineel INTEGER,           -- = Type (1 of 2)
    jobstudent_flag INTEGER,          -- = Jobstudent (0/1/2)
    up_kost REAL,                     -- aantal uur (UP)
    up_omzet REAL,
    ou_kost REAL,                     -- aantal uur (OU)
    ou_omzet REAL,
    gepresteerde_uren REAL,           -- = UP_kost + OU_kost (volgens definitie Mathieu)
    wgnr_omzet INTEGER                -- altijd -1 in de CSV, betekenis onbekend
);

CREATE INDEX IF NOT EXISTS idx_h_jaar ON margelijst_historisch(jaar);
CREATE INDEX IF NOT EXISTS idx_h_klant ON margelijst_historisch(klantreferentieid);
CREATE INDEX IF NOT EXISTS idx_h_persoon ON margelijst_historisch(persoonreferentieid);
CREATE INDEX IF NOT EXISTS idx_h_periode ON margelijst_historisch(jaar, maand);
CREATE INDEX IF NOT EXISTS idx_h_klantnaam ON margelijst_historisch(klantnaam);
CREATE INDEX IF NOT EXISTS idx_h_familienaam ON margelijst_historisch(familienaam);

CREATE TABLE IF NOT EXISTS sektie_kengetal_map (
    sektie_origineel TEXT PRIMARY KEY,
    werknemerskengetal TEXT NOT NULL,
    omschrijving TEXT
);

CREATE TABLE IF NOT EXISTS import_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bron TEXT NOT NULL,            -- 'historisch'
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,           -- 'running','ok','failed'
    rows_loaded INTEGER,
    rows_skipped INTEGER,
    filename TEXT,
    error TEXT
);

-- View: UNION van live + historisch.
-- Voor (jaar, maand)-combinaties die in BEIDE bronnen bestaan: kies historisch
-- (= afgesloten data, gezaghebbender dan onze in-progress live cache).
-- Note: bij wijziging van deze view-definitie moet je expliciet DROP doen
-- vanuit een migratie — CREATE VIEW IF NOT EXISTS recreëert niet bij wijziging.
CREATE VIEW IF NOT EXISTS v_margelijst AS
SELECT
    jaar, kwartaal, maand, week,
    vestigingseenheidreferentieid,
    klantreferentieid, klantnaam,
    persoonreferentieid, familienaam, voornaam,
    loonkost, werkuitkering, bvvrijstellingen,
    rszwerkgeversbijdragen, rszverminderingen, provisies,
    omzet_gefactureerd, omzet_te_factureren,
    kost, verloonde_uren, marge, margeperuur,
    COALESCE(
        (SELECT werknemerskengetal FROM sektie_kengetal_map
         WHERE sektie_origineel = h.sektie_origineel),
        NULL
    ) AS werknemerskengetal,
    sektie_origineel,
    gepresteerde_uren,
    'historisch' AS bron
FROM margelijst_historisch h

UNION ALL

SELECT
    jaar, kwartaal, maand, week,
    vestigingseenheidreferentieid,
    klantreferentieid, klantnaam,
    persoonreferentieid, familienaam, voornaam,
    loonkost, werkuitkering, bvvrijstellingen,
    rszwerkgeversbijdragen, rszverminderingen, provisies,
    omzet_gefactureerd, omzet_te_factureren,
    kost, verloonde_uren, marge, margeperuur,
    NULL AS werknemerskengetal,   -- live data heeft niet (nog) een kengetal-kolom in cache
    NULL AS sektie_origineel,
    verloonde_uren AS gepresteerde_uren,  -- live: bij gebrek aan onderscheid = verloonde
    'live' AS bron
FROM margelijst m
WHERE NOT EXISTS (
    SELECT 1 FROM margelijst_historisch h
    WHERE h.jaar = m.jaar AND h.maand = m.maand
);

CREATE TABLE IF NOT EXISTS sync_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    rows_loaded INTEGER,
    duration_ms INTEGER,
    error TEXT
);

CREATE TABLE IF NOT EXISTS pinned_charts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titel TEXT NOT NULL,
    metric TEXT NOT NULL,                       -- 'omzet','marge','loonkost','kost','uren','medewerkers','omzet_ltm','marge_ltm','uren_ltm','top_klanten_omzet','top_klanten_marge','uren_per_medewerker'
    segment TEXT NOT NULL,                      -- 'nestor','nestor_core','smartmat','martha','vab','all'
    chart_type TEXT NOT NULL DEFAULT 'line',    -- 'line','bar'
    grain TEXT NOT NULL DEFAULT 'month',        -- 'month','week','year','klant'
    period_mode TEXT NOT NULL DEFAULT 'ltm',    -- 'ltm','ytd','year','all'
    period_value TEXT,                          -- bv '2026' bij mode='year'
    extra_options TEXT,                         -- JSON (top_n, etc)
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def init_schema() -> None:
    """Maak tabellen + indexen aan als ze nog niet bestaan. Idempotent.
    Synchroniseert sektie_kengetal_map vanuit de hardcoded Python-mapping.
    Migreert pinned_charts.series_json kolom als die nog niet bestaat."""
    with cache_conn() as conn:
        conn.executescript(_SCHEMA)
        _ensure_column(conn, "pinned_charts", "series_json", "TEXT")
    _sync_sektie_mappings_from_code()
    log.info("Cache schema ready at %s", cache_db_path())


def _ensure_column(conn: Any, table: str, col: str, ddl_type: str) -> None:
    """SQLite ondersteunt geen ADD COLUMN IF NOT EXISTS. We checken via PRAGMA."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl_type}")
        log.info("Migratie: kolom %s toegevoegd aan %s", col, table)


def _sync_sektie_mappings_from_code() -> None:
    """Vul sektie_kengetal_map vanuit app.mappings.SEKTIE_KENGETAL."""
    from .mappings import SEKTIE_KENGETAL, SEKTIE_OMSCHRIJVING
    with cache_conn() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM sektie_kengetal_map")
            for sektie, kengetal in SEKTIE_KENGETAL.items():
                conn.execute(
                    "INSERT INTO sektie_kengetal_map (sektie_origineel, werknemerskengetal, omschrijving) "
                    "VALUES (?, ?, ?)",
                    (sektie, kengetal, SEKTIE_OMSCHRIJVING.get(sektie)),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


# ---------------------------------------------------------------------------
# Sync — vul cache opnieuw uit Prato
# ---------------------------------------------------------------------------


def _to_sqlite_value(value: Any) -> Any:
    """Convert Postgres-types naar SQLite-compatible primitives."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
        return value.isoformat()
    return value


def sync_from_prato() -> dict[str, Any]:
    """Volledige refresh: leeg margelijst, vul met huidige Prato-data.

    Returnt een dict met status/rows_loaded/duration_ms. Logt naar
    sync_meta voor de UI om de laatste sync-info te kunnen tonen.
    """
    # Lazy imports zodat circulaire imports vermeden worden + cache.py
    # blijft importeerbaar zonder fastapi/psycopg.
    from .prato_export import _EXPORT_SQL, EXPORT_COLUMNS, _connect_long_running

    init_schema()
    started_at_iso = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()

    # Log start
    with cache_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sync_meta (started_at, status) VALUES (?, ?)",
            (started_at_iso, "running"),
        )
        sync_id = cur.lastrowid

    try:
        log.info("sync: Prato-query starten")
        rows_loaded = 0

        with _connect_long_running() as pg_conn:
            with pg_conn.cursor(name="dashboard_sync") as pg_cur:
                pg_cur.itersize = 5000
                pg_cur.execute(_EXPORT_SQL)
                cols = [d.name for d in pg_cur.description] if pg_cur.description else []

                # Verify cols match expected
                expected_set = set(EXPORT_COLUMNS)
                got_set = set(cols)
                if got_set != expected_set:
                    missing = expected_set - got_set
                    extra = got_set - expected_set
                    raise RuntimeError(
                        f"Kolom-mismatch — ontbrekend: {missing}, extra: {extra}"
                    )

                col_idx = [cols.index(c) for c in EXPORT_COLUMNS]
                placeholders = ",".join(["?"] * len(EXPORT_COLUMNS))
                insert_sql = (
                    "INSERT INTO margelijst ("
                    + ",".join(EXPORT_COLUMNS)
                    + f") VALUES ({placeholders})"
                )

                with cache_conn() as cache:
                    cache.execute("BEGIN")
                    try:
                        cache.execute("DELETE FROM margelijst")
                        batch: list[tuple] = []
                        BATCH_SIZE = 5000
                        for pg_row in pg_cur:
                            row = tuple(_to_sqlite_value(pg_row[i]) for i in col_idx)
                            batch.append(row)
                            if len(batch) >= BATCH_SIZE:
                                cache.executemany(insert_sql, batch)
                                rows_loaded += len(batch)
                                batch = []
                                log.info("sync: %d rijen", rows_loaded)
                        if batch:
                            cache.executemany(insert_sql, batch)
                            rows_loaded += len(batch)
                        cache.execute("COMMIT")
                    except Exception:
                        cache.execute("ROLLBACK")
                        raise

        duration_ms = int((time.monotonic() - started) * 1000)
        ended_at_iso = datetime.now(timezone.utc).isoformat()

        with cache_conn() as conn:
            conn.execute(
                "UPDATE sync_meta SET ended_at=?, status='ok', rows_loaded=?, duration_ms=? WHERE id=?",
                (ended_at_iso, rows_loaded, duration_ms, sync_id),
            )

        log.info("sync: klaar — %d rijen / %d ms", rows_loaded, duration_ms)
        return {"status": "ok", "rows_loaded": rows_loaded, "duration_ms": duration_ms}

    except Exception as e:  # noqa: BLE001
        log.exception("sync: gefaald")
        duration_ms = int((time.monotonic() - started) * 1000)
        ended_at_iso = datetime.now(timezone.utc).isoformat()
        with cache_conn() as conn:
            conn.execute(
                "UPDATE sync_meta SET ended_at=?, status='failed', duration_ms=?, error=? WHERE id=?",
                (ended_at_iso, duration_ms, str(e)[:500], sync_id),
            )
        return {"status": "failed", "error": str(e)[:500], "duration_ms": duration_ms}


# ---------------------------------------------------------------------------
# Read — lees uit cache met dezelfde filter-conventies als de oorspronkelijke
# Prato-query
# ---------------------------------------------------------------------------


def read_cached(filters: dict[str, Any]) -> Iterator[tuple]:
    """Yield rijen uit de cache, gefilterd. Output is tuples in EXPORT_COLUMNS-volgorde.

    Filter-conventies (identiek aan de oude Prato-query):
      - INT_FILTERS (jaar/kwartaal/maand/week): IN-clause op integer-lijst
      - ID_FILTERS  (vestiging/klantref/persoonref): IN-clause op text-lijst
      - LIKE_FILTERS (klantnaam/familienaam/voornaam): %term% case-insensitive
    """
    from .prato_export import (
        EXPORT_COLUMNS, INT_FILTERS, ID_FILTERS, LIKE_FILTERS,
    )

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
            continue
        placeholders = ",".join(["?"] * len(int_vals))
        where_parts.append(f"{col} IN ({placeholders})")
        params.extend(int_vals)

    for col in ID_FILTERS:
        v = filters.get(col)
        if v is None or (isinstance(v, list) and not v):
            continue
        vals = v if isinstance(v, list) else [v]
        str_vals = [str(x) for x in vals if x is not None and x != ""]
        if not str_vals:
            continue
        placeholders = ",".join(["?"] * len(str_vals))
        where_parts.append(f"{col} IN ({placeholders})")
        params.extend(str_vals)

    for col in LIKE_FILTERS:
        v = filters.get(col)
        if v is None or v == "":
            continue
        val = v[0] if isinstance(v, list) else v
        # SQLite LIKE is by default case-insensitive voor ASCII; voor accent-strippen
        # zou een eigen collation nodig zijn. Voorlopig akkoord met ASCII-insensitive.
        where_parts.append(f"LOWER({col}) LIKE ?")
        params.append(f"%{val.lower()}%")

    cols_csv = ",".join(EXPORT_COLUMNS)
    # Lees uit v_margelijst (= UNION van live + historisch, met dedup op overlap)
    sql = f"SELECT {cols_csv} FROM v_margelijst"
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    sql += " ORDER BY jaar, kwartaal, maand, week, klantnaam, persoonreferentieid"

    init_schema()  # auto-init voor first run
    with cache_conn() as conn:
        for row in conn.execute(sql, params):
            yield tuple(row)


# ---------------------------------------------------------------------------
# Meta / status helpers
# ---------------------------------------------------------------------------


def get_last_sync() -> Optional[dict[str, Any]]:
    """Laatste sync_meta-rij als dict, of None."""
    init_schema()
    with cache_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sync_meta ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return dict(row)
    return None


def get_running_sync() -> Optional[dict[str, Any]]:
    """Eventuele sync-rij die status='running' heeft, of None."""
    init_schema()
    with cache_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sync_meta WHERE status='running' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return dict(row)
    return None


def get_row_count() -> int:
    """Aantal rijen in v_margelijst (= live + historisch, met dedup)."""
    init_schema()
    with cache_conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM v_margelijst").fetchone()
        return row[0] if row else 0


def get_row_count_breakdown() -> dict:
    """Aantal rijen per bron — handig voor /api/status diagnostics."""
    init_schema()
    with cache_conn() as conn:
        live = conn.execute("SELECT COUNT(*) FROM margelijst").fetchone()[0]
        hist = conn.execute("SELECT COUNT(*) FROM margelijst_historisch").fetchone()[0]
        view = conn.execute("SELECT COUNT(*) FROM v_margelijst").fetchone()[0]
    return {"live": live, "historisch": hist, "total_in_view": view}


# ---------------------------------------------------------------------------
# Pinned charts — vastgepinde dashboard-grafieken
# ---------------------------------------------------------------------------


_DEFAULT_PINNED = [
    # Single-series defaults (oude lijst — bewust korter gemaakt voor v0.6)
    # (titel, metric, segment, chart_type, grain, period_mode, period_value,
    #  extra_options_json, position, series_json)
    ("Omzet per maand — Nestor Core", "omzet", "nestor_core", "line", "month", "ltm", None, None, 10, None),
    ("Bruto marge per maand — Nestor Core", "marge", "nestor_core", "line", "month", "ltm", None, None, 11, None),
    ("Gepresteerde uren per week — Nestor Core", "uren", "nestor_core", "line", "week", "ltm", None, None, 12, None),
    ("Top 10 klanten op omzet — Nestor Core (LTM)", "top_klanten_omzet", "nestor_core", "bar", "klant", "ltm", None, '{"top_n":10}', 13, None),
]


# Multi-series default-pins (de twee charts die Mathieu expliciet vroeg).
# series_json wordt door dashboards_body() gelezen als lijst van
# (metric, segment) tuples; elke combo wordt een aparte lijn op de chart.
_DEFAULT_PINNED_MULTI = [
    # (titel, segment_default, chart_type, grain, period_mode, period_value,
    #  extra_options_json, position, series_json)
    (
        "Nestor — Omzet & Bruto marge per maand (sinds 2025-01)",
        "nestor", "line", "month", "since", "2025-01", None, 0,
        '[{"metric":"omzet","segment":"nestor","label":"Omzet"},'
        '{"metric":"marge","segment":"nestor","label":"Bruto marge"}]',
    ),
    (
        "Nestor — Omzet & Bruto marge LTM (rolling 12 mo)",
        "nestor", "line", "month", "all", None, None, 1,
        '[{"metric":"omzet_ltm","segment":"nestor","label":"Omzet LTM"},'
        '{"metric":"marge_ltm","segment":"nestor","label":"Bruto marge LTM"}]',
    ),
]


def seed_default_pinned() -> int:
    """Insert de default-pinned grafieken (zowel single-series als multi).

    Idempotent: pins worden geïdentificeerd op `titel`. Bestaande titels
    worden niet opnieuw toegevoegd. Returnt het aantal NIEUWE rijen.
    Mathieu kan via /api/pinned/{id} unpinnen wat hij niet wil; bij volgende
    deploy worden ze niet opnieuw toegevoegd want de titel bestaat al niet
    (alleen de andere titels).
    """
    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    new_count = 0
    with cache_conn() as conn:
        existing_titles = {
            row[0] for row in conn.execute("SELECT titel FROM pinned_charts").fetchall()
        }

        # Single-series
        for (titel, metric, segment, chart_type, grain, period_mode, period_value,
             extra, pos, series_json) in _DEFAULT_PINNED:
            if titel in existing_titles:
                continue
            conn.execute(
                """
                INSERT INTO pinned_charts
                  (titel, metric, segment, chart_type, grain, period_mode, period_value,
                   extra_options, position, created_at, series_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (titel, metric, segment, chart_type, grain, period_mode, period_value,
                 extra, pos, now, series_json),
            )
            new_count += 1

        # Multi-series (segment-veld is enkel een fallback-label; echte
        # specs zitten in series_json)
        for (titel, segment, chart_type, grain, period_mode, period_value,
             extra, pos, series_json) in _DEFAULT_PINNED_MULTI:
            if titel in existing_titles:
                continue
            conn.execute(
                """
                INSERT INTO pinned_charts
                  (titel, metric, segment, chart_type, grain, period_mode, period_value,
                   extra_options, position, created_at, series_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                # metric-kolom is verplicht (NOT NULL); we vullen 'multi' in als marker
                (titel, "multi", segment, chart_type, grain, period_mode, period_value,
                 extra, pos, now, series_json),
            )
            new_count += 1

    if new_count:
        log.info("Default-pinned grafieken geseed: %d nieuwe", new_count)
    return new_count


def reset_pinned_charts() -> int:
    """Wis alle pinned charts en re-seed de defaults. Returnt nieuw-count."""
    init_schema()
    with cache_conn() as conn:
        conn.execute("DELETE FROM pinned_charts")
    return seed_default_pinned()


def list_pinned_charts() -> list[dict[str, Any]]:
    init_schema()
    with cache_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pinned_charts ORDER BY position, id"
        ).fetchall()
    return [dict(r) for r in rows]


def add_pinned_chart(
    titel: str,
    metric: str,
    segment: str,
    chart_type: str = "line",
    grain: str = "month",
    period_mode: str = "ltm",
    period_value: Optional[str] = None,
    extra_options: Optional[str] = None,
    series_json: Optional[str] = None,
) -> int:
    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    with cache_conn() as conn:
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) FROM pinned_charts"
        ).fetchone()[0]
        cur = conn.execute(
            """
            INSERT INTO pinned_charts
              (titel, metric, segment, chart_type, grain, period_mode, period_value,
               extra_options, position, created_at, series_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (titel, metric, segment, chart_type, grain, period_mode, period_value,
             extra_options, max_pos + 1, now, series_json),
        )
        return cur.lastrowid


def delete_pinned_chart(chart_id: int) -> bool:
    init_schema()
    with cache_conn() as conn:
        cur = conn.execute("DELETE FROM pinned_charts WHERE id = ?", (chart_id,))
        return cur.rowcount > 0


def reorder_pinned_charts(id_order: list[int]) -> None:
    """Update position-veld op basis van een nieuwe volgorde."""
    init_schema()
    with cache_conn() as conn:
        conn.execute("BEGIN")
        try:
            for new_pos, chart_id in enumerate(id_order):
                conn.execute(
                    "UPDATE pinned_charts SET position = ? WHERE id = ?",
                    (new_pos, chart_id),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
