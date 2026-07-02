"""TUI-Reisebestätigungs-PDF-Parser für die Reisen-Datenbank.

Bewusst als eigenes Modul (nicht in app.py), damit die Regex-/Layout-Logik später
isoliert angepasst werden kann, wenn TUI das PDF-Format ändert.

Aufgeteilt in:
- ``parse_tui_text(full_text)`` — reine Regex-/Rechenlogik, ohne PDF-Abhängigkeit
  (so direkt mit Textschnipseln testbar).
- ``parse_tui_pdf(fileobj)`` — extrahiert Text via pdfplumber und ruft ``parse_tui_text``.

Erkenntnisse aus 11 echten TUI-PDFs (2024–2027), 3 Layout-Generationen, gemischte
Airlines (TUIfly + Eurowings), 1–7 Reisende, diverse Extras/Zahlungsarten.
"""
import re
from datetime import datetime


def _parse_eur(s) -> float:
    """'1.736,00' -> 1736.0 ; robust gegen None/leere Strings."""
    if not s:
        return 0.0
    s = str(s).replace("€", "").strip()
    if not s:
        return 0.0
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def _fmt_eur(v: float) -> str:
    """1736.0 -> '1.736,00' (deutsches Format)."""
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ── Vorreinigung ────────────────────────────────────────────────────────────
# TUI-PDFs bestehen aus mehreren Seiten mit identischem Kopf/Fuß und Rechts-
# Boilerplate; dazwischen verstreut PDF-Fußnoten-Hochzahlen (als eigene Zeile
# "3" oder angehängt "… (PMI) 3") und die "auf einen Blick"-Übersicht mit
# Punktelinien. Diese "Möbel" zerschießen mehrzeilige Feld-Regexes (z. B. einen
# Flug, dessen Streckenzeile auf der Folgeseite hinter dem Fuß steht).
#
# Statt jede Feld-Regex einzeln tolerant zu machen, wird der Müll EINMAL zentral
# entfernt. Neue Layout-Eigenheiten künftig hier ergänzen, nicht in den Feldern.

# Reine Boilerplate-Zeilen → restlos entfernen (alle Vorkommen).
_BOILERPLATE = re.compile(
    r"^(?:"
    r"Buchungsbestätigung/Rechnung"
    r"|TUI Deutschland GmbH\b.*Karl-Wiechert-Allee"      # Absender-Kopfzeile
    r"|TUI Deutschland GmbH, AG Hannover\b.*"            # Rechts-Fußzeile
    r"|Geschäftsführung:.*"                              # 2. Rechts-Fußzeile (+ "Seite X/Y")
    r"|Ihre Buchung im Detail#?\s*(?:\(Fortsetzung\))?"  # Abschnitts-Wiederholung
    r"|Datum Details Gast Preis"                         # Tabellenkopf-Wiederholung
    r"|Produkt Status|Teilnehmer Preis"                  # Übersichts-Tabellenköpfe
    r")\s*$"
)
# Seiten-Footer mit Buchungsnummer/Datum: wird gebraucht, aber nur EINMAL —
# weitere identische Vorkommen sind nur störendes Möbel zwischen den Blöcken.
_PAGE_FOOTER = re.compile(r"^Buchung:\s*\d+\s*\|.*\bDatum:\s*\d{2}\.\d{2}\.\d{4}")
# Punktelinie der "auf einen Blick"-Übersicht ("… . . . . bestätigt"). Die Zeile
# selbst bleibt (manche Posten — z. B. ein Coupon — stehen NUR dort); nur die
# Füll-Punkte werden entfernt. Dubletten fängt die Dedup-Logik unten ab.
_DOTLEADER = re.compile(r"(?:\.\s){3,}\.?")
# Reine Fußnoten-Hochzahl als eigene Zeile (1–2 Ziffern).
_FOOTNOTE_LINE = re.compile(r"^\d{1,2}$")


