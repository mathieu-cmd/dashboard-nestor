"""Prato reporting — read-only queries op de Earnie views.

Gebruikt de `reporter_nestor_nestor` user (read-only) op de Prato Postgres.
Toegang werkt enkel vanaf gewhiteliste IPs (de 3 Railway static outbound IPs).

Belangrijke design-keuzes:
- Eén verbinding per query (`with _connect() as conn`), geen pool. Reden:
  de queries zijn nightly batch (1× per dag), niet hoog-frequent. Pooling
  zou hier vooral risico op stale connections introduceren.
- Sessie wordt expliciet READ ONLY gezet en een statement_timeout opgelegd —
  fail-safe tegen runaway-queries op trage views.
- Wachtwoord komt **enkel** uit settings (= env var). Nooit als argument,
  nooit gelogd, nooit in stack-traces. We loggen alleen host + user.

Prato's eigen documentatie waarschuwt dat queries op deze views traag
kunnen zijn ("nuttige queries" sectie). De aanbevolen workflow voor
production is: data van de views overzetten naar een eigen DWH-tabel en
daarop rapporteren. In onze opzet doen we dat door het resultaat van
fetch_margelijst() in onze eigen SQLite te cachen.

De margelijst-query zelf komt rechtstreeks uit de Prato-documentatie en
levert deze kolommen:
  werkgeverreferentieid, vestigingseenheidreferentieid, werknemerskengetal,
  werkgeverscategorie, persoonreferentieid, voornaam, familienaam,
  jaar, kwartaal, maand, week, datum,
  loonkost, werkuitkering, bvvrijstellingen, rszwerkgeversbijdragen,
  rszverminderingen, provisies, omzet, kost, verloonde_uren,
  marge, margeperuur, margeprocent.

Wat de query NIET levert (en wat we later via aparte joins moeten halen
uit het PratoFlex-schema, mogelijk in een aparte DB):
  vestigingseenheidnaam, omzetkantoorreferentieid, omzetkantoornaam,
  klantkantoorreferentieid, klantkantoornaam, klantreferentieid,
  klantnaam, klantondernemingsnummer.

Die joins worden in een latere iteratie toegevoegd zodra Mathieu bevestigd
heeft of het PratoFlex-schema in dezelfde Postgres zit of in een aparte
SQL Server.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date
from typing import Any, Iterator, Optional

from .config import settings

log = logging.getLogger("invoice-bundler.prato")


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


class PratoNotConfigured(RuntimeError):
    """Wordt gegooid wanneer iemand een Prato-query probeert te doen
    zonder dat de env-vars gezet zijn. Bedoeld om duidelijke foutmelding
    te geven i.p.v. een cryptische psycopg-OperationalError."""


def is_configured() -> bool:
    """True als alle vereiste Prato-env-vars gezet zijn."""
    return bool(
        settings.PRATO_DB_HOST
        and settings.PRATO_DB_USER
        and settings.PRATO_DB_PASSWORD
        and settings.PRATO_DB_NAME
    )


def _require_configured() -> None:
    if not is_configured():
        raise PratoNotConfigured(
            "Prato DB-credentials ontbreken. Zet PRATO_DB_HOST, PRATO_DB_USER, "
            "PRATO_DB_PASSWORD en PRATO_DB_NAME in Railway → Variables."
        )


@contextmanager
def _connect() -> Iterator[Any]:
    """Yield een psycopg-verbinding met read-only sessie + statement timeout.

    Imports gebeuren binnen de functie zodat de hele app blijft draaien
    als psycopg nog niet geïnstalleerd is (bv. tijdens een gefaalde build).
    """
    _require_configured()
    import psycopg  # local import — zie docstring

    # Connection string: gebruik keyword-args ipv DSN-string zodat het
    # wachtwoord nooit in een string-rep van conn-info belandt.
    log.info(
        "Prato connect — host=%s db=%s user=%s sslmode=%s",
        settings.PRATO_DB_HOST,
        settings.PRATO_DB_NAME,
        settings.PRATO_DB_USER,
        settings.PRATO_DB_SSLMODE,
    )
    conn = psycopg.connect(
        host=settings.PRATO_DB_HOST,
        port=settings.PRATO_DB_PORT,
        user=settings.PRATO_DB_USER,
        password=settings.PRATO_DB_PASSWORD,
        dbname=settings.PRATO_DB_NAME,
        sslmode=settings.PRATO_DB_SSLMODE,
        connect_timeout=15,
        application_name="mathieus-agent-reporter",
    )
    try:
        # Defense-in-depth: ook al heeft reporter_nestor_nestor enkel SELECT,
        # we forceren de sessie zelf read-only en zetten een timeout.
        #
        # Opmerking: PostgreSQL's SET-statement ondersteunt GEEN parameter-
        # binding ($1) — daarom interpoleren we de int rechtstreeks in de
        # SQL-string. Veilig omdat de waarde via int() uit een env-var komt
        # (zie config.py), dus geen user input.
        timeout_ms = int(settings.PRATO_DB_STATEMENT_TIMEOUT_MS)
        with conn.cursor() as cur:
            cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            cur.execute(f"SET statement_timeout = {timeout_ms}")
        yield conn
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001 — best-effort close
            pass


# ---------------------------------------------------------------------------
# Test / health
# ---------------------------------------------------------------------------


def test_connection() -> dict[str, Any]:
    """Health-check. Doet SELECT 1 + version() + lijst van zichtbare schema's.

    Bedoeld om snel te valideren of:
    - de IP-whitelist door Prato is opengezet,
    - credentials kloppen,
    - SSL werkt,
    - en welke schema's we kunnen lezen.

    Gooit een uitzondering als één van deze stappen faalt. Caller (router)
    vertaalt dat naar een 5xx response met de foutboodschap (geredacteerd —
    geen wachtwoord lekken).
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()

            cur.execute("SELECT version()")
            (version,) = cur.fetchone()

            cur.execute("SELECT current_user, current_database()")
            current_user, current_database = cur.fetchone()

            # Welke schema's mogen we 'zien'? (USAGE-grant)
            cur.execute(
                """
                SELECT nspname
                FROM pg_namespace
                WHERE has_schema_privilege(current_user, nspname, 'USAGE')
                  AND nspname NOT IN ('pg_catalog', 'information_schema')
                  AND nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
                ORDER BY nspname
                """
            )
            schemas = [row[0] for row in cur.fetchall()]

    return {
        "ok": True,
        "version": version,
        "current_user": current_user,
        "current_database": current_database,
        "visible_schemas": schemas,
    }


