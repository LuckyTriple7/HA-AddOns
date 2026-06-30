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
    assert lst["trips"][0]["hotel"] == "Test Hotel"
    # Jahres-Aufschlüsselung (Reisebeginn 2026)
    assert lst["by_year"] == [{"year": "2026", "count": 1, "nights_sum": 7,
                               "total_sum": 1000.0, "avg_per_night": round(1000.0 / 7, 2)}]

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
