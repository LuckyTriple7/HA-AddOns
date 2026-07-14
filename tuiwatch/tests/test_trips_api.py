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
    # deepcopy: der echte Parser liefert pro Aufruf ein frisches Dict — ein geteiltes
    # Objekt würde Mutationen (Overrides/abgeleitete Felder) zwischen Aufrufen leaken.
    import copy
    monkeypatch.setattr(app_mod, "parse_tui_pdf", lambda f: copy.deepcopy(fake))
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


def test_trip_rescan_reparses_stored_pdf(client, monkeypatch):
    """Rescan liest das gespeicherte PDF neu ein (z. B. nach Parser-Update), ohne
    Löschen/Neu-Upload: gleiche Reise-id, PDF/created bleiben, Daten aktualisiert."""
    import importlib
    m = importlib.import_module("app")
    r = _import_pdf(client)
    tid = r.get_json()["id"]
    with m.db() as con:
        before = dict(con.execute("SELECT created, pdf_name FROM trips WHERE id=?",
                                  (tid,)).fetchone())

    # Parser-"Update": erkennt jetzt zusätzlich ein Extra und ein anderes Reiseziel
    fake2 = dict(r.get_json()["data"])
    fake2["reiseziel"] = "Neustrand"
    fake2["extras"] = [{"typ": "Handgepäck", "gewicht": "10kg", "code": "HBAG",
                        "teilnehmer": 1, "preis": "15,00"}]
    monkeypatch.setattr(m, "parse_tui_pdf", lambda f: fake2)

    rr = client.post(f"/api/trips/{tid}/rescan", headers=ING)
    assert rr.status_code == 200
    d = rr.get_json()
    assert d["ok"] is True and d["id"] == tid
    assert d["data"]["reiseziel"] == "Neustrand"

    detail = client.get(f"/api/trips/{tid}", headers=ING).get_json()
    assert detail["data"]["reiseziel"] == "Neustrand"
    assert detail["data"]["extras"][0]["code"] == "HBAG"
    with m.db() as con:
        after = dict(con.execute("SELECT created, pdf_name FROM trips WHERE id=?",
                                 (tid,)).fetchone())
    assert after == before   # PDF-Datei + Erstellungsdatum unangetastet
    assert client.get("/api/trips", headers=ING).get_json()["stats"]["count"] == 1

    # Rescan auf nicht existierende Reise → 404
    assert client.post("/api/trips/999999/rescan", headers=ING).status_code == 404


# ── Manuelle Feld-Zuordnung (PATCH /api/trips/<id>/fields) ──────────────────────

def _patch_fields(client, tid, fields):
    return client.patch(f"/api/trips/{tid}/fields", headers=ING, json={"fields": fields})


