"""Smoke-Test der Reisen-Routen (Import → Liste/Statistik → Detail → PDF → Delete).

Importiert die volle Flask-App (Flask/Playwright nötig). In der CI sind diese
Abhängigkeiten nicht installiert → der Test überspringt sich dann sauber.
Der Parser wird gemonkeypatcht, sodass kein echtes PDF/pdfplumber gebraucht wird.
"""
import importlib

import pytest

pytest.importorskip("flask")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))  # kein Template-Rendering im Test
    try:
        app_mod = importlib.import_module("app")
    except Exception as exc:  # Flask/Playwright o. Ä. fehlt (z. B. CI)
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(app_mod)
    # Pfade auf das Temp-Verzeichnis umbiegen (Modul-Konstanten wurden beim ersten
    # Import evtl. mit Default /data gesetzt).
    app_mod.DB_PATH = str(tmp_path / "tuiwatch.db")
    app_mod.TRIPS_DIR = str(tmp_path / "trips")
    app_mod.init_db()

    fake = {
        "buchungsnummer": "99999999",
        "buchungsdatum": "01.02.2026",
        "reisende": [{"name": "Herr Max Mustermann", "geburtsdatum": "01.01.1980", "preis": "1.000,00"}],
        "reisezeitraum": {"von": "01.05.2026", "bis": "08.05.2026"},
        "naechte": 7,
        "reiseziel": "Teststrand",
        "hotel": {"name": "Test Hotel", "code": "ABC12345"},
        "verpflegung": "All Inclusive",
        "gesamtpreis": "1.000,00",
        "paketpreis": "1.000,00",
        "fluege": [], "extras": [], "rabatte": [], "sonderwuensche": [],
        "anzahlung": {"betrag": None, "faelligkeit": None},
        "restzahlung": {"betrag": None, "faelligkeit": None},
        "zimmertyp": None, "zahlungsart": None,
    }
    monkeypatch.setattr(app_mod, "parse_tui_pdf", lambda f: fake)
    c = app_mod.test_client = app_mod.app.test_client()
    return c


# HA-Ingress-Header → Auth-Bypass (HA authentifiziert selbst)
ING = {"X-Ingress-Path": "/test"}


def _import_pdf(client):
    import io
    return client.post("/api/trips/import", headers=ING,
                       data={"pdf": (io.BytesIO(b"%PDF-1.4 fake"), "reise.pdf")},
                       content_type="multipart/form-data")


def test_unauth_without_ingress(client):
    assert client.get("/api/trips").status_code == 401


def test_import_list_detail_pdf_delete(client):
    r = _import_pdf(client)
    assert r.status_code == 200
    tid = r.get_json()["id"]

    lst = client.get("/api/trips", headers=ING).get_json()
    assert lst["stats"]["count"] == 1
    assert lst["stats"]["nights_sum"] == 7
    assert lst["stats"]["total_sum"] == 1000.0
    assert lst["stats"]["own_sum"] == 1000.0        # 1 Reisender → eigener Anteil = Gesamtpreis
    assert lst["trips"][0]["hotel"] == "Test Hotel"
    # Jahres-Aufschlüsselung (Reisebeginn 2026)
    assert lst["by_year"] == [{"year": "2026", "count": 1, "nights_sum": 7,
                               "total_sum": 1000.0, "own_sum": 1000.0,
                               "avg_per_night": round(1000.0 / 7, 2)}]

    detail = client.get(f"/api/trips/{tid}", headers=ING).get_json()
    assert detail["data"]["reiseziel"] == "Teststrand"
    assert detail["has_pdf"] is True

    pdf = client.get(f"/api/trips/{tid}/pdf", headers=ING)
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"

    # Re-Import gleicher Buchungsnummer → Upsert (kein zweiter Datensatz)
    _import_pdf(client)
    assert client.get("/api/trips", headers=ING).get_json()["stats"]["count"] == 1

    dele = client.delete(f"/api/trips/{tid}", headers=ING)
    assert dele.status_code == 200
    assert client.get("/api/trips", headers=ING).get_json()["stats"]["count"] == 0
    # PDF-Abruf danach 404
    assert client.get(f"/api/trips/{tid}/pdf", headers=ING).status_code == 404


def test_reject_non_pdf(client):
    import io
    r = client.post("/api/trips/import", headers=ING,
                    data={"pdf": (io.BytesIO(b"x"), "foto.jpg")},
                    content_type="multipart/form-data")
    assert r.status_code == 400