# ---------------------------------------------------------------------------
# Margelijst-query (uit Prato documentatie pagina 50-54)
# ---------------------------------------------------------------------------

# Letterlijk overgenomen uit de PDF "Rapportering op Earnie data — info views",
# hoofdstuk "Nuttige queries / Margelijsten". Niet aanpassen tenzij Prato
# zelf de view-schema's wijzigt — anders verlies je backwards compatibility
# met hun documentatie.
#
# De query gebruikt views uit 5 schema's:
#   loonbepaling.{brutoloongegevens, belastbareloongegevens,
#                  nettoloongegevens, werkuitkering, cheques,
#                  arbeidstijdgegevens, arbeidstijdgegeventypes}
#   bv.vrijstellingsbedragen
#   dmfa_reporting.{werkgeversbijdragen, verminderingen}
#   boekhouding.provisies
#   facturatie.gefactureerdebedragen
#   loonbetaling.{contracten, personen}
_MARGELIJST_SQL = """
WITH uitgebreidegegevens AS (
    WITH gegevens AS (
        SELECT brutoloongegevens.contractreferentieid,
               brutoloongegevens.datum,
               brutoloongegevens.bedrag AS loonkost,
               0 AS werkuitkering,
               0 AS bvvrijstellingen,
               0 AS rszwerkgeversbijdragen,
               0 AS rszverminderingen,
               0 AS provisies,
               0 AS omzet,
               0 AS verloonde_uren
        FROM loonbepaling.brutoloongegevens
        UNION ALL
        SELECT belastbareloongegevens.contractreferentieid,
               belastbareloongegevens.datum,
               belastbareloongegevens.bedrag AS loonkost,
               0, 0, 0, 0, 0, 0, 0
        FROM loonbepaling.belastbareloongegevens
        UNION ALL
        SELECT nettoloongegevens.contractreferentieid,
               nettoloongegevens.datum,
               nettoloongegevens.bedrag AS loonkost,
               0, 0, 0, 0, 0, 0, 0
        FROM loonbepaling.nettoloongegevens
        WHERE nettoloongegevens.code <> ALL (ARRAY[
            'Maaltijdcheque werknemersbijdrage'::text,
            'Inhouding Kledij Of Materiaal'::text,
            'Terugbetaling Inhouding Kledij Of Materiaal'::text
        ])
        UNION ALL
        SELECT werkuitkering.contractreferentieid,
               werkuitkering.datum,
               0, werkuitkering.bedrag AS werkuitkering,
               0, 0, 0, 0, 0, 0
        FROM loonbepaling.werkuitkering
        UNION ALL
        SELECT cheques.contractreferentieid,
               cheques.datum,
               cheques.werkgeversbijdrage AS loonkost,
               0, 0, 0, 0, 0, 0, 0
        FROM loonbepaling.cheques
        UNION ALL
        SELECT vrijstellingsbedragen.contractreferentieid,
               vrijstellingsbedragen.datum,
               0, 0,
               vrijstellingsbedragen.bedrag AS bvvrijstellingen,
               0, 0, 0, 0, 0
        FROM bv.vrijstellingsbedragen
        UNION ALL
        SELECT werkgeversbijdragen.contractreferentieid,
               werkgeversbijdragen.datum,
               0, 0, 0,
               werkgeversbijdragen.bedrag AS rszwerkgeversbijdragen,
               0, 0, 0, 0
        FROM dmfa_reporting.werkgeversbijdragen
        UNION ALL
        SELECT verminderingen.contractreferentieid,
               verminderingen.datum,
               0, 0, 0, 0,
               verminderingen.bedrag AS rszverminderingen,
               0, 0, 0
        FROM dmfa_reporting.verminderingen
        UNION ALL
        SELECT provisies.contractreferentieid,
               provisies.datum,
               0, 0, 0, 0, 0,
               provisies.bedrag AS provisies,
               0, 0
        FROM boekhouding.provisies
        UNION ALL
        SELECT gefactureerdebedragen.contractreferentieid,
               gefactureerdebedragen.prestatiedatum AS datum,
               0, 0, 0, 0, 0, 0,
               gefactureerdebedragen.bedrag AS omzet,
               0
        FROM facturatie.gefactureerdebedragen
        UNION ALL
        SELECT arbeidstijdgegeven.contractreferentieid,
               arbeidstijdgegeven.datum,
               0, 0, 0, 0, 0, 0, 0,
               CASE
                   WHEN arbeidstijdgegeventypes.eigenschappen IS NOT NULL
                   THEN arbeidstijdgegeven.aantal
                   ELSE 0::numeric
               END AS verloonde_uren
        FROM loonbepaling.arbeidstijdgegevens arbeidstijdgegeven
        LEFT JOIN loonbepaling.arbeidstijdgegeventypes
               ON arbeidstijdgegeventypes.code = arbeidstijdgegeven.code
              AND arbeidstijdgegeven.werknemerskengetal = arbeidstijdgegeventypes.werknemerkengetal
              AND arbeidstijdgegeven.datum >= arbeidstijdgegeventypes.geldigvan
              AND arbeidstijdgegeven.datum <= arbeidstijdgegeventypes.geldigtot
              AND arbeidstijdgegeventypes.eigenschappen LIKE '%%Kost Margelijst%%'
    ),
    contracten AS (
        SELECT * FROM loonbetaling.contracten c1
        WHERE NOT EXISTS (
            SELECT 1 FROM loonbetaling.contracten c2
            WHERE c1.contractreferentieid = c2.contractreferentieid
              AND c2.lastmodified >= c1.lastmodified
              AND c2.aanvangsdatum > c1.aanvangsdatum
        )
    ),
    personen AS (
        SELECT * FROM loonbetaling.personen p1
        WHERE NOT EXISTS (
            SELECT 1 FROM loonbetaling.personen p2
            WHERE p1.referentieid = p2.referentieid
              AND p2.lastmodified >= p1.lastmodified
              AND p2.aanvangsdatum > p1.aanvangsdatum
        )
    )
    SELECT contracten.werkgeverreferentieid                     AS werkgeverreferentieid,
           contracten.vestigingseenheidreferentieid             AS vestigingseenheidreferentieid,
           contracten.werknemerskengetal                        AS werknemerskengetal,
           contracten.werkgeverscategorie                       AS werkgeverscategorie,
           contracten.persoonreferentieid                       AS persoonreferentieid,
           personen.voornaam                                    AS voornaam,
           personen.familienaam                                 AS familienaam,
           date_part('year'::text,    gegevens.datum)           AS jaar,
           date_part('quarter'::text, gegevens.datum)           AS kwartaal,
           date_part('month'::text,   gegevens.datum)           AS maand,
           date_part('week'::text,    gegevens.datum)           AS week,
           gegevens.datum                                       AS datum,
           gegevens.loonkost,
           gegevens.werkuitkering,
           gegevens.bvvrijstellingen,
           gegevens.rszwerkgeversbijdragen,
           gegevens.rszverminderingen,
           gegevens.provisies,
           gegevens.omzet,
           gegevens.verloonde_uren
    FROM gegevens
    LEFT JOIN contracten ON contracten.contractreferentieid = gegevens.contractreferentieid
    LEFT JOIN personen   ON personen.referentieid           = contracten.persoonreferentieid
    /* DATE_FILTER_PLACEHOLDER */
)
SELECT NOW() AS last_refresh,
       uitgebreidegegevens.werkgeverreferentieid,
       uitgebreidegegevens.vestigingseenheidreferentieid,
       uitgebreidegegevens.werknemerskengetal,
       uitgebreidegegevens.werkgeverscategorie,
       uitgebreidegegevens.persoonreferentieid,
       uitgebreidegegevens.voornaam,
       uitgebreidegegevens.familienaam,
       uitgebreidegegevens.jaar,
       uitgebreidegegevens.kwartaal,
       uitgebreidegegevens.maand,
       uitgebreidegegevens.week,
       uitgebreidegegevens.datum,
       SUM(uitgebreidegegevens.loonkost)              AS loonkost,
       SUM(uitgebreidegegevens.werkuitkering)         AS werkuitkering,
       SUM(uitgebreidegegevens.bvvrijstellingen)      AS bvvrijstellingen,
       SUM(uitgebreidegegevens.rszwerkgeversbijdragen) AS rszwerkgeversbijdragen,
       SUM(uitgebreidegegevens.rszverminderingen)     AS rszverminderingen,
       SUM(uitgebreidegegevens.provisies)             AS provisies,
       SUM(uitgebreidegegevens.omzet)                 AS omzet,
       (
           SUM(uitgebreidegegevens.loonkost)
         - SUM(uitgebreidegegevens.werkuitkering)
         - SUM(uitgebreidegegevens.bvvrijstellingen)
         + SUM(uitgebreidegegevens.rszwerkgeversbijdragen)
         - SUM(uitgebreidegegevens.rszverminderingen)
         + SUM(uitgebreidegegevens.provisies)
       ) AS kost,
       SUM(uitgebreidegegevens.verloonde_uren) AS verloonde_uren,
       (
           SUM(uitgebreidegegevens.omzet)
         - (
             SUM(uitgebreidegegevens.loonkost)
           - SUM(uitgebreidegegevens.werkuitkering)
           - SUM(uitgebreidegegevens.bvvrijstellingen)
           + SUM(uitgebreidegegevens.rszwerkgeversbijdragen)
           - SUM(uitgebreidegegevens.rszverminderingen)
           + SUM(uitgebreidegegevens.provisies)
         )
       ) AS marge,
       CASE
           WHEN SUM(uitgebreidegegevens.verloonde_uren) = 0::numeric THEN NULL::numeric
           ELSE ROUND(
               (SUM(uitgebreidegegevens.omzet)
                - (
                    SUM(uitgebreidegegevens.loonkost)
                  - SUM(uitgebreidegegevens.werkuitkering)
                  - SUM(uitgebreidegegevens.bvvrijstellingen)
                  + SUM(uitgebreidegegevens.rszwerkgeversbijdragen)
                  - SUM(uitgebreidegegevens.rszverminderingen)
                  + SUM(uitgebreidegegevens.provisies)
                )
               ) / SUM(uitgebreidegegevens.verloonde_uren),
               2
           )
       END AS margeperuur,
       CASE
           WHEN SUM(uitgebreidegegevens.omzet) = 0::numeric THEN NULL::numeric
           ELSE ROUND(
               (SUM(uitgebreidegegevens.omzet)
                - (
                    SUM(uitgebreidegegevens.loonkost)
                  - SUM(uitgebreidegegevens.werkuitkering)
                  - SUM(uitgebreidegegevens.bvvrijstellingen)
                  + SUM(uitgebreidegegevens.rszwerkgeversbijdragen)
                  - SUM(uitgebreidegegevens.rszverminderingen)
                  + SUM(uitgebreidegegevens.provisies)
                )
               ) / SUM(uitgebreidegegevens.omzet) * 100::numeric,
               2
           )
       END AS margeprocent
FROM uitgebreidegegevens
GROUP BY uitgebreidegegevens.werkgeverreferentieid,
         uitgebreidegegevens.vestigingseenheidreferentieid,
         uitgebreidegegevens.werknemerskengetal,
         uitgebreidegegevens.werkgeverscategorie,
         uitgebreidegegevens.persoonreferentieid,
         uitgebreidegegevens.voornaam,
         uitgebreidegegevens.familienaam,
         uitgebreidegegevens.jaar,
         uitgebreidegegevens.kwartaal,
         uitgebreidegegevens.maand,
         uitgebreidegegevens.week,
         uitgebreidegegevens.datum
ORDER BY persoonreferentieid, werknemerskengetal, datum
"""