def _clean_text(full_text: str) -> str:
    """Entfernt Seiten-Möbel/Fußnoten/Übersichts-Dubletten vor dem Parsen.

    Bewusst konservativ: lässt jede Zeile mit echtem Inhalt unangetastet (außer dem
    Abschneiden angehängter Fußnoten), damit die Feld-Regexes unverändert greifen.
    """
    out = []
    footer_kept = False
    for raw in (full_text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if _DOTLEADER.search(s):          # Punktelinie der Übersicht → Punkte raus
            s = _DOTLEADER.sub(" ", s).strip()
        if _FOOTNOTE_LINE.match(s):       # alleinstehende Fußnoten-Ziffer → weg
            continue
        if _BOILERPLATE.match(s):         # Boilerplate → weg
            continue
        if _PAGE_FOOTER.match(s):         # Footer nur beim 1. Mal behalten
            if footer_kept:
                continue
            footer_kept = True
        out.append(s)
    return "\n".join(out)


def parse_tui_text(full_text: str) -> dict:
    """Parst den Volltext einer TUI-Reisebestätigung in ein strukturiertes Dict.

    Tolerant gegenüber den 3 bekannten Layout-Generationen (2024/2025/2026).
    Der Text wird zunächst von Seiten-Möbeln/Fußnoten bereinigt (``_clean_text``).
    """
    data = {
        "buchungsnummer": None,
        "buchungsdatum": None,
        "reisende": [],
        "reisezeitraum": {"von": None, "bis": None},
        "naechte": None,
        "reiseziel": None,
        "hotel": {"name": None, "code": None},
        "zimmertyp": None,
        "verpflegung": None,
        "gesamtpreis": None,
        "paketpreis": None,
        "paketpreis_netto": None,
        "extras_summe": None,
        "rabatte_summe": None,
        "preis_pro_nacht": None,
        "preis_pro_person_nacht": None,
        "preis_pro_nacht_paket": None,
        "preis_pro_person_nacht_paket": None,
        "rabatte": [],
        "zahlungsart": None,
        "anzahlung": {"betrag": None, "faelligkeit": None},
        "restzahlung": {"betrag": None, "faelligkeit": None},
        "fluege": [],
        "extras": [],
        "sonderwuensche": [],
    }

    full_text = _clean_text(full_text)

    # Buchungsnummer
    m = re.search(r"Buchung:\s*(\d+)", full_text)
    if m:
        data["buchungsnummer"] = m.group(1)

    # Buchungsdatum (Datum: DD.MM.YYYY HH:MM)
    m = re.search(r"Datum:\s*(\d{2}\.\d{2}\.\d{4})\s*\d{2}:\d{2}", full_text)
    if m:
        data["buchungsdatum"] = m.group(1)

    # Reisende (1–7): "Gast N  Herr/Frau Name (DD.MM.YYYY)  Preis €" bzw. ohne "Gast"
    for m in re.finditer(
        r"(?:Gast\s+)?\d+\s+((?:Herr|Frau)\s+[\w\s.-]+?)\s*"
        r"\((\d{2}\.\d{2}\.\d{4})\)\s+([\d.,]+)\s*€",
        full_text,
    ):
        data["reisende"].append({
            "name": m.group(1).strip(),
            "geburtsdatum": m.group(2),
            "preis": m.group(3),
        })

    # Gesamtpreis
    m = re.search(r"Gesamtpreis\s+([\d.,]+)\s*€", full_text)
    if m:
        data["gesamtpreis"] = m.group(1)

    # Zahlungsart (3 Varianten)
    m = re.search(r"Zahlungsart:\s*(.+?)(?:\s{2,}|Gesamtpreis|\n)", full_text)
    if m:
        data["zahlungsart"] = m.group(1).strip()

    # Anzahlung — mit oder ohne | Separator
    m = re.search(
        r"Anzahlung:\s*([\d.,]+)\s*€\s*[|\s]*Fälligkeit:\s*(\d{2}\.\d{2}\.\d{4})",
        full_text,
    )
    if m:
        data["anzahlung"] = {"betrag": m.group(1), "faelligkeit": m.group(2)}

    # Restzahlung
    m = re.search(
        r"Restzahlung:\s*([\d.,]+)\s*€\s*[|\s]*Fälligkeit:\s*(\d{2}\.\d{2}\.\d{4})",
        full_text,
    )
    if m:
        data["restzahlung"] = {"betrag": m.group(1), "faelligkeit": m.group(2)}

    # Hotel + Hotelcode + Zeitraum (Hotelname mit/ohne "Hotel"-Präfix).
    # Variante A (aktuelles Layout): Datum + "Paket (Unterkunft)" auf einer Zeile,
    # Hotel + Code auf der Folgezeile mit dem Bis-Datum:
    #   18.09.2025 – Paket (Unterkunft)
    #   27.09.2025 LANDMAR Playa La Arena (TFS36040)
    m = re.search(
        r"(\d{2}\.\d{2}\.\d{4})\s*[–-]\s*Paket\s*\(Unterkunft\)[^\n]*\n"
        r"\s*(\d{2}\.\d{2}\.\d{4})\s+(.+?)\s*\((\w{3}\d{4,5})\)",
        full_text,
    )
    if not m:
        # Variante B (älteres Layout): Datumsbereich in einer Zeile, Hotel danach.
        m = re.search(
            r"(\d{2}\.\d{2}\.\d{4})\s*[–-]\s*(\d{2}\.\d{2}\.\d{4})\s*.*?"
            r"(?:Paket|Unterkunft)\s*\n\s*(.+?)\s*\((\w{3}\d{4,5})\)",
            full_text,
            re.DOTALL,
        )
    if m:
        data["reisezeitraum"]["von"] = m.group(1)
        data["reisezeitraum"]["bis"] = m.group(2)
        data["hotel"]["name"] = m.group(3).strip()
        data["hotel"]["code"] = m.group(4)

    # Reiseziel (Zeile nach Hotelcode)
    m = re.search(r"\(\w{3}\d{4,5}\)\s*\n\s*(.+?)$", full_text, re.MULTILINE)
    if m:
        data["reiseziel"] = m.group(1).strip()

    # Zimmertyp — bis einschließlich "(Belegung: …)"; sonst ganze Zeile.
    # (Im aktuellen Layout folgt danach noch " 1  1.940,00 €" auf derselben Zeile.)
    m = re.search(r"Zimmertyp:\s*(.+?\(Belegung:[^)]*\))", full_text)
    if not m:
        m = re.search(r"Zimmertyp:\s*(.+)", full_text)
    if m:
        data["zimmertyp"] = m.group(1).strip()

    # Verpflegung — "All Inclusive" / "Nur Übernachtung" etc.
    m = re.search(r"Verpflegung:\s*(.+)", full_text)
    if m:
        data["verpflegung"] = m.group(1).strip()

    # Flüge — TUIfly UND Eurowings; tolerant gegenüber Zusatztext auf der Datums-
    # zeile ("Hinflug 1 im Paket") und der Zeitzeile ("(4h 40m) enthalten") sowie
    # optionalem "Voraussichtliche Flugzeit:"-Präfix. Seiten-Möbel zwischen Zeit- und
    # Streckenzeile (früher Ursache nicht erkannter Rückflüge) entfernt bereits
    # _clean_text; die kleine Lücken-Toleranz ist nur noch ein Puffer. Restliche
    # Fußnoten-Ziffern an der Strecke (" … (PMI) 3") schneidet _strip_footnote ab.
    def _strip_footnote(s):
        return re.sub(r"(\))\s+\d+\s*$", r"\1", s.strip()).strip()

    for fm in re.finditer(
        r"(\d{2}\.\d{2}\.\d{4})\s+(Hin|Rück)flug[^\n]*\n"
        r"(?:[^\n]*\n){0,3}?"                       # evtl. Statuszeile ("enthalten") dazwischen
        r"\s*(?:Voraussichtliche Flugzeit:\s*)?"
        r"(\d{2}:\d{2})\s*[–-]\s*(\d{2}:\d{2})\s*Uhr\s*\(([^)]+)\)[^\n]*\n"
        r"(?:[^\n>]*\n){0,2}?"                      # kleiner Puffer (Möbel raus via _clean_text)
        r"\s*([^>\n]+?)\s*>\s*([^>\n]+?)\n"
        r"\s*((?:TUIfly|Eurowings)\s+\S+)",
        full_text,
    ):
        data["fluege"].append({
            "datum": fm.group(1),
            "typ": fm.group(2) + "flug",
            "abflug_zeit": fm.group(3),
            "ankunft_zeit": fm.group(4),
            "dauer": fm.group(5).strip(),
            "von": _strip_footnote(fm.group(6)),
            "nach": _strip_footnote(fm.group(7)),
            "flugnummer": fm.group(8).strip(),
        })

    # Rabatte / Aktionscodes + Coupons (negative Beträge). Dedup nach Code, da
    # Posten in Übersicht und Detail doppelt vorkommen können.
    _rabatt_seen = set()

    def _add_rabatt(code, betrag):
        code = code.strip()
        if code in _rabatt_seen:
            return
        _rabatt_seen.add(code)
        data["rabatte"].append({"code": code, "betrag": betrag.strip()})

    for m in re.finditer(
        r"((?:SAVE|SUMMER|WINTER|EARLY)\w*)\s+.*?(-[\d.,]+\s*€)",
        full_text,
    ):
        _add_rabatt(m.group(1), m.group(2))

    # Coupons: zwischen "Nr. <id>" und Betrag kann Text stehen ("pro Buchung").
    for m in re.finditer(
        r"((?:SMILE|CA)-Coupon\s+Nr\.\s*[\w-]+).*?\((-[\d.,]+\s*€)\)",
        full_text,
    ):
        _add_rabatt(m.group(1), m.group(2))

    # Sitzplatzreservierung — mit Platznummern
    for m in re.finditer(
        r"Sitzplatzreservierung:\s*([\w,\s]+?)\s+(\d+)\s+([\d.,]+)\s*€",
        full_text,
    ):
        data["extras"].append({
            "typ": "Sitzplatzreservierung",
            "plaetze": m.group(1).strip(),
            "teilnehmer": int(m.group(2)),
            "preis": m.group(3),
        })

    # Großes Handgepäck
    for m in re.finditer(
        r"Großes\s+Handgepäck\s+(\d+\s*kg)\s*\((\w+)\)\s+(\d+)\s+([\d.,]+)\s*€",
        full_text,
    ):
        data["extras"].append({
            "typ": "Handgepäck",
            "gewicht": m.group(1),
            "code": m.group(2),
            "teilnehmer": int(m.group(3)),
            "preis": m.group(4),
        })

    # Flex Tarif
    m = re.search(
        r"(?:Entgelt\s+)?Flex\s+Tarif.*?\((\w+)\).*?(\d+)\s+([\d.,]+)\s*€",
        full_text,
    )
    if m:
        data["extras"].append({
            "typ": "Flex Tarif",
            "code": m.group(1),
            "teilnehmer": int(m.group(2)),
            "preis": m.group(3),
        })

    # (Zug zum Flug wird bewusst ignoriert — uninteressant für die Auswertung.)

    # Bustransfer — datierte Vorkommen bevorzugen; die Übersicht listet sie ohne
    # Datum zusätzlich (sonst doppelte Zählung). Fallback: rohe Zählung.
    dated_bus = len(re.findall(r"\d{2}\.\d{2}\.\d{4}\s+Bustransfer\s+inkl", full_text))
    raw_bus = len(re.findall(r"Bustransfer\s+inkl", full_text))
    bus_count = dated_bus or raw_bus
    if bus_count:
        data["extras"].append({
            "typ": "Bustransfer",
            "anzahl": bus_count,
            "preis": "inkl.",
        })

    # Sonderwünsche (interner =CODE= wird abgeschnitten)
    for m in re.finditer(r"Kundenwunsch:\s*(.+?)(?:\s*=\w+=)", full_text):
        data["sonderwuensche"].append(m.group(1).strip())

    # ── Berechnete Felder ──────────────────────────────────────────────────────

    # Nächte
    if data["reisezeitraum"]["von"] and data["reisezeitraum"]["bis"]:
        try:
            d1 = datetime.strptime(data["reisezeitraum"]["von"], "%d.%m.%Y")
            d2 = datetime.strptime(data["reisezeitraum"]["bis"], "%d.%m.%Y")
            data["naechte"] = (d2 - d1).days
        except ValueError:
            data["naechte"] = None

    # Extras-Summe (nur kostenpflichtige; "inkl." zählt nicht)
    extras_total = 0.0
    for e in data["extras"]:
        p = e.get("preis")
        if p and p != "inkl.":
            extras_total += _parse_eur(p)
    data["extras_summe"] = _fmt_eur(extras_total)

    # Rabatte-Summe (negativ)
    rabatte_total = 0.0
    for r in data["rabatte"]:
        rabatte_total += _parse_eur(r.get("betrag"))
    data["rabatte_summe"] = _fmt_eur(rabatte_total)

    # Paketpreis (brutto) = Gesamt − Extras − Rabatte (Rabatte negativ → wieder auf).
    # Netto-Paketpreis = Gesamt − bezahlte Extras: der reine Reisepreis (Hotel/Flug/
    # Transfer) nach Rabatt, ohne Extras (Rabatte stecken bereits im Gesamtpreis).
    if data["gesamtpreis"]:
        gesamt = _parse_eur(data["gesamtpreis"])
        paket = gesamt - extras_total - rabatte_total
        netto = gesamt - extras_total
        data["paketpreis"] = _fmt_eur(paket)
        data["paketpreis_netto"] = _fmt_eur(netto)

        if data["naechte"] and data["naechte"] > 0:
            anz = max(len(data["reisende"]), 1)
            data["preis_pro_nacht"] = _fmt_eur(gesamt / data["naechte"])
            data["preis_pro_person_nacht"] = _fmt_eur(gesamt / data["naechte"] / anz)
            data["preis_pro_nacht_paket"] = _fmt_eur(netto / data["naechte"])
            data["preis_pro_person_nacht_paket"] = _fmt_eur(netto / data["naechte"] / anz)

    return data


def check_fields(data: dict) -> list:
    """Listet wichtige Felder, die beim Parsen nicht (vollständig) erkannt wurden.

    Liefert menschenlesbare deutsche Labels für einen Import-Hinweis. Leer = alles ok.
    """
    data = data or {}
    warn = []
    if not data.get("buchungsnummer"):
        warn.append("Buchungsnummer")
    if not data.get("buchungsdatum"):
        warn.append("Buchungsdatum")
    if not data.get("reiseziel"):
        warn.append("Reiseziel")
    if not (data.get("hotel") or {}).get("name"):
        warn.append("Hotel")
    z = data.get("reisezeitraum") or {}
    if not (z.get("von") and z.get("bis")):
        warn.append("Reisezeitraum")
    elif not data.get("naechte"):
        warn.append("Nächte")
    if not data.get("verpflegung"):
        warn.append("Verpflegung")
    if not data.get("gesamtpreis"):
        warn.append("Gesamtpreis")
    if not data.get("reisende"):
        warn.append("Reisende")
    fl = data.get("fluege") or []
    if not fl:
        warn.append("Flüge")
    else:
        if not any((f.get("typ") or "").startswith("Hin") for f in fl):
            warn.append("Hinflug")
        if not any((f.get("typ") or "").startswith("Rück") for f in fl):
            warn.append("Rückflug")
    return warn


def extract_pdf_text(fileobj) -> str:
    """Extrahiert den rohen Volltext einer PDF (fürs Parsen und die Debug-Ansicht)."""
    import pdfplumber  # lokal importiert, damit die reine Textlogik ohne pdfplumber testbar bleibt

    with pdfplumber.open(fileobj) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def parse_tui_pdf(fileobj) -> dict:
    """Öffnet eine TUI-PDF (Dateipfad oder Datei-/Stream-Objekt) und parst sie."""
    return parse_tui_text(extract_pdf_text(fileobj))
