"""Tests für muc_flights_client.py (Flugplan ab München aus dem Saison-PDF).

Das PDF-Parsen selbst wird über die reinen Helfer und eine gemockte
pdfplumber-Ebene geprüft (kein Download im Testlauf), dazu die Logik drumherum:
PDF-Link auflösen, nur bei Änderung neu einlesen, Filter über Zeitraum/Richtung.
Die Zeilenformate stammen 1:1 aus dem echten Sommerplan 2026 (SCRAPING_MUC.md).
"""
import pytest

import muc_flights_client as muc


@pytest.fixture(autouse=True)
def _reset_state():
    muc._state.update(url="", size=0, datenstand="", season="", rows=[],
                      checked_ts=0, parsed_ts=0)
    yield
    muc._state.update(url="", size=0, datenstand="", season="", rows=[],
                      checked_ts=0, parsed_ts=0)


# ── Reine Helfer ───────────────────────────────────────────────────────────────

def test_weekdays_short():
    assert muc._weekdays_short("12-456-") == "Mo, Di, Do, Fr, Sa"
    assert muc._weekdays_short("1234567") == "täglich"
    assert muc._weekdays_short("------7") == "So"


def test_de_date_to_iso():
    assert muc._de_date("13.08.26") == "2026-08-13"
    assert muc._de_date("") == ""


ROWS = [
    "L EY 125 02:35 06:55 1234567 AUH 22.08.26 24.10.26 1 Etihad Airways",
    "S EY 128 22:30 + 06:20 1234567 AUH 01.09.26 22.09.26 1 Etihad Airways",
    "L DL 130 - 17:25 08:25 1234567 ATL 13.08.26 01.09.26 1 Delta Air Lines",
    "S DE 1508 05:55 08:05 12-456- PMI 13.08.26 20.10.26 1 Condor",
    "L EZY2929 06:45 09:45 1------ BRS 17.08.26 19.10.26 1 easyJet",
    "S LH 111 08:00 10:00 1234567 LCA ATH 13.08.26 24.10.26 2 Lufthansa",
    "S E9 768 18:40 21:30 -----6- MAD 22.08.26 22.08.26 1",   # ohne Airlinename
]


def test_row_regex_covers_all_real_shapes():
    for line in ROWS:
        assert muc._ROW_RE.match(line), line


def test_row_regex_rejects_headers():
    assert not muc._ROW_RE.match(
        "L/S Flug-Nr - Ziel ab MUC + Ziel an Tag Ziel Stop von bis Term. Airlinename")
    assert not muc._ROW_RE.match("Abu Dhabi (AUH) Vereinigte Arab. Emirate")


# ── Parsen mit gemocktem pdfplumber ────────────────────────────────────────────

class _FakePage:
    def __init__(self, text, words=None):
        self._text, self._words = text, words or []

    def extract_text(self):
        return self._text

    def extract_words(self):
        return self._words


class _FakePDF:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _header_words(city_parts, code, country_parts, top=85):
    """Überschriftzeile wie im PDF: Stadt links, (CODE) mittig, Land rechts."""
    out, x = [], 54
    for t in city_parts:
        out.append({"text": t, "x0": x, "top": top}); x += 30
    out.append({"text": f"({code})", "x0": x, "top": top})
    x = 360
    for t in country_parts:
        out.append({"text": t, "x0": x, "top": top}); x += 40
    return out


def _patch_pdf(monkeypatch, pages):
    import types
    fake = types.SimpleNamespace(open=lambda *a, **kw: _FakePDF(pages))
    monkeypatch.setitem(__import__("sys").modules, "pdfplumber", fake)


def test_parse_pdf_full(monkeypatch):
    text = ("Alle Angaben ohne Gewähr! Datenstand: 12.08.2026\n"
            "Flugplan München SOMMER 2026 (ZEITRAUM SAISON: 29.03.2026 BIS 24.10.2026)\n"
            + "\n".join(ROWS))
    words = (_header_words(["Palma", "de", "Mallorca"], "PMI", ["Spanien"])
             + _header_words(["Abu", "Dhabi"], "AUH", ["Vereinigte", "Arab.", "Emirate"], top=200))
    _patch_pdf(monkeypatch, [_FakePage(text, words)])

    res = muc.parse_pdf(b"x", verbose=False)
    assert res["datenstand"] == "12.08.2026"
    assert res["season"] == "29.03.2026–24.10.2026"
    assert len(res["rows"]) == len(ROWS)

    by_no = {r["flight_no"]: r for r in res["rows"]}
    # S = Start ab MUC (Zeit 1 = ab MUC), gegen die Flugtafel verifizierter Fall
    dep = by_no["DE 1508"]
    assert dep["direction"] == "departure"
    assert (dep["departure"], dep["arrival"]) == ("05:55", "08:05")
    assert dep["weekdays_short"] == "Mo, Di, Do, Fr, Sa"
    assert dep["date_from"] == "2026-08-13" and dep["date_till"] == "2026-10-20"
    assert dep["airport_name"] == "Palma de Mallorca" and dep["country"] == "Spanien"
    assert dep["terminal"] == "1" and dep["airline_name"] == "Condor"
    # L = Landung in MUC
    assert by_no["EY 125"]["direction"] == "arrival"
    # Tagesmarker
    assert by_no["EY 128"]["next_day"] is True and by_no["EY 128"]["prev_day"] is False
    assert by_no["DL 130"]["prev_day"] is True
    # Zwischenstopp + fehlender Airlinename
    assert by_no["LH 111"]["stop"] == "ATH"
    assert by_no["E9 768"]["airline_name"] == ""
    # dreistelliger Airline-Code ohne Leerzeichen
    assert by_no["EZY 2929"]["airline_code"] == "EZY"