# Kolomvolgorde van de query — handig voor CSV/Sheets export.
MARGELIJST_COLUMNS: tuple[str, ...] = (
    "last_refresh",
    "werkgeverreferentieid",
    "vestigingseenheidreferentieid",
    "werknemerskengetal",
    "werkgeverscategorie",
    "persoonreferentieid",
    "voornaam",
    "familienaam",
    "jaar",
    "kwartaal",
    "maand",
    "week",
    "datum",
    "loonkost",
    "werkuitkering",
    "bvvrijstellingen",
    "rszwerkgeversbijdragen",
    "rszverminderingen",
    "provisies",
    "omzet",
    "kost",
    "verloonde_uren",
    "marge",
    "margeperuur",
    "margeprocent",
)


def fetch_margelijst(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Haal de margelijst op uit Prato.

    Args:
        date_from: optioneel — filter op gegevens.datum >= date_from
        date_to:   optioneel — filter op gegevens.datum <= date_to
        limit:     optioneel — maximum aantal rijen (handig voor smoke-test)

    Returns:
        Lijst van dicts, key = kolomnaam (zie MARGELIJST_COLUMNS).

    Raises:
        PratoNotConfigured: als env-vars ontbreken
        psycopg.Error:      bij DB-fouten (timeout, geen toegang, …)
    """
    # Datumfilter wordt veilig geïnjecteerd in de inner CTE.
    sql = _MARGELIJST_SQL
    params: list[Any] = []
    where_parts: list[str] = []
    if date_from is not None:
        where_parts.append("gegevens.datum >= %s")
        params.append(date_from)
    if date_to is not None:
        where_parts.append("gegevens.datum <= %s")
        params.append(date_to)
    if where_parts:
        sql = sql.replace(
            "/* DATE_FILTER_PLACEHOLDER */",
            "WHERE " + " AND ".join(where_parts),
        )
    if limit is not None:
        # Veilig — limit komt uit code, niet uit user-input. Maar we cast'en
        # toch naar int als defense-in-depth.
        sql = sql + f"\nLIMIT {int(limit)}"

    log.info(
        "Prato fetch_margelijst — date_from=%s date_to=%s limit=%s",
        date_from, date_to, limit,
    )
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchall()

    log.info("Prato fetch_margelijst — %d rijen opgehaald", len(rows))
    return [dict(zip(cols, row)) for row in rows]
