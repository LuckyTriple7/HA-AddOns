"""Tests für den TUI-PDF-Parser (tripparser.parse_tui_text).

Arbeitet mit gecrafteten Volltext-Schnipseln, die die in C:\\Temp\\PDF\\CLAUDE.md
dokumentierten Muster der 3 Layout-Generationen abbilden — so testbar ohne echte
PDFs/pdfplumber.
"""
from tripparser import _parse_eur, parse_tui_text

# Gran Canaria 2026 — 2 Reisende, alle Extras, gemischte Codes
GC2026 = """\
Buchung: 76767692
Datum: 10.02.2026 14:30
Hallo Herr Waidele,
Gast 1 Herr Andreas Waidele (06.11.1977) 1.444,00 €
Gast 2 Herr Gerald Gauss-Peter (16.05.1984) 1.407,00 €
01.05.2026 - 11.05.2026 Paket
Riu Papayas (LPA31006)
Playa del Ingles
Zimmertyp: DZX1, Double Room with Garden View (Belegung: 2 Personen)
Verpflegung: All Inclusive
01.05.2026 Hinflug
13:30 – 17:10 Uhr (4h 40m)
Stuttgart (STR) > Gran Canaria (LPA)
TUIfly X32168
11.05.2026 Rückflug
18:10 – 23:25 Uhr (4h 15m)
Gran Canaria (LPA) > Stuttgart (STR)
TUIfly X32169
Sitzplatzreservierung: 11D, 11C 2 21,00 €
Großes Handgepäck 10 kg (HBAG) 1 10,00 €
Sitzplatzreservierung: 12D, 12C 2 21,00 €
Großes Handgepäck 10 kg (HBAG) 1 10,00 €
Entgelt Flex Tarif bis 2500 Euro (CL1X5401) 1 59,00 €
Kostenloses Zug zum Flug 2. Klasse Oneway Hin (ZZFXZR2H)
Kostenloses Zug zum Flug 2. Klasse Oneway Rück (ZZFXZR2R)
Bustransfer inkl. (2111)
Bustransfer inkl. (2111)
Kundenwunsch: bitte Zimmer in oberen Etagen =XBBY=
Zahlungsart: TUI CARD Gold One
Anzahlung: 551,75 € | Fälligkeit: 24.07.2025
Restzahlung: 2.299,25 € | Fälligkeit: 03.04.2026
Gesamtpreis 2.851,00 €
"""


def test_parse_eur_helper():
    assert _parse_eur("1.736,00") == 1736.0
    assert _parse_eur("-150,00 €") == -150.0
    assert _parse_eur("") == 0.0
    assert _parse_eur(None) == 0.0


def test_gran_canaria_kerndaten():
    d = parse_tui_text(GC2026)
    assert d["buchungsnummer"] == "76767692"
    assert d["buchungsdatum"] == "10.02.2026"
    assert d["reiseziel"] == "Playa del Ingles"
    assert d["hotel"]["name"] == "Riu Papayas"
    assert d["hotel"]["code"] == "LPA31006"
    assert d["reisezeitraum"] == {"von": "01.05.2026", "bis": "11.05.2026"}
    assert d["naechte"] == 10
    assert d["verpflegung"] == "All Inclusive"
    assert d["gesamtpreis"] == "2.851,00"
    assert d["zahlungsart"] == "TUI CARD Gold One"
    assert d["anzahlung"] == {"betrag": "551,75", "faelligkeit": "24.07.2025"}
    assert d["restzahlung"] == {"betrag": "2.299,25", "faelligkeit": "03.04.2026"}


def test_gran_canaria_reisende():
    d = parse_tui_text(GC2026)
    assert len(d["reisende"]) == 2
    assert d["reisende"][0]["name"] == "Herr Andreas Waidele"
    assert d["reisende"][0]["geburtsdatum"] == "06.11.1977"
    assert d["reisende"][1]["name"] == "Herr Gerald Gauss-Peter"


def test_gran_canaria_fluege():
    d = parse_tui_text(GC2026)
    assert len(d["fluege"]) == 2
    hin, rueck = d["fluege"]
    assert hin["typ"] == "Hinflug"
    assert hin["von"] == "Stuttgart (STR)"
    assert hin["nach"] == "Gran Canaria (LPA)"
    assert hin["flugnummer"] == "TUIfly X32168"
    assert rueck["typ"] == "Rückflug"


