"""Importeer historische margelijst-CSV (HIAnt-formaat) naar SQLite.

De bron-CSV bestaat uit twee delen geplakt met verschillende header-stijlen:
  Deel 1: CamelCase NL  (Maand, Wgnr, Naam, Sektie, ...) — 2023-01 → 2025-12
  Deel 2: lowercase     (periode, wgnr, wnnaam, sektie, ...) — 2026-01 → 2026-03

Beide delen hebben dezelfde 25 kolommen in dezelfde volgorde. We normaliseren
op kolom-positie (niet op naam) en bewaren alles in margelijst_historisch.

Format-conventies in de bron-CSV:
  - Decimaalkomma in dubbele quotes: "849,81"
  - Geen quotes voor integers (0, 39)
  - Lege rijen tussen de twee delen
  - Tussen-headers ("periode,wgnr,...") komen voor in het midden van het bestand

Mapping (kolompositie -> SQLite kolom):
  0  Maand/periode      -> jaar + maand (split)
  1  Wgnr/wgnr          -> vestigingseenheidreferentieid (TEXT)
  2  WgnrOmzet          -> wgnr_omzet (altijd -1, betekenis onbekend)
  3  Klnr               -> klantreferentieid (TEXT)
  4  Naam (klant)       -> klantnaam
  5  wnnr               -> persoonreferentieid (TEXT)
  6  Naam (persoon)     -> familienaam (volledige naam, voornaam blijft '')
  7  Sektie             -> sektie_origineel
  8  Type               -> type_origineel (INTEGER)
  9  Jobstudent         -> jobstudent_flag (INTEGER)
  10 Kost               -> loonkost
  11 Bruto              -> bruto_loon
  12 AutoProv/prov      -> provisies
  13 RSZ_SV             -> rszwerkgeversbijdragen
  14 RSZ_Andere         -> rsz_andere
  15 BVVerm/bvverm      -> bvvrijstellingen
  16 TotaleKost         -> kost
  17 Totale omzet       -> omzet_gefactureerd
  18 Marge              -> marge
  19 Marge%             -> margeprocent
  20 UP Kost            -> up_kost (= aantal uur, UP-categorie)
  21 UP Omzet           -> up_omzet
  22 OU Kost            -> ou_kost (= aantal uur, OU-categorie)
  23 OU Omzet           -> ou_omzet
  24 Totale uren        -> verloonde_uren (in historisch = totaal)

  Afgeleid:
    gepresteerde_uren  = up_kost + ou_kost
    margeperuur        = marge / verloonde_uren  (NULL bij 0 uren)
    kwartaal           = (maand-1)//3 + 1
"""

from __future__ import annotations

import csv
import io
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Iterator

from .cache import cache_conn, init_schema

log = logging.getLogger("dashboard-nestor.import")


def _to_float(value: str | None) -> float | None:
    """Parse Belgisch decimaal-formaat ('849,81' of '0') naar float."""
    if value is None:
        return None
    s = value.strip().strip('"')
    if not s:
        return None
    # Komma -> punt voor float-parsing
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    s = value.strip().strip('"')
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        # Probeer via float (bv. "1,0")
        f = _to_float(value)
        if f is not None:
            return int(f)
        return None


