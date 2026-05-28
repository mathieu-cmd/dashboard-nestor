"""Hardcoded mappings voor Dashboard Nestor.

Drie tabellen, hier op één plek bij elkaar zodat aanpassingen via een
code-commit gebeuren (geen UI-editor meer in /admin):

  SEKTIE_KENGETAL          historische HIAnt-sektie -> RSZ-werknemerskengetal
  SEKTIE_OMSCHRIJVING      leesbare naam per HIAnt-sektie
  KENGETAL_OMSCHRIJVING    leesbare naam per RSZ-werknemerskengetal

Bij elke app-start synchroniseert init_schema() de SEKTIE_KENGETAL-dict naar
de SQLite-tabel sektie_kengetal_map, die door v_margelijst gebruikt wordt.

PAS DE WAARDEN HIERONDER AAN als de mapping wijzigt.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# SEKTIE -> KENGETAL
# ---------------------------------------------------------------------------
#
# Top-7 sekties in de historische CSV (= meest voorkomende):
#   7115 (10.516 rijen), 195 (5.817), 7195 (4.713), 1195 (2.733),
#   115 (2.724), 500 (70), 5000 (29)
#
# VUL IN met de juiste mapping. Lege dict = geen mapping = werknemerskengetal
# blijft NULL voor historische rijen.

SEKTIE_KENGETAL: dict[str, str] = {
    # "7115": "840",   # bv. flexi-job arbeider
    # "195":  "450",   # bv. bediende
    # "7195": "841",   # bv. flexi-job bediende
    # "1195": "450",
    # "115":  "015",
    # "500":  "050",
    # "5000": "050",
}


# ---------------------------------------------------------------------------
# SEKTIE -> leesbare omschrijving (HIAnt)
# ---------------------------------------------------------------------------

SEKTIE_OMSCHRIJVING: dict[str, str] = {
    # "7115": "Arbeider — flexi (sektie 7115)",
    # "195":  "Bediende (sektie 195)",
    # "7195": "Bediende — flexi (sektie 7195)",
    # "1195": "Bediende (sektie 1195)",
    # "115":  "Arbeider (sektie 115)",
    # "500":  "Student (sektie 500)",
    # "5000": "Student (sektie 5000)",
}


# ---------------------------------------------------------------------------
# KENGETAL -> leesbare omschrijving (RSZ-werknemerskengetal in live Prato-data)
# ---------------------------------------------------------------------------
#
# Op basis van Prato's officiële werknemerskengetal-set + Nestor-gebruik
# (050 = student is Nestor-specifieke conventie).

KENGETAL_OMSCHRIJVING: dict[str, str] = {
    "011": "Arbeider (cat. 011)",
    "015": "Arbeider",
    "025": "Arbeider IT",
    "050": "Student",
    "200": "Bediende (cat. 200)",
    "450": "Bediende",
    "495": "Bediende uitvoerend",
    "496": "Bediende (cat. 496)",
    "597": "Dienstencheques",
    "840": "Flexi-job arbeider",
    "841": "Flexi-job bediende",
}


def kengetal_label(code: str | None) -> str:
    """Pretty-print een werknemerskengetal. Onbekende code -> code zelf."""
    if not code:
        return ""
    return KENGETAL_OMSCHRIJVING.get(str(code), str(code))


def sektie_label(code: str | None) -> str:
    if not code:
        return ""
    return SEKTIE_OMSCHRIJVING.get(str(code), str(code))