def test_gran_canaria_extras_und_summen():
    d = parse_tui_text(GC2026)
    typen = [e["typ"] for e in d["extras"]]
    # Sitzplatz/Handgepäck dürfen doppelt sein (pro Flug Hin/Rück); Flex nur einmal.
    assert typen.count("Sitzplatzreservierung") == 2
    assert typen.count("Handgepäck") == 2
    assert typen.count("Flex Tarif") == 1
    assert "Zug zum Flug" not in typen  # bewusst ignoriert
    bus = [e for e in d["extras"] if e["typ"] == "Bustransfer"][0]
    assert bus["anzahl"] == 2 and bus["preis"] == "inkl."
    # 21 + 21 + 10 + 10 + 59 = 121,00 ; Paket = 2851 - 121 = 2730,00
    assert d["extras_summe"] == "121,00"
    assert d["paketpreis"] == "2.730,00"
    assert d["preis_pro_nacht"] == "285,10"
    assert d["preis_pro_person_nacht"] == "142,55"
    # Netto (ohne Extras, Rabatt 0) = 2730 ; /10 = 273,00 ; /Person = 136,50 (vgl. MD)
    assert d["paketpreis_netto"] == "2.730,00"
    assert d["preis_pro_nacht_paket"] == "273,00"
    assert d["preis_pro_person_nacht_paket"] == "136,50"


def test_sonderwunsch_ohne_internen_code():
    d = parse_tui_text(GC2026)
    assert d["sonderwuensche"] == ["bitte Zimmer in oberen Etagen"]


# Algarve 2025 — Eurowings + TUIfly gemischt, "Nur Übernachtung", ohne "Hotel"-Präfix
ALGARVE = """\
Buchung: 76255579
Datum: 05.06.2025 09:10
Gast 1 Herr Andreas Waidele (06.11.1977) 538,00 €
05.11.2025 - 09.11.2025 Paket
Aparthotel Jardim do Vau (FAO13010)
Alvor
Verpflegung: Nur Übernachtung
05.11.2025 Hinflug
06:00 – 08:05 Uhr (3h 5m)
Stuttgart (STR) > Faro (FAO)
Eurowings EW2648
09.11.2025 Rückflug
08:40 – 12:40 Uhr (3h 0m)
Faro (FAO) > Stuttgart (STR)
TUIfly X32819
Sitzplatzreservierung: 2A 1 0,00 €
Bustransfer inkl.
Zahlungsart: TUI CARD Gold One
Gesamtpreis 538,00 €
"""


def test_algarve_gemischte_airlines_und_verpflegung():
    d = parse_tui_text(ALGARVE)
    assert d["verpflegung"] == "Nur Übernachtung"
    assert d["hotel"]["name"] == "Aparthotel Jardim do Vau"
    assert d["naechte"] == 4
    assert d["fluege"][0]["flugnummer"] == "Eurowings EW2648"
    assert d["fluege"][1]["flugnummer"] == "TUIfly X32819"
    # nur ein Sitzplatz zu 0,00 € + Bustransfer inkl. → keine kostenpflichtigen Extras
    assert d["extras_summe"] == "0,00"
    assert d["paketpreis"] == "538,00"


# Rabatte / Coupons (negative Beträge)
def test_rabatte_und_coupons():
    txt = (
        "Buchung: 63406343\n"
        "SAVE300 Aktionscode für Frühbucher (-150,00 €)\n"
        "SMILE-Coupon Nr. 029-2024 (-60,00 €)\n"
        "Gesamtpreis 1.608,00 €\n"
    )
    d = parse_tui_text(txt)
    codes = {r["code"] for r in d["rabatte"]}
    assert "SAVE300" in codes
    assert any("SMILE-Coupon" in c for c in codes)
    assert d["rabatte_summe"] == "-210,00"


def test_sieben_reisende():
    lines = ["Buchung: 75595465"]
    for i in range(1, 8):
        lines.append(f"Gast {i} Herr Tester Nummer{i} (01.01.1980) 559,00 €")
    d = parse_tui_text("\n".join(lines))
    assert len(d["reisende"]) == 7


