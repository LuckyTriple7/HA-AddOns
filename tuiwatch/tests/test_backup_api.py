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
    tid = _import_pdf(c).get_json()["id"]
    att = c.post(f"/api/trips/{tid}/attachments", headers=ING,
                data={"pdf": (io.BytesIO(b"%PDF-1.4 reiseplan"), "Reiseplan.pdf")},
                content_type="multipart/form-data")
    assert att.status_code == 200

    # Backup ziehen → ZIP mit data.json + PDF + Anhang
    b = c.get("/api/backup", headers=ING)
    assert b.status_code == 200 and b.mimetype == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(b.data))
    names = zf.namelist()
    assert "data.json" in names
    assert any(n.startswith("trips/") and n.endswith(".pdf") for n in names)
    assert any(n.startswith("attachments/") and n.endswith(".pdf") for n in names)
    data = json.loads(zf.read("data.json"))
    assert len(data["offers"]) == 1
    assert len(data["offers"][0]["history"]) == 2
    assert data["offers"][0]["events"][0]["type"] == "booked"
    assert len(data["trips"]) == 1 and len(data["saved_searches"]) == 1
    assert len(data["trip_attachments"]) == 1
    assert data["trip_attachments"][0]["orig_name"] == "Reiseplan.pdf"

    # DB + PDFs leeren → frischer Zustand
    with m.db() as con:
        for tbl in ("offers", "price_history", "offer_events", "trips",
                    "trip_attachments", "saved_searches"):
            con.execute(f"DELETE FROM {tbl}")
    shutil.rmtree(m.TRIPS_DIR, ignore_errors=True)

    # Restore aus der ZIP
    rr = c.post("/api/restore", headers=ING,
                data={"file": (io.BytesIO(b.data), "tuiwatch-backup.zip")},
                content_type="multipart/form-data")
    assert rr.status_code == 200
    jd = rr.get_json()
    assert jd["added"] == 1 and jd["trips"] == 1 and jd["searches"] == 1
    assert jd["attachments"] == 1

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
    detail = c.get(f"/api/trips/{tid}", headers=ING).get_json()
    assert len(detail["attachments"]) == 1
    assert detail["attachments"][0]["orig_name"] == "Reiseplan.pdf"
    aid = detail["attachments"][0]["id"]
    assert c.get(f"/api/trips/{tid}/attachments/{aid}", headers=ING).status_code == 200

    # Zweiter Restore → nichts doppelt (nicht-destruktiv)
    rr2 = c.post("/api/restore", headers=ING,
                 data={"file": (io.BytesIO(b.data), "b.zip")},
                 content_type="multipart/form-data")
    assert rr2.get_json()["skipped"] == 1
    assert rr2.get_json()["attachments"] == 0
    with m.db() as con:
        assert con.execute("SELECT COUNT(*) c FROM offers").fetchone()["c"] == 1
        assert con.execute("SELECT COUNT(*) c FROM trips").fetchone()["c"] == 1
        assert con.execute("SELECT COUNT(*) c FROM trip_attachments").fetchone()["c"] == 1


def test_restore_legacy_json(app_mod):
    """Altes Format (reine Angebotsliste als JSON-Body) wird weiter akzeptiert."""
    m = app_mod
    c = m.app.test_client()
    r = c.post("/api/restore", headers=ING, json=[{"url": _URL, "label": "Alt"}])
    assert r.status_code == 200 and r.get_json()["added"] == 1
    with m.db() as con:
        assert con.execute("SELECT label FROM offers WHERE url=?", (_URL,)).fetchone()["label"] == "Alt"


def test_auto_backup_rotation(app_mod, tmp_path, monkeypatch):
    """Auto-Backup schreibt ein gültiges ZIP nach BACKUP_DIR und rotiert alte Dateien."""
    m = app_mod
    bdir = tmp_path / "cfg_backups"
    monkeypatch.setattr(m, "BACKUP_DIR", str(bdir))
    with m.db() as con:
        con.execute(
            "INSERT INTO offers (url,label,hotel,details,paused,archived,created) "
            "VALUES (?,?,?,?,?,?,?)", (_URL, "Mein Hotel", "Test Hotel", "", 0, 0, 1))
    # 6 vorhandene Alt-Backups + 1 Fremddatei (darf die Rotation nicht anfassen)
    bdir.mkdir(parents=True)
    for i in range(6):
        (bdir / f"tuiwatch-backup-2026010{i+1}-000000.zip").write_bytes(b"alt")
    (bdir / "eigenes-backup.zip").write_bytes(b"fremd")

    m._run_auto_backup(keep=5)

    own = sorted(p.name for p in bdir.glob("tuiwatch-backup-*.zip"))
    assert len(own) == 5                      # 6 alte + 1 neues → auf 5 rotiert
    assert (bdir / "eigenes-backup.zip").exists()
    newest = max(bdir.glob("tuiwatch-backup-*.zip"), key=lambda p: p.name)
    zf = zipfile.ZipFile(io.BytesIO(newest.read_bytes()))
    data = json.loads(zf.read("data.json"))
    assert len(data["offers"]) == 1 and data["offers"][0]["url"] == _URL


def test_maybe_auto_backup_respects_interval(app_mod, tmp_path, monkeypatch):
    """_maybe_auto_backup: läuft höchstens 1×/Intervall und lässt sich abschalten."""
    m = app_mod
    bdir = tmp_path / "cfg_backups2"
    monkeypatch.setattr(m, "BACKUP_DIR", str(bdir))
    monkeypatch.setattr(m, "load_config", lambda: {"auto_backup": True, "auto_backup_keep": 5})
    m._maybe_auto_backup()
    assert len(list(bdir.glob("tuiwatch-backup-*.zip"))) == 1
    m._maybe_auto_backup()                    # Intervall nicht verstrichen → kein zweites
    assert len(list(bdir.glob("tuiwatch-backup-*.zip"))) == 1
    monkeypatch.setattr(m, "load_config", lambda: {"auto_backup": False})
    with m.db() as con:
        con.execute("DELETE FROM meta WHERE key='last_auto_backup'")
    m._maybe_auto_backup()                    # deaktiviert → nichts Neues
    assert len(list(bdir.glob("tuiwatch-backup-*.zip"))) == 1
