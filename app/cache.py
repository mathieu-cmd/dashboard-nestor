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

-- klant_mapping: HIAnt klant-id -> Earnie klant-id.
-- Wordt automatisch geseed op name-match + manueel overschreven vanuit
-- mappings.KLANT_HIANT_TO_EARNIE.
CREATE TABLE IF NOT EXISTS klant_mapping (
    hiant_klantref TEXT PRIMARY KEY,
    earnie_klantref TEXT NOT NULL,
    canonical_naam TEXT,
    source TEXT NOT NULL DEFAULT 'auto'   -- 'auto', 'manual', 'confirmed'
);
CREATE INDEX IF NOT EXISTS idx_km_earnie ON klant_mapping(earnie_klantref);

-- uren_extern: extern aangeleverde uren per (jaar, week, segment).
-- Wordt vervangen bij elke CSV-import (TRUNCATE + INSERT).
CREATE TABLE IF NOT EXISTS uren_extern (
    jaar INTEGER NOT NULL,
    week INTEGER NOT NULL,
    segment TEXT NOT NULL,        -- 'nestor_core', 'smartmat', etc.
    uren REAL NOT NULL,
    PRIMARY KEY (jaar, week, segment)
);
CREATE INDEX IF NOT EXISTS idx_uren_extern_segment ON uren_extern(segment);
CREATE INDEX IF NOT EXISTS idx_uren_extern_periode ON uren_extern(jaar, week);

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

-- View: UNION van live + historisch met klant-id-merge.
-- Voor (jaar, maand)-combinaties die in BEIDE bronnen bestaan: kies historisch
-- (= afgesloten data, gezaghebbender dan onze in-progress live cache).
-- Historische klantref wordt via klant_mapping omgezet naar Earnie-id wanneer
-- gemapt, zodat dezelfde klant niet als twee aparte verschijnt.
-- Note: bij wijziging van deze view-definitie wordt DROP gedaan via init_schema.
DROP VIEW IF EXISTS v_margelijst;
CREATE VIEW IF NOT EXISTS v_margelijst AS
SELECT
    h.jaar, h.kwartaal, h.maand, h.week,
    h.vestigingseenheidreferentieid,
    -- Gemerged klantref: vervang HIAnt-id door Earnie-id indien gemapt
    -- (skip 'rejected'-rijen — die mochten expliciet NIET koppelen).
    COALESCE(
        (SELECT km.earnie_klantref FROM klant_mapping km
         WHERE km.hiant_klantref = h.klantreferentieid
           AND km.source != 'rejected'),
        h.klantreferentieid
    ) AS klantreferentieid,
    COALESCE(
        (SELECT km.canonical_naam FROM klant_mapping km
         WHERE km.hiant_klantref = h.klantreferentieid
           AND km.source != 'rejected' AND km.canonical_naam IS NOT NULL),
        h.klantnaam
    ) AS klantnaam,
    h.persoonreferentieid, h.familienaam, h.voornaam,
    h.loonkost, h.werkuitkering, h.bvvrijstellingen,
    h.rszwerkgeversbijdragen, h.rszverminderingen, h.provisies,
    h.omzet_gefactureerd, h.omzet_te_factureren,
    h.kost, h.verloonde_uren, h.marge, h.margeperuur,
    COALESCE(
        (SELECT werknemerskengetal FROM sektie_kengetal_map
         WHERE sektie_origineel = h.sektie_origineel),
        NULL
    ) AS werknemerskengetal,
    h.sektie_origineel,
    h.gepresteerde_uren,
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


# Pin-titels die we automatisch opruimen bij elke startup omdat ze door
# een nieuwere versie zijn vervangen. Voorkomt dat Mathieu handmatig moet
# resetten.
_OBSOLETE_PIN_TITLES = [
    "Nestor — Omzet & Bruto marge LTM (rolling 12 mo)",   # vervangen door 'vanaf 2025-01'
]


