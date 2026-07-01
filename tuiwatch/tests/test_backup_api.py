"""Round-Trip-Test für Backup & Restore (ZIP mit Angeboten inkl. Verlauf/Marker,
gebuchten Reisen inkl. PDF, gespeicherten Suchen).

Importiert die volle Flask-App (Flask nötig). In der CI ohne diese Abhängigkeiten
überspringt sich der Test sauber. Der PDF-Parser wird gemonkeypatcht.
"""
import importlib
import io
import json
import shutil
import time
import zipfile

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}

_FAKE_TRIP = {
    "buchungsnummer": "99999999",
    "buchungsdatum": "01.02.2026",
    "reisende": [{"name": "Herr Max Mustermann", "geburtsdatum": "01.01.1980",
                  "preis": "1.000,00"}],
    "reisezeitraum": {"von": "01.05.2026", "bis": "08.05.2026"},
    "naechte": 7,
    "reiseziel": "Teststrand",
    "hotel": {"name": "Test Hotel", "code": "ABC12345"},
    "verpflegung": "All Inclusive",
    "gesamtpreis": "1.000,00", "paketpreis": "1.000,00",
    "fluege": [], "extras": [], "rabatte": [], "sonderwuensche": [],
    "anzahlung": {"betrag": None, "faelligkeit": None},
    "restzahlung": {"betrag": None, "faelligkeit": None},
    "zimmertyp": None, "zahlungsart": None,
}


@pytest.fixture
def app_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        m = importlib.import_module("app")
    except Exception as exc:  # Flask o. Ä. fehlt (z. B. CI)
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(m)
    m.DB_PATH = str(tmp_path / "tuiwatch.db")
    m.TRIPS_DIR = str(tmp_path / "trips")
    m.init_db()
    monkeypatch.setattr(m, "check_offer", lambda *a, **k: None)  # kein Netz
    monkeypatch.setattr(m, "parse_tui_pdf", lambda f: _FAKE_TRIP)
    return m


_URL = ("https://www.tui.com/pauschalreisen/suchen/angebote/Test-Hotel/12345/offer/"
        "?startDate=2027-09-01&endDate=2027-09-08&duration=7&travellers=2")


def _import_pdf(client):
    return client.post("/api/trips/import", headers=ING,
                       data={"pdf": (io.BytesIO(b"%PDF-1.4 fake"), "reise.pdf")},
                       content_type="multipart/form-data")


def test_backup_restore_roundtrip(app_mod):
    m = app_mod
    c = m.app.test_client()

    # Angebot + Verlauf + Marker + gespeicherte Suche direkt anlegen (ohne Netz)
    with m.db() as con:
        cur = con.execute(
            "INSERT INTO offers (url,label,hotel,details,target_price,booked_price,"
            "paused,archived,created) VALUES (?,?,?,?,?,?,?,?,?)",
            (_URL, "Mein Hotel", "Test Hotel", "", 900.0, 1000.0, 0, 0, int(time.time())))
        oid = cur.lastrowid
        con.execute("INSERT INTO price_history (offer_id,ts,price,ok,available) "
                    "VALUES (?,?,?,?,?)", (oid, 1000, 950.0, 1, 1))
        con.execute("INSERT INTO price_history (offer_id,ts,price,ok,available) "
                    "VALUES (?,?,?,?,?)", (oid, 2000, 900.0, 1, 1))
        con.execute("INSERT INTO offer_events (offer_id,ts,type,text) VALUES (?,?,?,?)",
                    (oid, 1500, "booked", "gebucht"))
        con.execute("INSERT INTO saved_searches (name,payload,ts) VALUES (?,?,?)",
                    ("Kanaren", json.dumps({"a": 1}), 123))
    assert _import_pdf(c).status_code == 200

    # Backup ziehen → ZIP mit data.json + PDF
    b = c.get("/api/backup", headers=ING)
    assert b.status_code == 200 and b.mimetype == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(b.data))
    names = zf.namelist()
    assert "data.json" in names
    assert any(n.startswith("trips/") and n.endswith(".pdf") for n in names)
    data = json.loads(zf.read("data.json"))
    assert len(data["offers"]) == 1
    assert len(data["offers"][0]["history"]) == 2
    assert data["offers"][0]["events"][0]["type"] == "booked"
    assert len(data["trips"]) == 1 and len(data["saved_searches"]) == 1

    # DB + PDFs leeren → frischer Zustand
    with m.db() as con:
        for tbl in ("offers", "price_history", "offer_events", "trips", "saved_searches"):
            con.execute(f"DELETE FROM {tbl}")
    shutil.rmtree(m.TRIPS_DIR, ignore_errors=True)

    # Restore aus der ZIP
    rr = c.post("/api/restore", headers=ING,
                data={"file": (io.BytesIO(b.data), "tuiwatch-backup.zip")},
                content_type="multipart/form-data")
    assert rr.status_code == 200
    jd = rr.get_json()
    assert jd["added"] == 1 and jd["trips"] == 1 and jd["searches"] == 1

    with m.db() as con:
        offs = con.execute("SELECT id,url,label,booked_price FROM offers").fetchall()
        assert len(offs) == 1 and offs[0]["url"] == _URL and offs[0]["label"] == "Mein Hotel"
        assert offs[0]["booked_price"] == 1000.0
        noid = offs[0]["id"]
        hist = con.execute("SELECT price FROM price_history WHERE offer_id=? ORDER BY ts",
                           (noid,)).fetchall()
        assert [h["price"] for h in hist] == [950.0, 900.0]
        assert con.execute("SELECT type FROM offer_events WHERE offer_id=?",
                           (noid,)).fetchone()["type"] == "booked"

    # Reise inkl. PDF wieder abrufbar
    lst = c.get("/api/trips", headers=ING).get_json()
    assert lst["stats"]["count"] == 1
    tid = lst["trips"][0]["id"]
    assert c.get(f"/api/trips/{tid}/pdf", headers=ING).status_code == 200

    # Zweiter Restore → nichts doppelt (nicht-destruktiv)
    rr2 = c.post("/api/restore", headers=ING,
                 data={"file": (io.BytesIO(b.data), "b.zip")},
                 content_type="multipart/form-data")
    assert rr2.get_json()["skipped"] == 1
    with m.db() as con:
        assert con.execute("SELECT COUNT(*) c FROM offers").fetchone()["c"] == 1
        assert con.execute("SELECT COUNT(*) c FROM trips").fetchone()["c"] == 1


def test_restore_legacy_json(app_mod):
    """Altes Format (reine Angebotsliste als JSON-Body) wird weiter akzeptiert."""
    m = app_mod
    c = m.app.test_client()
    r = c.post("/api/restore", headers=ING, json=[{"url": _URL, "label": "Alt"}])
    assert r.status_code == 200 and r.get_json()["added"] == 1
    with m.db() as con:
        assert con.execute("SELECT label FROM offers WHERE url=?", (_URL,)).fetchone()["label"] == "Alt"