def test_trip_debug(client, monkeypatch):
    """Debug-Modus: bereinigter Text (Boilerplate raus), Feld-Status, Upload-Variante."""
    import importlib
    import io
    m = importlib.import_module("app")
    monkeypatch.setattr(m, "extract_pdf_text",
                        lambda f: "Buchungsbestätigung/Rechnung\nZeile 1\nZeile 2")
    tid = _import_pdf(client).get_json()["id"]

    d = client.get(f"/api/trips/{tid}/debug", headers=ING).get_json()
    assert d["ok"]
    assert "Zeile 1" in d["cleaned_text"]
    assert "Buchungsbestätigung" not in d["cleaned_text"]     # Boilerplate entfernt
    fields = {f["label"]: f["ok"] for f in d["fields"]}
    assert fields["Buchungsnummer"] is False                  # aus Dummy-Text nicht erkennbar

    # Upload-Variante (ohne Speichern) + Auth-Pflicht
    up = {"data": {"pdf": (io.BytesIO(b"%PDF fake"), "x.pdf")},
          "content_type": "multipart/form-data"}
    assert client.post("/api/trips/debug", headers=ING, **up).get_json()["ok"]
    assert client.get(f"/api/trips/{tid}/debug").status_code == 401


def test_next_trip_uses_hinflug_time(client, monkeypatch):
    """/api/trips/next: Abflugzeit kommt aus dem erkannten Hinflug (data.fluege)."""
    import importlib
    m = importlib.import_module("app")
    fake = {
        "buchungsnummer": "1", "buchungsdatum": "01.02.2026",
        "reisende": [{"name": "A", "geburtsdatum": "", "preis": "1"}],
        "reisezeitraum": {"von": "14.01.2099", "bis": "21.01.2099"},
        "naechte": 7, "reiseziel": "Sal", "hotel": {"name": "Hotel Sal", "code": "X"},
        "verpflegung": "AI", "gesamtpreis": "1", "paketpreis": "1",
        "fluege": [{"typ": "Hinflug", "datum": "14.01.2099", "abflug_zeit": "06:15",
                    "ankunft_zeit": "12:10", "dauer": "", "von": "STR", "nach": "SID",
                    "flugnummer": "X3 123"}],
        "extras": [], "rabatte": [], "sonderwuensche": [],
        "anzahlung": {"betrag": None, "faelligkeit": None},
        "restzahlung": {"betrag": None, "faelligkeit": None},
        "zimmertyp": None, "zahlungsart": None,
    }
    monkeypatch.setattr(m, "parse_tui_pdf", lambda f: fake)
    assert _import_pdf(client).status_code == 200

    d = client.get("/api/trips/next", headers=ING).get_json()["trip"]
    assert d["destination"] == "Sal"
    assert d["departure"] == "2099-01-14T06:15:00"
    assert d["has_time"] is True


def test_next_trip_falls_back_to_midnight_without_flight(client, monkeypatch):
    """Ohne erkannten Hinflug wird 00:00 des Reisebeginns als Abflug angenommen."""
    import importlib
    m = importlib.import_module("app")
    fake = {
        "buchungsnummer": "2", "buchungsdatum": "01.02.2026",
        "reisende": [{"name": "A", "geburtsdatum": "", "preis": "1"}],
        "reisezeitraum": {"von": "01.03.2099", "bis": "08.03.2099"},
        "naechte": 7, "reiseziel": "Mallorca", "hotel": {"name": "Hotel M", "code": "Y"},
        "verpflegung": "AI", "gesamtpreis": "1", "paketpreis": "1",
        "fluege": [], "extras": [], "rabatte": [], "sonderwuensche": [],
        "anzahlung": {"betrag": None, "faelligkeit": None},
        "restzahlung": {"betrag": None, "faelligkeit": None},
        "zimmertyp": None, "zahlungsart": None,
    }
    monkeypatch.setattr(m, "parse_tui_pdf", lambda f: fake)
    assert _import_pdf(client).status_code == 200

    d = client.get("/api/trips/next", headers=ING).get_json()["trip"]
    assert d["departure"] == "2099-03-01T00:00:00"
    assert d["has_time"] is False


def test_next_trip_none_without_upcoming_trips(client):
    assert client.get("/api/trips/next", headers=ING).get_json()["trip"] is None