def init_schema() -> None:
    """Maak tabellen + indexen aan als ze nog niet bestaan. Idempotent.
    Synchroniseert sektie_kengetal_map vanuit de hardcoded Python-mapping.
    Migreert pinned_charts.series_json kolom als die nog niet bestaat.
    Ruimt obsolete pin-titels automatisch op."""
    with cache_conn() as conn:
        conn.executescript(_SCHEMA)
        _ensure_column(conn, "pinned_charts", "series_json", "TEXT")
        # Auto-cleanup van obsolete pins
        for old_title in _OBSOLETE_PIN_TITLES:
            cur = conn.execute("DELETE FROM pinned_charts WHERE titel = ?", (old_title,))
            if cur.rowcount > 0:
                log.info("Obsolete pin verwijderd: %s", old_title)
    _sync_sektie_mappings_from_code()
    _sync_klant_mapping_from_code()
    _auto_seed_klant_mapping()
    _seed_uren_extern_from_code()
    log.info("Cache schema ready at %s", cache_db_path())


def _seed_uren_extern_from_code() -> None:
    """Laad UREN_EXTERN_HARDCODED in de uren_extern tabel.

    Strategie: TRUNCATE + bulk INSERT. De tabel is bedoeld als een
    'externe waarheid' die alleen via code wijzigt — niet via UI.
    Voor weken waar Earnie data heeft, prevaleert Earnie (zie
    metrics.uren_per_week_with_extern_fallback)."""
    from .uren_extern_data import UREN_EXTERN_HARDCODED
    rows = [
        (int(j), int(w), str(s).strip().lower(), float(u))
        for (j, w, s, u) in UREN_EXTERN_HARDCODED
    ]
    with cache_conn() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM uren_extern")
            conn.executemany(
                "INSERT INTO uren_extern (jaar, week, segment, uren) VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    log.info("uren_extern: %d hardcoded rijen geladen uit uren_extern_data.py", len(rows))


def _ensure_column(conn: Any, table: str, col: str, ddl_type: str) -> None:
    """SQLite ondersteunt geen ADD COLUMN IF NOT EXISTS. We checken via PRAGMA."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl_type}")
        log.info("Migratie: kolom %s toegevoegd aan %s", col, table)


def _sync_klant_mapping_from_code() -> None:
    """Sync hardcoded KLANT_HIANT_TO_EARNIE naar de klant_mapping tabel
    met source='manual'. Manual-rijen overschrijven 'auto'-rijen niet 1:1
    om consistente data te krijgen — manual heeft voorrang."""
    from .mappings import KLANT_HIANT_TO_EARNIE
    if not KLANT_HIANT_TO_EARNIE:
        return
    with cache_conn() as conn:
        # Bepaal voor elke manual-mapping de canonical naam vanuit live data
        for hiant, earnie in KLANT_HIANT_TO_EARNIE.items():
            row = conn.execute(
                "SELECT klantnaam FROM margelijst WHERE klantreferentieid = ? "
                "AND klantnaam IS NOT NULL LIMIT 1",
                (earnie,),
            ).fetchone()
            canonical = row[0] if row else None
            conn.execute(
                "INSERT OR REPLACE INTO klant_mapping "
                "(hiant_klantref, earnie_klantref, canonical_naam, source) "
                "VALUES (?, ?, ?, 'manual')",
                (hiant, earnie, canonical),
            )


def _auto_seed_klant_mapping() -> None:
    """Auto-mapping: voor elke historische klant met identieke naam (case-
    insensitive, trim spaces) aan een live klant, voeg mapping toe — mits
    de IDs verschillen en er nog geen mapping bestaat."""
    with cache_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO klant_mapping
              (hiant_klantref, earnie_klantref, canonical_naam, source)
            SELECT h.klantreferentieid, l.klantreferentieid, l.klantnaam, 'auto'
            FROM (
                SELECT DISTINCT klantreferentieid,
                       LOWER(TRIM(klantnaam)) AS naam_norm
                FROM margelijst_historisch
                WHERE klantreferentieid IS NOT NULL
                  AND klantnaam IS NOT NULL AND klantnaam != ''
            ) h
            JOIN (
                SELECT DISTINCT klantreferentieid, klantnaam,
                       LOWER(TRIM(klantnaam)) AS naam_norm
                FROM margelijst
                WHERE klantreferentieid IS NOT NULL
                  AND klantnaam IS NOT NULL AND klantnaam != ''
            ) l ON h.naam_norm = l.naam_norm
            WHERE h.klantreferentieid != l.klantreferentieid
            """
        )


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
    # SYNC_COLUMNS = 22 kolommen die de margelijst-tabel kent (zonder 'bron',
    # die wordt door v_margelijst toegevoegd als view-kolom).
    from .prato_export import _EXPORT_SQL, SYNC_COLUMNS, _connect_long_running

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

                # Verify cols match expected SYNC_COLUMNS (= 22 kolommen
                # die de Prato-query oplevert; 'bron' is enkel view-kolom).
                expected_set = set(SYNC_COLUMNS)
                got_set = set(cols)
                if got_set != expected_set:
                    missing = expected_set - got_set
                    extra = got_set - expected_set
                    raise RuntimeError(
                        f"Kolom-mismatch — ontbrekend: {missing}, extra: {extra}"
                    )

                col_idx = [cols.index(c) for c in SYNC_COLUMNS]
                placeholders = ",".join(["?"] * len(SYNC_COLUMNS))
                insert_sql = (
                    "INSERT INTO margelijst ("
                    + ",".join(SYNC_COLUMNS)
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


# Geen single-series defaults meer — Mathieu wil alleen de 2 multi-series
# charts hieronder. /admin → "Reset pinned charts" wist alles en seed't
# alleen deze 2 opnieuw.
_DEFAULT_PINNED: list[tuple] = []


# Multi-series default-pins met dual y-axis.
# series_json: lijst van {metric, segment, label, axis}.
#   axis = 'left' | 'right'  (default 'left')
_DEFAULT_PINNED_MULTI = [
    # (titel, segment_default, chart_type, grain, period_mode, period_value,
    #  extra_options_json, position, series_json)
    (
        "Nestor — Omzet & Bruto marge per maand (sinds 2025-01)",
        "nestor", "line", "month", "since", "2025-01", None, 0,
        '[{"metric":"omzet","segment":"nestor","label":"Omzet","axis":"left"},'
        '{"metric":"marge","segment":"nestor","label":"Bruto marge","axis":"right"}]',
    ),
    (
        "Nestor — Omzet & Bruto marge LTM (rolling 12 mo, vanaf 2025-01)",
        "nestor", "line", "month", "since", "2025-01", None, 1,
        '[{"metric":"omzet_ltm","segment":"nestor","label":"Omzet LTM","axis":"left"},'
        '{"metric":"marge_ltm","segment":"nestor","label":"Bruto marge LTM","axis":"right"}]',
    ),
    (
        "Gepresteerde uren per week — Nestor Core & Smartmat",
        "nestor_core", "line", "week", "all", None, None, 2,
        '[{"metric":"uren_extern","segment":"nestor_core","label":"Nestor Core"},'
        '{"metric":"uren_extern","segment":"smartmat","label":"Smartmat"}]',
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


def find_potential_klant_duplicates(min_score: float = 0.70, max_results: int = 50) -> list[dict]:
    """Returnt klantnamen die *bijna* overeenkomen tussen HIAnt en Earnie
    maar niet exact (= geen auto-mapping). Sortert op similarity-score
    aflopend. Gebruik difflib.SequenceMatcher (standard library)."""
    from difflib import SequenceMatcher

    init_schema()
    with cache_conn() as conn:
        # Skip klanten die al gemapt zijn
        hiant_rows = conn.execute(
            """
            SELECT DISTINCT klantreferentieid, klantnaam
            FROM margelijst_historisch
            WHERE klantreferentieid IS NOT NULL
              AND klantnaam IS NOT NULL AND klantnaam != ''
              AND klantreferentieid NOT IN (SELECT hiant_klantref FROM klant_mapping)
            ORDER BY klantnaam
            """
        ).fetchall()
        live_rows = conn.execute(
            """
            SELECT DISTINCT klantreferentieid, klantnaam
            FROM margelijst
            WHERE klantreferentieid IS NOT NULL
              AND klantnaam IS NOT NULL AND klantnaam != ''
            """
        ).fetchall()

    def normalize(s: str) -> str:
        return " ".join(s.lower().split())

    candidates = []
    for h_ref, h_naam in hiant_rows:
        h_norm = normalize(h_naam)
        for l_ref, l_naam in live_rows:
            if h_ref == l_ref:
                continue
            l_norm = normalize(l_naam)
            if h_norm == l_norm:
                continue  # exact match — al via auto-seed gepakt
            ratio = SequenceMatcher(None, h_norm, l_norm).ratio()
            if ratio >= min_score:
                candidates.append({
                    "hiant_klantref": h_ref,
                    "hiant_klantnaam": h_naam,
                    "earnie_klantref": l_ref,
                    "earnie_klantnaam": l_naam,
                    "score": round(ratio, 3),
                })

    candidates.sort(key=lambda c: -c["score"])
    return candidates[:max_results]


def confirm_klant_mapping(hiant_ref: str, earnie_ref: str, canonical_naam: Optional[str] = None) -> None:
    """Bevestig een mapping vanuit /admin. Source = 'confirmed'."""
    init_schema()
    with cache_conn() as conn:
        if canonical_naam is None:
            row = conn.execute(
                "SELECT klantnaam FROM margelijst WHERE klantreferentieid = ? "
                "AND klantnaam IS NOT NULL LIMIT 1",
                (earnie_ref,),
            ).fetchone()
            canonical_naam = row[0] if row else None
        conn.execute(
            "INSERT OR REPLACE INTO klant_mapping "
            "(hiant_klantref, earnie_klantref, canonical_naam, source) "
            "VALUES (?, ?, ?, 'confirmed')",
            (hiant_ref, earnie_ref, canonical_naam),
        )
    log.info("AUDIT: klant_mapping bevestigd %s -> %s", hiant_ref, earnie_ref)


def reject_klant_mapping(hiant_ref: str, earnie_ref: str) -> None:
    """Markeer een paar als 'NIET koppelen' zodat 't niet meer in de
    verwarrende-lijst verschijnt. Gebruikt source='rejected'."""
    init_schema()
    with cache_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO klant_mapping "
            "(hiant_klantref, earnie_klantref, canonical_naam, source) "
            "VALUES (?, ?, NULL, 'rejected')",
            (hiant_ref, earnie_ref),
        )
    log.info("AUDIT: klant_mapping verworpen %s -> %s", hiant_ref, earnie_ref)


# ---------------------------------------------------------------------------
# uren_extern — extern aangeleverde gepresteerde uren per (jaar, week, segment)
# ---------------------------------------------------------------------------


def import_uren_extern(rows: list[dict]) -> dict:
    """Vervang de uren_extern tabel met de meegegeven rijen.

    Elke rij: {'jaar': int, 'week': int, 'segment': str, 'uren': float}.
    Returnt {'rows_loaded': N}.
    """
    init_schema()
    valid = []
    for r in rows:
        try:
            jaar = int(r["jaar"])
            week = int(r["week"])
            segment = str(r["segment"]).strip().lower()
            uren = float(r["uren"])
        except (KeyError, ValueError, TypeError):
            continue
        if not segment or jaar < 2000 or jaar > 2100 or week < 1 or week > 53:
            continue
        valid.append((jaar, week, segment, uren))

    with cache_conn() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM uren_extern")
            conn.executemany(
                "INSERT INTO uren_extern (jaar, week, segment, uren) VALUES (?, ?, ?, ?)",
                valid,
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    log.info("uren_extern: %d rijen geladen", len(valid))
    return {"rows_loaded": len(valid)}


def get_uren_extern_summary() -> dict:
    """Statistieken voor /admin: aantal rijen, segmenten, periode-range."""
    init_schema()
    with cache_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM uren_extern").fetchone()[0]
        segs = [r[0] for r in conn.execute(
            "SELECT DISTINCT segment FROM uren_extern ORDER BY segment"
        ).fetchall()]
        date_range = conn.execute(
            "SELECT MIN(jaar*100+week), MAX(jaar*100+week) FROM uren_extern"
        ).fetchone()
    return {
        "rows": n,
        "segments": segs,
        "periode_van": date_range[0] if date_range and date_range[0] else None,
        "periode_tot": date_range[1] if date_range and date_range[1] else None,
    }


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