def test_sieben_reisende_pro_person_nacht():
    # Mallorca-Gruppe: 7 Personen, 2 Nächte, 3.955 € → 282,50 €/Person/Nacht (vgl. MD)
    lines = ["Buchung: 75595465"]
    for i in range(1, 8):
        lines.append(f"Gast {i} Herr Tester Nummer{i} (01.01.1980) 565,00 €")
    lines += [
        "25.07.2025 – Paket (Unterkunft) bestätigt",
        "27.07.2025 Grupotel Amapola (PMI83043)",
        "Bucht von Alcudia",
        "Gesamtpreis 3.955,00 €",
    ]
    d = parse_tui_text("\n".join(lines))
    assert len(d["reisende"]) == 7
    assert d["naechte"] == 2
    assert d["preis_pro_nacht_paket"] == "1.977,50"          # gesamte Buchung/Nacht
    assert d["preis_pro_person_nacht_paket"] == "282,50"     # /7 Personen


# Echtes Layout (Variante A, anonymisiert) — getrennte Datumszeile mit
# "Paket (Unterkunft)", Flugzeilen mit Zusatztext, Coupon mit "pro Buchung",
# und die typische Dopplung Übersicht ↔ Detail (Bustransfer/Sitzplatz/Handgepäck).
REAL_LAYOUT = """\
Buchung: 74245049 | Vertrags-/Versicherungsbeginn: 18.09.2025 | Datum: 04.01.2025 11:24 Uhr
Ihre Buchung auf einen Blick
Stuttgart (STR) > Teneriffa Süd (TFS) . . . . . . . . . . . bestätigt
Sitzplatzreservierung: 2A
Großes Handgepäck 10 kg (HBAG)
Bustransfer inkl. (2111). . . . . . . . . . . bestätigt
LANDMAR Playa La Arena (TFS36040), Puerto Santiago . . . . . bestätigt
SMILE-Coupon Nr. 029-2024 pro Buchung (-60,00 €). . . . . . enthalten
Teilnehmer Preis
Gast 1 Herr Max Mustermann (06.11.1977) 1.949,00 €
Gesamtpreis 1.949,00 €
Zahlungsart: TUI CARD Gold One
Anzahlung: 487,25 € | Fälligkeit: 10.01.2025
Restzahlung: 1.461,75 € | Fälligkeit: 21.08.2025
Ihre Buchung im Detail#
Datum Details Gast Preis
18.09.2025 Hinflug 1 im Paket
13:20 – 17:00 Uhr (4h 40m) enthalten
Stuttgart (STR) > Teneriffa Süd (TFS)
TUIfly X32218 – Economy Class
Sitzplatzreservierung: 2A 1 0,00 €
Großes Handgepäck 10 kg (HBAG) 1 10,00 €
18.09.2025 Bustransfer inkl. (2111) 1 im Paket
18.09.2025 – Paket (Unterkunft)
27.09.2025 LANDMAR Playa La Arena (TFS36040)
Puerto Santiago
Zimmertyp: DZM2, Double Deluxe Platinum (adults only) (Belegung: 1 Person) 1 1.940,00 €
Ihre Verpflegung: All Inclusive
27.09.2025 Bustransfer inkl. (2111) 1 im Paket
27.09.2025 Rückflug 1 im Paket
18:00 – 23:25 Uhr (4h 25m) enthalten
Teneriffa Süd (TFS) > Stuttgart (STR)
TUIfly X32219 – Economy Class
Sitzplatzreservierung: 2A 1 0,00 €
Großes Handgepäck 10 kg (HBAG) 1 10,00 €
18.09.2025 Entgelt Flex Tarif bis 2500 Euro (CL1X5401) 1 49,00 €
"""