def _to_str(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip().strip('"')
    return s if s else None


def _is_data_row(cols: list[str]) -> bool:
    """True als deze rij echte data is (= kolom 0 ziet eruit als YYYYMM)."""
    if len(cols) < 25:
        return False
    first = cols[0].strip().strip('"')
    return bool(re.fullmatch(r"\d{6}", first))


def _is_header_row(cols: list[str]) -> bool:
    """True als deze rij een header is (kolom 0 = 'Maand' of 'periode')."""
    if not cols:
        return False
    first = cols[0].strip().strip('"').lower()
    return first in {"maand", "periode"}


def parse_csv_bytes(raw: bytes) -> Iterator[dict[str, Any]]:
    """Yield één dict per data-rij uit het CSV-bestand.

    Strip BOM, herken header-rijen + lege rijen + tussen-headers,
    yield genormaliseerde dicts klaar voor INSERT in margelijst_historisch.
    """
    # Decode + strip BOM
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    for cols in reader:
        if not _is_data_row(cols):
            continue
        try:
            yield _row_to_dict(cols)
        except Exception as e:  # noqa: BLE001
            log.warning("Skip ongeldige rij: %s — %r", e, cols[:5])


def _row_to_dict(cols: list[str]) -> dict[str, Any]:
    """Map een rij van 25 kolomwaarden naar een dict voor SQLite-insert."""
    periode_str = cols[0].strip().strip('"')
    jaar = int(periode_str[:4])
    maand = int(periode_str[4:6])
    kwartaal = (maand - 1) // 3 + 1

    loonkost = _to_float(cols[10])
    bruto = _to_float(cols[11])
    autoprov = _to_float(cols[12])
    rsz_sv = _to_float(cols[13])
    rsz_andere = _to_float(cols[14])
    bvverm = _to_float(cols[15])
    totale_kost = _to_float(cols[16])
    totale_omzet = _to_float(cols[17])
    marge = _to_float(cols[18])
    margeprocent = _to_float(cols[19])
    up_kost = _to_float(cols[20])
    up_omzet = _to_float(cols[21])
    ou_kost = _to_float(cols[22])
    ou_omzet = _to_float(cols[23])
    totale_uren = _to_float(cols[24])

    gepresteerde_uren = (up_kost or 0.0) + (ou_kost or 0.0)
    margeperuur = (
        round(marge / totale_uren, 2)
        if marge is not None and totale_uren and totale_uren != 0
        else None
    )

    return {
        "jaar": jaar,
        "kwartaal": kwartaal,
        "maand": maand,
        "week": None,
        "vestigingseenheidreferentieid": _to_str(cols[1]),
        "klantreferentieid": _to_str(cols[3]),
        "klantnaam": _to_str(cols[4]),
        "persoonreferentieid": _to_str(cols[5]),
        "familienaam": _to_str(cols[6]),  # volledige naam, voornaam blijft None
        "voornaam": None,
        "loonkost": loonkost,
        "werkuitkering": None,
        "bvvrijstellingen": bvverm,
        "rszwerkgeversbijdragen": rsz_sv,
        "rszverminderingen": None,
        "provisies": autoprov,
        "omzet_gefactureerd": totale_omzet,
        "omzet_te_factureren": None,
        "kost": totale_kost,
        "verloonde_uren": totale_uren,
        "marge": marge,
        "margeperuur": margeperuur,
        # Historische extra's
        "bruto_loon": bruto,
        "rsz_andere": rsz_andere,
        "margeprocent": margeprocent,
        "sektie_origineel": _to_str(cols[7]),
        "type_origineel": _to_int(cols[8]),
        "jobstudent_flag": _to_int(cols[9]),
        "up_kost": up_kost,
        "up_omzet": up_omzet,
        "ou_kost": ou_kost,
        "ou_omzet": ou_omzet,
        "gepresteerde_uren": gepresteerde_uren,
        "wgnr_omzet": _to_int(cols[2]),
    }


_INSERT_COLS = [
    "jaar", "kwartaal", "maand", "week",
    "vestigingseenheidreferentieid",
    "klantreferentieid", "klantnaam",
    "persoonreferentieid", "familienaam", "voornaam",
    "loonkost", "werkuitkering", "bvvrijstellingen",
    "rszwerkgeversbijdragen", "rszverminderingen", "provisies",
    "omzet_gefactureerd", "omzet_te_factureren",
    "kost", "verloonde_uren", "marge", "margeperuur",
    "bruto_loon", "rsz_andere", "margeprocent",
    "sektie_origineel", "type_origineel", "jobstudent_flag",
    "up_kost", "up_omzet", "ou_kost", "ou_omzet",
    "gepresteerde_uren", "wgnr_omzet",
]


def import_csv_to_historisch(raw: bytes, filename: str = "") -> dict[str, Any]:
    """Importeer een HIAnt-CSV in margelijst_historisch.

    Idempotent gedrag: TRUNCATE margelijst_historisch eerst, dan INSERT alles.
    Mathieu's intentie: historisch is immutable, dus elke import overschrijft
    het bestaande (geen merge / append-logica).

    Returnt {'rows_loaded': N, 'rows_skipped': M, 'duration_ms': X}.
    """
    init_schema()
    started = time.monotonic()
    started_iso = datetime.now(timezone.utc).isoformat()
    rows_loaded = 0
    rows_skipped = 0

    with cache_conn() as conn:
        cur = conn.execute(
            "INSERT INTO import_meta (bron, started_at, status, filename) VALUES (?, ?, 'running', ?)",
            ("historisch", started_iso, filename),
        )
        import_id = cur.lastrowid

    placeholders = ",".join(["?"] * len(_INSERT_COLS))
    insert_sql = f"INSERT INTO margelijst_historisch ({','.join(_INSERT_COLS)}) VALUES ({placeholders})"

    try:
        with cache_conn() as conn:
            conn.execute("BEGIN")
            try:
                conn.execute("DELETE FROM margelijst_historisch")
                batch: list[tuple] = []
                BATCH_SIZE = 5000
                for row_dict in parse_csv_bytes(raw):
                    row = tuple(row_dict[k] for k in _INSERT_COLS)
                    batch.append(row)
                    if len(batch) >= BATCH_SIZE:
                        conn.executemany(insert_sql, batch)
                        rows_loaded += len(batch)
                        batch = []
                        log.info("import_historisch: %d rijen", rows_loaded)
                if batch:
                    conn.executemany(insert_sql, batch)
                    rows_loaded += len(batch)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        duration_ms = int((time.monotonic() - started) * 1000)
        ended_iso = datetime.now(timezone.utc).isoformat()
        with cache_conn() as conn:
            conn.execute(
                "UPDATE import_meta SET ended_at=?, status='ok', rows_loaded=?, rows_skipped=? WHERE id=?",
                (ended_iso, rows_loaded, rows_skipped, import_id),
            )
        log.info("import_historisch klaar: %d rijen, %d ms", rows_loaded, duration_ms)
        return {
            "status": "ok",
            "rows_loaded": rows_loaded,
            "rows_skipped": rows_skipped,
            "duration_ms": duration_ms,
        }

    except Exception as e:  # noqa: BLE001
        log.exception("import_historisch gefaald")
        duration_ms = int((time.monotonic() - started) * 1000)
        ended_iso = datetime.now(timezone.utc).isoformat()
        with cache_conn() as conn:
            conn.execute(
                "UPDATE import_meta SET ended_at=?, status='failed', error=? WHERE id=?",
                (ended_iso, str(e)[:500], import_id),
            )
        return {"status": "failed", "error": str(e)[:500], "duration_ms": duration_ms}


def get_historisch_summary() -> dict[str, Any]:
    """Korte info: aantal rijen, datum-range, sektie-codes."""
    init_schema()
    with cache_conn() as conn:
        row_count = conn.execute("SELECT COUNT(*) FROM margelijst_historisch").fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(jaar*100+maand), MAX(jaar*100+maand) FROM margelijst_historisch"
        ).fetchone()
        sekties = conn.execute(
            "SELECT sektie_origineel, COUNT(*) c FROM margelijst_historisch "
            "GROUP BY sektie_origineel ORDER BY c DESC LIMIT 20"
        ).fetchall()
        mapped = conn.execute("SELECT COUNT(*) FROM sektie_kengetal_map").fetchone()[0]
        last_import = conn.execute(
            "SELECT * FROM import_meta WHERE bron='historisch' ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def _periode(yymm):
        if not yymm:
            return None
        return f"{yymm // 100}-{yymm % 100:02d}"

    return {
        "rows": row_count,
        "periode_van": _periode(date_range[0]) if date_range else None,
        "periode_tot": _periode(date_range[1]) if date_range else None,
        "sekties_top20": [{"code": s[0], "count": s[1]} for s in sekties],
        "sekties_mapped": mapped,
        "last_import": dict(last_import) if last_import else None,
    }


# ---------------------------------------------------------------------------
# Sektie-mapping helpers
# ---------------------------------------------------------------------------


def set_sektie_mapping(mappings: list[dict]) -> int:
    """Bulk-upsert van sektie -> werknemerskengetal mapping.

    Input: [{'sektie_origineel': '7115', 'werknemerskengetal': '015',
             'omschrijving': 'Arbeider'}].
    Returnt het aantal geüpdate rijen (insert + update samen).
    """
    init_schema()
    if not mappings:
        return 0
    with cache_conn() as conn:
        conn.execute("BEGIN")
        try:
            for m in mappings:
                if not m.get("sektie_origineel") or not m.get("werknemerskengetal"):
                    continue
                conn.execute(
                    """
                    INSERT INTO sektie_kengetal_map (sektie_origineel, werknemerskengetal, omschrijving)
                    VALUES (?, ?, ?)
                    ON CONFLICT(sektie_origineel) DO UPDATE SET
                        werknemerskengetal = excluded.werknemerskengetal,
                        omschrijving = excluded.omschrijving
                    """,
                    (m["sektie_origineel"], m["werknemerskengetal"], m.get("omschrijving")),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return len(mappings)


def get_sektie_mappings() -> list[dict]:
    """Returnt alle bestaande mappings."""
    init_schema()
    with cache_conn() as conn:
        rows = conn.execute(
            "SELECT sektie_origineel, werknemerskengetal, omschrijving "
            "FROM sektie_kengetal_map ORDER BY sektie_origineel"
        ).fetchall()
    return [dict(r) for r in rows]