def test_airport_names_ignores_index_page(monkeypatch):
    """Das Inhaltsverzeichnis listet Land links und Stadt rechts — würde Stadt
    und Land vertauschen, wenn es mitgelesen würde."""
    index_words = [{"text": "Spanien", "x0": 53, "top": 40},
                   {"text": "Palma", "x0": 259, "top": 40},
                   {"text": "(PMI)", "x0": 333, "top": 40}]
    table_words = _header_words(["Palma", "de", "Mallorca"], "PMI", ["Spanien"])
    pages = [_FakePage("Inhaltsverzeichnis\nSpanien Palma (PMI) 48", index_words),
             _FakePage("\n".join(ROWS), table_words)]
    _patch_pdf(monkeypatch, pages)
    rows = muc.parse_pdf(b"x")["rows"]
    pmi = next(r for r in rows if r["airport_code"] == "PMI")
    assert pmi["airport_name"] == "Palma de Mallorca"
    assert pmi["country"] == "Spanien"


# ── Link-Auflösung und Änderungserkennung ──────────────────────────────────────

class _Resp:
    def __init__(self, text="", content=b"", status=200, headers=None):
        self.text, self.content, self.status_code = text, content, status
        self.headers = headers or {}


def test_resolve_pdf_url(monkeypatch):
    html = '<a href="/_b/0000000000000027589260bb6718b5d0/flugplan.pdf">Aktueller Flugplan</a>'
    monkeypatch.setattr(muc.requests, "get", lambda *a, **kw: _Resp(text=html))
    assert muc.resolve_pdf_url() == (
        "https://www.munich-airport.de/_b/0000000000000027589260bb6718b5d0/flugplan.pdf")


def test_resolve_pdf_url_missing_link(monkeypatch):
    monkeypatch.setattr(muc.requests, "get", lambda *a, **kw: _Resp(text="<html>nix</html>"))
    assert muc.resolve_pdf_url() == ""


def _patch_download(monkeypatch, calls, size=500):
    html = '<a href="/_b/abc/flugplan.pdf">x</a>'

    def fake_get(url, **kw):
        calls.append(url)
        return _Resp(text=html, content=b"PDF")

    monkeypatch.setattr(muc.requests, "get", fake_get)
    monkeypatch.setattr(muc.requests, "head",
                        lambda *a, **kw: _Resp(headers={"Content-Length": str(size)}))
    monkeypatch.setattr(muc, "parse_pdf",
                        lambda data, verbose=False: {
                            "datenstand": "12.08.2026", "season": "S",
                            "rows": [{"direction": "departure", "airport_code": "PMI",
                                      "airport_name": "Palma", "country": "Spanien",
                                      "departure": "05:55", "arrival": "08:05",
                                      "date_from": "2026-08-13", "date_till": "2026-10-20",
                                      "flight_no": "DE 1508", "airline_name": "Condor",
                                      "airline_code": "DE", "weekdays_short": "Mo",
                                      "weekdays": "1------", "stop": "", "terminal": "1",
                                      "prev_day": False, "next_day": False}]})


def test_refresh_skips_download_when_unchanged(monkeypatch):
    calls: list = []
    _patch_download(monkeypatch, calls)
    assert muc.refresh() is True
    assert sum(1 for c in calls if c.endswith(".pdf")) == 1
    # Zweiter Lauf: gleiche URL, gleiche Größe → kein erneuter PDF-Download
    assert muc.refresh() is True
    assert sum(1 for c in calls if c.endswith(".pdf")) == 1
    # force lädt trotzdem neu
    assert muc.refresh(force=True) is True
    assert sum(1 for c in calls if c.endswith(".pdf")) == 2


def test_refresh_reloads_when_size_changed(monkeypatch):
    calls: list = []
    _patch_download(monkeypatch, calls, size=500)
    muc.refresh()
    _patch_download(monkeypatch, calls, size=999)
    muc.refresh()
    assert sum(1 for c in calls if c.endswith(".pdf")) == 2


def test_search_filters(monkeypatch):
    calls: list = []
    _patch_download(monkeypatch, calls)
    res = muc.search("PMI", direction="departure", date_from="2026-09", date_till="2026-09")
    assert res["total"] == 1 and res["datenstand"] == "12.08.2026"
    assert muc.search("PMI", direction="arrival")["total"] == 0
    assert muc.search("Spanien")["total"] == 1          # Land wird mitdurchsucht
    assert muc.search("PMI", date_from="2026-11")["total"] == 0   # nach Saisonende
    assert muc.search("PMI", date_till="2026-07")["total"] == 0   # vor Saisonstart


def test_search_returns_none_without_data(monkeypatch):
    monkeypatch.setattr(muc.requests, "get", lambda *a, **kw: _Resp(status=500))
    assert muc.search("PMI") is None