def test_reales_layout_variante_a():
    d = parse_tui_text(REAL_LAYOUT)
    assert d["buchungsnummer"] == "74245049"
    assert d["reisezeitraum"] == {"von": "18.09.2025", "bis": "27.09.2025"}
    assert d["naechte"] == 9
    assert d["hotel"] == {"name": "LANDMAR Playa La Arena", "code": "TFS36040"}
    assert d["reiseziel"] == "Puerto Santiago"
    assert d["zimmertyp"] == "DZM2, Double Deluxe Platinum (adults only) (Belegung: 1 Person)"
    assert d["verpflegung"] == "All Inclusive"
    assert len(d["fluege"]) == 2
    assert d["fluege"][0]["dauer"] == "4h 40m"
    assert d["fluege"][0]["nach"] == "Teneriffa Süd (TFS)"
    typen = [e["typ"] for e in d["extras"]]
    assert typen.count("Sitzplatzreservierung") == 2   # Hin + Rück
    assert typen.count("Handgepäck") == 2              # Hin + Rück
    assert typen.count("Flex Tarif") == 1
    bus = [e for e in d["extras"] if e["typ"] == "Bustransfer"][0]
    assert bus["anzahl"] == 2                          # datierte Vorkommen, nicht 3
    assert len(d["rabatte"]) == 1                      # Coupon nicht doppelt
    assert d["rabatte"][0]["code"] == "SMILE-Coupon Nr. 029-2024"
    # 20 (Handgepäck) + 49 (Flex) = 69 ; Rabatt -60 ; Paket = 1949 - 69 + 60 = 1940
    assert d["extras_summe"] == "69,00"
    assert d["rabatte_summe"] == "-60,00"
    assert d["paketpreis"] == "1.940,00"
    # Netto (o. Extras, Rabatt bereits im Gesamt) = 1949 - 69 = 1880 ; /9 = 208,89 (vgl. MD)
    assert d["paketpreis_netto"] == "1.880,00"
    assert d["preis_pro_nacht_paket"] == "208,89"


def test_flug_mit_umgebrochener_statuszeile():
    # In manchen PDFs steht die Status-Spalte ("enthalten") als eigene Zeile
    # zwischen Datums- und Zeitzeile (v. a. beim Rückflug).
    txt = """\
03.05.2024 Hinflug 1 im Paket
13:30 – 17:10 Uhr (4h 40m) enthalten
Stuttgart (STR) > Gran Canaria (LPA)
TUIfly X32168 – Economy Class
13.05.2024 Rückflug 1 im Paket
enthalten
18:10 – 23:25 Uhr (4h 15m)
Gran Canaria (LPA) > Stuttgart (STR)
TUIfly X32169 – Economy Class
"""
    d = parse_tui_text(txt)
    assert len(d["fluege"]) == 2
    assert d["fluege"][0]["typ"] == "Hinflug"
    assert d["fluege"][1]["typ"] == "Rückflug"
    assert d["fluege"][1]["flugnummer"] == "TUIfly X32169"
    assert d["fluege"][1]["von"] == "Gran Canaria (LPA)"


def test_paket_zeile_mit_status_und_pro_person_nacht():
    # Paket-Block mit angehängtem "bestätigt" hinter "(Unterkunft)" + 2 Reisende.
    # Früher blieb der Zeitraum leer → keine €/Nacht-Berechnung.
    txt = """\
Buchung: 76767692
Gast 1 Herr Andreas Waidele (06.11.1977) 1.444,00 €
Gast 2 Herr Gerald Gauss-Peter (16.05.1984) 1.407,00 €
01.05.2026 – Paket (Unterkunft) bestätigt
11.05.2026 Riu Papayas (LPA31006)
Playa del Ingles
Verpflegung: All Inclusive
Gesamtpreis 2.851,00 €
"""
    d = parse_tui_text(txt)
    assert d["reisezeitraum"] == {"von": "01.05.2026", "bis": "11.05.2026"}
    assert d["naechte"] == 10
    assert d["hotel"] == {"name": "Riu Papayas", "code": "LPA31006"}
    assert len(d["reisende"]) == 2
    # ohne Extras/Rabatt: netto = 2851 ; /10 = 285,10 ; /10/2 = 142,55
    assert d["preis_pro_nacht_paket"] == "285,10"
    assert d["preis_pro_person_nacht_paket"] == "142,55"


def test_leerer_text_bricht_nicht():
    d = parse_tui_text("")
    assert d["buchungsnummer"] is None
    assert d["reisende"] == []
    assert d["naechte"] is None
