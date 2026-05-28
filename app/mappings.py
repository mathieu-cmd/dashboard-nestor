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
    "115":  "015",   # Arbeider
    "1195": "450",   # Bediende
    "195":  "450",   # Bediende
    "500":  "050",   # Student
    "5000": "050",   # Student
    "7115": "840",   # Flexi-job arbeider
    "7195": "841",   # Flexi-job bediende
}


# ---------------------------------------------------------------------------
# SEKTIE -> leesbare omschrijving (HIAnt)
# ---------------------------------------------------------------------------

SEKTIE_OMSCHRIJVING: dict[str, str] = {
    "115":  "Arbeider",
    "1195": "Bediende",
    "195":  "Bediende",
    "500":  "Student",
    "5000": "Student",
    "7115": "Flexi-job arbeider",
    "7195": "Flexi-job bediende",
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


# ---------------------------------------------------------------------------
# KLANT-id mapping (HIAnt ↔ Earnie/Prato)
# ---------------------------------------------------------------------------
#
# Soms gebruikt HIAnt een andere klant-id dan Earnie/Prato voor DEZELFDE
# klant — dan zou een naieve UNION twee aparte regels per maand opleveren.
# We mappen historische klant-id naar de live klant-id (Earnie). Voor klanten
# met identieke naam in beide systemen wordt deze automatisch bijgevuld in
# init_schema(); hier overschrijf je manueel voor uitzonderingen.
#
# Format: "hiant_klantref" -> "earnie_klantref"

KLANT_HIANT_TO_EARNIE: dict[str, str] = {
    # bv. "23456": "464",  # HIAnt-id voor Smartmat -> Earnie 464
}


# ---------------------------------------------------------------------------
# PERSOON-id mapping (HIAnt ↔ Earnie/Prato)
# ---------------------------------------------------------------------------
#
# In HIAnt staat de naam ongeplitst in één veld ("Hessens Filip"), in Earnie
# zijn voornaam en familienaam apart. Plus de persoonref verschilt vaak per
# systeem. Deze tabel mapt historische persoonref naar de live persoonref.
# Wordt aangevuld in init_schema() door auto-match op naam (woorden-overlap).
#
# Format: "hiant_persoonref" -> "earnie_persoonref"

PERSOON_HIANT_TO_EARNIE: dict[str, str] = {
    # bv. "3896": "2996",  # HIAnt 3896 (Hessens Filip) -> Earnie 2996 (Filip Hessens)
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