def test_manual_field_override_updates_data_sql_and_derived(client):
    import importlib
    m = importlib.import_module("app")
    tid = _import_pdf(client).get_json()["id"]
    r = _patch_fields(client, tid, {"reiseziel": "Neuland", "gesamtpreis": "2000,00"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert d["data"]["reiseziel"] == "Neuland"
    assert d["data"]["gesamtpreis"] == "2.000,00"     # normalisiert
    assert d["data"]["paketpreis"] == "2.000,00"       # abgeleitet neu berechnet
    assert d["manual"] == {"reiseziel": "Neuland", "gesamtpreis": "2.000,00"}
    detail = client.get(f"/api/trips/{tid}", headers=ING).get_json()
    assert detail["data"]["reiseziel"] == "Neuland"
    with m.db() as con:
        row = con.execute("SELECT destination, total_price FROM trips WHERE id=?",
                          (tid,)).fetchone()
    assert row["destination"] == "Neuland"
    assert row["total_price"] == 2000.0


def test_manual_override_survives_rescan_and_reimport(client):
    tid = _import_pdf(client).get_json()["id"]
    _patch_fields(client, tid, {"reiseziel": "Neuland"})
    # Rescan: Parser liefert weiterhin "Teststrand" — Override muss gewinnen
    rr = client.post(f"/api/trips/{tid}/rescan", headers=ING)
    assert rr.get_json()["data"]["reiseziel"] == "Neuland"
    # Re-Import gleicher Buchungsnummer (Upsert) — Override bleibt, kein Duplikat
    _import_pdf(client)
    assert client.get("/api/trips", headers=ING).get_json()["stats"]["count"] == 1
    detail = client.get(f"/api/trips/{tid}", headers=ING).get_json()
    assert detail["data"]["reiseziel"] == "Neuland"


def test_manual_override_delete_restores_parser_value(client):
    tid = _import_pdf(client).get_json()["id"]
    _patch_fields(client, tid, {"reiseziel": "Neuland"})
    r = _patch_fields(client, tid, {"reiseziel": None})
    assert r.status_code == 200
    d = r.get_json()
    assert d["manual"] == {}
    assert d["data"]["reiseziel"] == "Teststrand"      # Parser-Wert wieder aktiv


def test_manual_extras_override_replaces_and_recomputes(client):
    import importlib
    m = importlib.import_module("app")
    tid = _import_pdf(client).get_json()["id"]
    r = _patch_fields(client, tid, {"extras": [
        {"typ": "Handgepäck", "details": "10kg", "anzahl": 1, "preis": "15,00 €"},
        {"typ": "Bustransfer", "preis": "inkl."}]})
    assert r.status_code == 200
    d = r.get_json()["data"]
    assert [e["typ"] for e in d["extras"]] == ["Handgepäck", "Bustransfer"]
    assert d["extras"][0]["preis"] == "15,00"          # € entfernt/normalisiert
    assert d["extras_summe"] == "15,00"                # "inkl." zählt nicht
    assert d["paketpreis"] == "985,00"                 # 1.000 − 15
    with m.db() as con:
        assert con.execute("SELECT package_price FROM trips WHERE id=?",
                           (tid,)).fetchone()["package_price"] == 985.0


def test_manual_rabatte_override_and_inklusive_flag(client):
    """Rabatte manuell setzen: Betrag wird negativ normalisiert und standardmäßig
    zum Brutto-Paketpreis zurückgerechnet. Mit rabatt_inklusive (Rabatt steckt
    schon im ausgewiesenen Reisepreis) entfällt die Rückrechnung."""
    tid = _import_pdf(client).get_json()["id"]
    r = _patch_fields(client, tid, {"rabatte": [{"code": "SAVE150", "betrag": "150,00 €"}]})
    assert r.status_code == 200
    d = r.get_json()["data"]
    assert d["rabatte"] == [{"code": "SAVE150", "betrag": "-150,00"}]
    assert d["rabatte_summe"] == "-150,00"
    assert d["paketpreis"] == "1.150,00"        # 1.000 − 0 Extras − (−150) = brutto vor Rabatt
    assert d["paketpreis_netto"] == "1.000,00"

    r2 = _patch_fields(client, tid, {"rabatt_inklusive": True})
    d2 = r2.get_json()["data"]
    assert d2["rabatt_inklusive"] is True
    assert d2["paketpreis"] == "1.000,00"       # keine Rückrechnung mehr
    # Flag löschen → wieder Standard-Rechnung
    d3 = _patch_fields(client, tid, {"rabatt_inklusive": None}).get_json()["data"]
    assert d3["paketpreis"] == "1.150,00"


def test_manual_field_validation(client):
    tid = _import_pdf(client).get_json()["id"]
    assert _patch_fields(client, tid, {"kaputt": "x"}).status_code == 400
    assert _patch_fields(client, tid, {"buchungsdatum": "2026-05-01"}).status_code == 400
    assert _patch_fields(client, tid, {"gesamtpreis": "viel"}).status_code == 400
    assert _patch_fields(client, tid, {"naechte": 0}).status_code == 400
    assert _patch_fields(client, tid, {"extras": [{"preis": "15,00"}]}).status_code == 400  # typ fehlt
    assert _patch_fields(client, 999999, {"reiseziel": "X"}).status_code == 404
    assert client.patch(f"/api/trips/{tid}/fields", headers=ING, json={}).status_code == 400


def test_debug_payload_marks_manual_fields(client, monkeypatch):
    import importlib
    m = importlib.import_module("app")
    tid = _import_pdf(client).get_json()["id"]
    _patch_fields(client, tid, {"reiseziel": "Neuland"})
    monkeypatch.setattr(m, "extract_pdf_text", lambda f: "irrelevanter Text")
    monkeypatch.setattr(m, "parse_tui_text", lambda t: {"reiseziel": None, "hotel": {}})
    d = client.get(f"/api/trips/{tid}/debug", headers=ING).get_json()
    assert d["ok"] is True
    assert d["manual"] == {"reiseziel": "Neuland"}
    ziel = next(f for f in d["fields"] if f["label"] == "Reiseziel")
    assert ziel["manual"] is True and ziel["ok"] is True   # Override deckt Feld ab
    assert d["data"]["reiseziel"] == "Neuland"


# ── Packlisten-Vorlage (GET/POST /api/packing-template) ────────────────────────

def test_packing_template_default_and_custom_roundtrip(client):
    import importlib
    m = importlib.import_module("app")
    d = client.get("/api/packing-template", headers=ING).get_json()
    assert d["custom"] is False
    assert d["template"] == m.PACKING_TEMPLATE

    tpl = {"Kleidung": ["T-Shirts", "Shorts"], "Technik": ["Ladekabel"]}
    r = client.post("/api/packing-template", headers=ING, json={"template": tpl})
    assert r.status_code == 200 and r.get_json()["custom"] is True
    d2 = client.get("/api/packing-template", headers=ING).get_json()
    assert d2["custom"] is True and d2["template"] == tpl

    # Neue Reise wird aus der ANGEPASSTEN Vorlage befüllt (Seed beim ersten Detail-GET)
    tid = _import_pdf(client).get_json()["id"]
    detail = client.get(f"/api/trips/{tid}", headers=ING).get_json()
    assert [(p["category"], p["label"]) for p in detail["packing"]] == [
        ("Kleidung", "T-Shirts"), ("Kleidung", "Shorts"), ("Technik", "Ladekabel")]

    # „Zurücksetzen" einer Reise nutzt ebenfalls die angepasste Vorlage
    client.post(f"/api/trips/{tid}/packing", headers=ING,
                json={"category": "Kleidung", "label": "Eigenes Item"})
    client.post(f"/api/trips/{tid}/packing/reset", headers=ING)
    detail = client.get(f"/api/trips/{tid}", headers=ING).get_json()
    assert len(detail["packing"]) == 3

    # template:null stellt die Standard-Vorlage wieder her
    r3 = client.post("/api/packing-template", headers=ING, json={"template": None})
    assert r3.status_code == 200 and r3.get_json()["custom"] is False
    assert client.get("/api/packing-template", headers=ING).get_json()["template"] == m.PACKING_TEMPLATE


def test_packing_template_validation(client):
    bad = [
        {},                                     # leer
        {"": ["x"]},                            # leere Kategorie
        {"Kat": []},                            # keine Items
        {"Kat": ["x" * 81]},                    # Item zu lang
        {"Kat": ["ok"], "K2": "kein-array"},    # Items kein Array
        {"Kat": ["x"] * 71},                    # über Gesamt-Limit 70
    ]
    for tpl in bad:
        assert client.post("/api/packing-template", headers=ING,
                           json={"template": tpl}).status_code == 400, tpl


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


def _upload_attachment(client, tid, name="reiseplan.pdf", content=b"%PDF-1.4 fake"):
    import io
    return client.post(f"/api/trips/{tid}/attachments", headers=ING,
                       data={"pdf": (io.BytesIO(content), name)},
                       content_type="multipart/form-data")


def test_trip_starts_without_attachments(client):
    tid = _import_pdf(client).get_json()["id"]
    assert client.get(f"/api/trips/{tid}", headers=ING).get_json()["attachments"] == []


def test_attachment_upload_get_delete(client):
    tid = _import_pdf(client).get_json()["id"]

    r = _upload_attachment(client, tid, "Reiseplan.pdf")
    assert r.status_code == 200
    aid = r.get_json()["id"]

    detail = client.get(f"/api/trips/{tid}", headers=ING).get_json()
    assert len(detail["attachments"]) == 1
    assert detail["attachments"][0]["orig_name"] == "Reiseplan.pdf"

    got = client.get(f"/api/trips/{tid}/attachments/{aid}", headers=ING)
    assert got.status_code == 200
    assert got.mimetype == "application/pdf"

    dele = client.delete(f"/api/trips/{tid}/attachments/{aid}", headers=ING)
    assert dele.status_code == 200
    assert client.get(f"/api/trips/{tid}", headers=ING).get_json()["attachments"] == []
    assert client.get(f"/api/trips/{tid}/attachments/{aid}", headers=ING).status_code == 404


def test_attachment_reject_non_pdf(client):
    tid = _import_pdf(client).get_json()["id"]
    r = _upload_attachment(client, tid, "foto.jpg")
    assert r.status_code == 400


def test_attachment_deleted_with_trip(client):
    tid = _import_pdf(client).get_json()["id"]
    _upload_attachment(client, tid)
    assert client.delete(f"/api/trips/{tid}", headers=ING).status_code == 200
    # Reise weg → auch der Anhang nicht mehr abrufbar (Kaskade)
    assert client.get(f"/api/trips/{tid}", headers=ING).status_code == 404
