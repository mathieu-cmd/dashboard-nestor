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

CREATE TABLE IF NOT EXISTS sync_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    rows_loaded INTEGER,
    duration_ms INTEGER,
    error TEXT
);
"""


def init_schema() -> None:
    """Maak tabellen + indexen aan als ze nog niet bestaan. Idempotent."""
    with cache_conn() as conn:
        conn.executescript(_SCHEMA)
    log.info("Cache schema ready at %s", cache_db_path())


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
    sql = f"SELECT {cols_csv} FROM margelijst"
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
    """Aantal rijen in de margelijst-cache."""
    init_schema()
    with cache_conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM margelijst").fetchone()
        return row[0] if row else 0
