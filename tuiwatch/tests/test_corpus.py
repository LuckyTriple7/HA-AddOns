"""Golden-Korpus: echte (anonymisierte) TUI-PDF-Volltexte → erwartetes Parse-Ergebnis.

Dies ist das Sicherheitsnetz gegen künftige Layout-Änderungen: Bricht TUI das
Format, legt man den neuen (anonymisierten) Volltext + erwartetes JSON unter
``tests/fixtures/trips/`` ab — dieser Test zeigt dann **genau**, welches Feld kippt,
statt blind zu raten.

Fixtures sind aus echten Buchungsbestätigungen extrahiert und PII-bereinigt
(Namen → Mustermann/Vorname N, Geburtsdaten/Nummern → maskiert). Die Originale
liegen NICHT im Repo. Anlegen eines neuen Falls:

    python - <<'PY'
    import pdfplumber, re
    from tripparser import parse_tui_text, check_fields
    # ... Text extrahieren, anonymisieren, als trips/<slug>.txt speichern;
    # erwartetes Subset (siehe _subset unten) als trips/<slug>.json ablegen.
    PY
"""
import glob
import json
import os

import pytest

from tripparser import check_fields, parse_tui_text

FIXDIR = os.path.join(os.path.dirname(__file__), "fixtures", "trips")
CASES = sorted(glob.glob(os.path.join(FIXDIR, "*.txt")))


def _subset(d):
    """Das beim Import relevante Feld-Subset (so wird auch das erwartete JSON erzeugt)."""
    return {
        "buchungsnummer": d["buchungsnummer"],
        "reisezeitraum": d["reisezeitraum"],
        "naechte": d["naechte"],
        "reiseziel": d["reiseziel"],
        "hotel": d["hotel"],
        "verpflegung": d["verpflegung"],
        "gesamtpreis": d["gesamtpreis"],
        "reisende_count": len(d["reisende"]),
        "fluege_typen": [x["typ"] for x in d["fluege"]],
        "fluege_strecken": [x["von"] + " > " + x["nach"] for x in d["fluege"]],
        "preis_pro_person_nacht_paket": d["preis_pro_person_nacht_paket"],
        "warnings": check_fields(d),
    }


def test_korpus_vorhanden():
    assert CASES, f"Keine Korpus-Fixtures unter {FIXDIR}"


@pytest.mark.parametrize("txt_path", CASES, ids=[os.path.basename(p) for p in CASES])
def test_korpus_fall(txt_path):
    with open(txt_path, encoding="utf-8") as fh:
        text = fh.read()
    with open(txt_path[:-4] + ".json", encoding="utf-8") as fh:
        expected = json.load(fh)

    got = _subset(parse_tui_text(text))
    assert got == expected


@pytest.mark.parametrize("txt_path", CASES, ids=[os.path.basename(p) for p in CASES])
def test_korpus_vollstaendig_erkannt(txt_path):
    # Jeder echte Fall muss restlos erkannt werden (keine Import-Hinweise).
    with open(txt_path, encoding="utf-8") as fh:
        d = parse_tui_text(fh.read())
    assert check_fields(d) == []
