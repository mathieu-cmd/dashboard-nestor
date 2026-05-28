"""Bedrijfsdimensies — Nestor / Nestor Core / Smartmat / Martha / VAB.

Elk segment levert een SQL WHERE-clause + bijhorende params voor de
SQLite-cache. Definities zijn op één plek zodat metrics/dashboards/explorer
allemaal dezelfde interpretatie hebben.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Bedrijfsregels — pas aan als de definities wijzigen
# ---------------------------------------------------------------------------

# Vestiging die voor Martha-tak staat.
MARTHA_VESTIGING_REF: str = "12703"

# Nestor Core vestigingen (kantoren waar de Core-business draait).
# Definitie: kantoren 12701, 12702, 12704, 12705 — exclusief Smartmat, exclusief VAB.
# 12703 = Martha (apart segment).
NESTOR_CORE_VESTIGINGEN: tuple[str, ...] = ("12701", "12702", "12704", "12705")

# Smartmat-klant (bevestigd via data: klantnaam='Smartmat' bij klantreferentieid=464).
SMARTMAT_KLANTREF: str = "464"

# VAB identificeren via naam-pattern (case-insensitive LIKE).
# Gebruik %term% formaat — LOWER(klantnaam) LIKE LOWER(?) check.
VAB_KLANTNAAM_PATTERN: str = "%vab%"


# ---------------------------------------------------------------------------
# Segment-definities
# ---------------------------------------------------------------------------


SEGMENTS: dict[str, dict] = {
    "all": {
        "label": "Alles",
        "where": "1=1",
        "params": [],
    },
    "nestor": {
        "label": "Nestor",
        "where": "vestigingseenheidreferentieid != ?",
        "params": [MARTHA_VESTIGING_REF],
    },
    "martha": {
        "label": "Martha",
        "where": "vestigingseenheidreferentieid = ?",
        "params": [MARTHA_VESTIGING_REF],
    },
    "smartmat": {
        "label": "Smartmat",
        "where": "klantreferentieid = ?",
        "params": [SMARTMAT_KLANTREF],
    },
    "vab": {
        "label": "VAB",
        "where": "LOWER(COALESCE(klantnaam,'')) LIKE ?",
        "params": [VAB_KLANTNAAM_PATTERN],
    },
    "nestor_core": {
        "label": "Nestor Core",
        # Nestor Core = vestiging IN (12701, 12702, 12704, 12705)
        #   MINUS Smartmat (klantref) MINUS VAB (naam-LIKE)
        # NB: Martha (12703) valt automatisch weg want zit niet in de IN-lijst.
        "where": (
            "vestigingseenheidreferentieid IN ("
            + ",".join(["?"] * len(NESTOR_CORE_VESTIGINGEN))
            + ") "
            "AND (klantreferentieid IS NULL OR klantreferentieid != ?) "
            "AND LOWER(COALESCE(klantnaam,'')) NOT LIKE ?"
        ),
        "params": [*NESTOR_CORE_VESTIGINGEN, SMARTMAT_KLANTREF, VAB_KLANTNAAM_PATTERN],
    },
}


def segment_where(segment_key: str) -> tuple[str, list]:
    """Returnt (where_clause, params_list) voor een segment."""
    s = SEGMENTS.get(segment_key)
    if not s:
        raise ValueError(f"Onbekend segment: {segment_key}")
    return s["where"], list(s["params"])


def segment_label(segment_key: str) -> str:
    s = SEGMENTS.get(segment_key)
    return s["label"] if s else segment_key


def all_segments() -> list[dict]:
    """Returnt lijst met (key, label) voor de UI."""
    return [{"key": k, "label": v["label"]} for k, v in SEGMENTS.items()]
