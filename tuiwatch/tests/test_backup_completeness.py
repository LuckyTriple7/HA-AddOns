"""Backup/Restore-Roundtrip mit Vergleich der Tabelleninhalte vor und nach dem
Restore.

`test_backup_api.py` prüft, dass ein Roundtrip grundsätzlich läuft. Hier geht es um
die Vollständigkeit: Ein Backup, das sich „vollständig" nennt, darf keine Spalte und
keine nutzerverwaltete Tabelle stillschweigend fallen lassen. Genau das war lange
der Fall — Suchabos verloren ihre Schwelle, der Preisverlauf seinen Preis-Split, der
KI-Verlauf seine Angebots-Zuordnung, und Klimatabellen, Reiseführer, Share-Links und
deren Kommentare fehlten ganz.

Der Aufbau ist bewusst „befüllen → sichern → in eine leere DB spielen → vergleichen",
nicht „prüfe Feld X" — so fällt auch eine künftig neu hinzugefügte Spalte auf, statt
erst beim Nutzer.
"""
import importlib
import io
import json
import time
import zipfile

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}

_URL = ("https://www.tui.com/pauschalreisen/suchen/angebote/Test-Hotel/12345/offer/"
        "?startDate=2027-09-01&endDate=2027-09-08&duration=7&travellers=2")

_FAKE_TRIP = {
    "buchungsnummer": "", "buchungsdatum": "01.02.2026",
    "reisende": [{"name": "Herr Max Mustermann", "geburtsdatum": "01.01.1980",
                  "preis": "1.000,00"}],
    "reisezeitraum": {"von": "01.05.2026", "bis": "08.05.2026"},
    "naechte": 7, "reiseziel": "Teststrand",
    "hotel": {"name": "Test Hotel", "code": "ABC12345"},
    "verpflegung": "All Inclusive",
    "gesamtpreis": "1.000,00", "paketpreis": "1.000,00",
    "fluege": [], "extras": [], "rabatte": [], "sonderwuensche": [],
    "anzahlung": {"betrag": None, "faelligkeit": None},
    "restzahlung": {"betrag": None, "faelligkeit": None},
    "zimmertyp": None, "zahlungsart": None,
}


def _make_app(tmp_path, monkeypatch, sub):
    """Eigene App-Instanz mit eigener DB — Quelle und Ziel des Roundtrips."""
    root = tmp_path / sub
    root.mkdir()
    monkeypatch.setenv("TUIWATCH_DATA", str(root))
    monkeypatch.setenv("TUIWATCH_BASE", str(root))
    m = importlib.import_module("app")
    importlib.reload(m)
    m.DB_PATH = str(root / "tuiwatch.db")
    m.TRIPS_DIR = str(root / "trips")
    m.init_db()
    monkeypatch.setattr(m, "check_offer", lambda *a, **k: None)
    monkeypatch.setattr(m, "parse_tui_pdf", lambda f: _FAKE_TRIP)
    return m


@pytest.fixture
def source(tmp_path, monkeypatch):
    try:
        return _make_app(tmp_path, monkeypatch, "src")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")


def _fill(m):
    """Jede nutzerverwaltete Tabelle mit einem unterscheidbaren Datensatz füllen."""
    c = m.app.test_client()
    with m.db() as con:
        oid = con.execute(
            "INSERT INTO offers (url, label, hotel, created) VALUES (?,?,?,?)",
            (_URL, "Mein Hotel", "Test Hotel", int(time.time()))).lastrowid
        # Preisverlauf inkl. Preis-Split und Verfügbarkeitsprüfung
        con.execute(
            "INSERT INTO price_history (offer_id, ts, price, old_price, discount, available, "
            "ok, note, price_hotel, price_flight_out, price_flight_ret, vac_ok) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (oid, 1000, 900.0, 950.0, 5, 1, 1, "Notiz", 600.0, 180.0, 120.0, 1))
        # Suchabo mit Schwelle und gemeldeten Hotels
        con.execute(
            "INSERT INTO saved_searches (name, payload, ts, watch, max_price, last_checked, "
            "seen, hits) VALUES (?,?,?,?,?,?,?,?)",
            ("Kanaren", json.dumps({"a": 1}), 123, 1, 799.0, 4711,
             json.dumps({"12345": 750}), json.dumps([{"giata": 12345}])))
        # KI-Verlauf mit Angebots-Zuordnung
        con.execute(
            "INSERT INTO ai_analyses (kind, title, model, summary, usage, ts, prompt, "
            "offer_id) VALUES (?,?,?,?,?,?,?,?)",
            ("score", "Buchungsscore", "sonar-pro", "Text", "{}", 900, "P", oid))
        con.execute("INSERT INTO climate (giata, label, ts, model, data) VALUES (?,?,?,?,?)",
                    (12345, "Gran Canaria", 800, "sonar-pro", json.dumps({"months": []})))
        con.execute("INSERT INTO guide (giata, label, ts, model, data) VALUES (?,?,?,?,?)",
                    (12345, "Gran Canaria", 810, "sonar-pro", json.dumps({"sections": []})))
        con.execute(
            "INSERT INTO shares (token, title, note, payload, created_ts, expires_ts, views, "
            "comments_seen_ts, comments_enabled) VALUES (?,?,?,?,?,?,?,?,?)",
            ("tok123", "Mein Link", "Notiz", json.dumps({"x": 1}), 700, 99999, 3, 0, 1))
        con.execute(
            "INSERT INTO share_comments (token, author, text, ts, ip) VALUES (?,?,?,?,?)",
            ("tok123", "Oma", "Schön dort!", 750, "1.2.3.4"))
    # Reise ohne Buchungsnummer (_FAKE_TRIP) + Anhang + Packlisten-Eintrag
    tid = c.post("/api/trips/import", headers=ING,
                 data={"pdf": (io.BytesIO(b"%PDF-1.4 fake"), "reise.pdf")},
                 content_type="multipart/form-data").get_json()["id"]
    assert c.post(f"/api/trips/{tid}/attachments", headers=ING,
                  data={"pdf": (io.BytesIO(b"%PDF-1.4 plan"), "Reiseplan.pdf")},
                  content_type="multipart/form-data").status_code == 200
    with m.db() as con:
        assert not (con.execute("SELECT booking_code FROM trips WHERE id=?",
                                (tid,)).fetchone()["booking_code"] or ""), \
            "Testvoraussetzung: Reise ohne Buchungsnummer"
        con.execute("INSERT INTO trip_packing_items (trip_id, category, label, checked, created) "
                    "VALUES (?,?,?,?,?)", (tid, "Doks", "Reisepass", 1, 600))


def _snapshot(m):
    """Vergleichbarer Abzug aller nutzerverwalteten Tabellen — ohne die IDs, die
    beim Restore zwangsläufig neu vergeben werden."""
    out = {}
    with m.db() as con:
        out['price_history'] = [dict(r) for r in con.execute(
            "SELECT ts, price, old_price, discount, available, ok, note, price_hotel, "
            "price_flight_out, price_flight_ret, vac_ok FROM price_history ORDER BY ts")]
        out['saved_searches'] = [dict(r) for r in con.execute(
            "SELECT name, payload, ts, watch, max_price, last_checked, seen, hits "
            "FROM saved_searches ORDER BY name")]
        out['climate'] = [dict(r) for r in con.execute(
            "SELECT giata, label, ts, model, data FROM climate ORDER BY giata")]
        out['guide'] = [dict(r) for r in con.execute(
            "SELECT giata, label, ts, model, data FROM guide ORDER BY giata")]
        out['shares'] = [dict(r) for r in con.execute(
            "SELECT token, title, note, payload, created_ts, expires_ts, views, "
            "comments_seen_ts, comments_enabled FROM shares ORDER BY token")]
        out['share_comments'] = [dict(r) for r in con.execute(
            "SELECT token, author, text, ts, ip FROM share_comments ORDER BY ts")]
        out['trip_packing_items'] = [dict(r) for r in con.execute(
            "SELECT category, label, checked FROM trip_packing_items ORDER BY label")]
        out['trip_attachments'] = [dict(r) for r in con.execute(
            "SELECT filename, orig_name FROM trip_attachments ORDER BY filename")]
        # KI-Verlauf samt Angebot, an dem er hängt (die id selbst ändert sich)
        out['ai_analyses'] = [dict(r) for r in con.execute(
            "SELECT ai_analyses.kind, ai_analyses.title, ai_analyses.model, "
            "ai_analyses.summary, ai_analyses.ts, offers.url AS offer_url "
            "FROM ai_analyses LEFT JOIN offers ON offers.id = ai_analyses.offer_id "
            "ORDER BY ai_analyses.ts")]
    return out


def test_roundtrip_preserves_every_user_managed_table(source, tmp_path, monkeypatch):
    _fill(source)
    before = _snapshot(source)
    blob = source.app.test_client().get("/api/backup", headers=ING).data
    assert zipfile.ZipFile(io.BytesIO(blob)).read("data.json")

    target = _make_app(tmp_path, monkeypatch, "dst")
    r = target.app.test_client().post(
        "/api/restore", headers=ING,
        data={"file": (io.BytesIO(blob), "backup.zip")},
        content_type="multipart/form-data")
    assert r.status_code == 200, r.data

    after = _snapshot(target)
    for table in sorted(before):
        assert after[table] == before[table], f"{table} kam nicht unverändert zurück"


def test_backup_declares_the_new_schema_version(source):
    """Ein Backup mit den zusätzlichen Tabellen muss sich auch als solches ausweisen,
    sonst kann ein künftiger Restore die Formate nicht auseinanderhalten."""
    blob = source.app.test_client().get("/api/backup", headers=ING).data
    data = json.loads(zipfile.ZipFile(io.BytesIO(blob)).read("data.json"))
    assert data["tuiwatch_backup"] == 8
    for key in ("climate", "guide", "shares", "share_comments"):
        assert key in data, f"{key} fehlt im Backup"


def test_restore_keeps_a_running_watch_untouched(source, tmp_path, monkeypatch):
    """Nicht-destruktiv: ein hier bereits laufendes Abo darf sein `seen` nicht aus
    einem älteren Backup überschrieben bekommen — sonst meldet es längst gemeldete
    Hotels erneut."""
    _fill(source)
    blob = source.app.test_client().get("/api/backup", headers=ING).data

    target = _make_app(tmp_path, monkeypatch, "dst2")
    with target.db() as con:
        con.execute("INSERT INTO saved_searches (name, payload, ts, watch, max_price, seen) "
                    "VALUES (?,?,?,?,?,?)",
                    ("Kanaren", "{}", 1, 1, 555.0, json.dumps({"999": 500})))
    target.app.test_client().post(
        "/api/restore", headers=ING,
        data={"file": (io.BytesIO(blob), "backup.zip")},
        content_type="multipart/form-data")
    with target.db() as con:
        row = con.execute("SELECT max_price, seen FROM saved_searches WHERE name=?",
                          ("Kanaren",)).fetchone()
    assert row["max_price"] == 555.0
    assert json.loads(row["seen"]) == {"999": 500}


def test_restore_adopts_the_watch_when_none_is_running(source, tmp_path, monkeypatch):
    """Umgekehrt: auf einer frischen Installation muss das Abo aus dem Backup
    ankommen, sonst ist es nach einem Restore stillschweigend aus."""
    _fill(source)
    blob = source.app.test_client().get("/api/backup", headers=ING).data

    target = _make_app(tmp_path, monkeypatch, "dst3")
    target.app.test_client().post(
        "/api/restore", headers=ING,
        data={"file": (io.BytesIO(blob), "backup.zip")},
        content_type="multipart/form-data")
    with target.db() as con:
        row = con.execute("SELECT watch, max_price, seen FROM saved_searches WHERE name=?",
                          ("Kanaren",)).fetchone()
    assert row["watch"] == 1 and row["max_price"] == 799.0
    assert json.loads(row["seen"]) == {"12345": 750}


def test_old_backup_without_the_new_keys_still_restores(source, tmp_path, monkeypatch):
    """Version 7 kannte weder die neuen Tabellen noch `trip_ref` — so ein Backup muss
    weiterhin einspielbar sein, nur eben ohne die fehlenden Teile."""
    old = {"tuiwatch_backup": 7, "offers": [{"url": _URL, "label": "Alt",
                                             "history": [{"ts": 1, "price": 100.0, "ok": 1}]}],
           "trips": [], "saved_searches": [{"name": "Alt", "payload": "{}", "ts": 5}]}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("data.json", json.dumps(old))

    target = _make_app(tmp_path, monkeypatch, "dst4")
    r = target.app.test_client().post(
        "/api/restore", headers=ING,
        data={"file": (io.BytesIO(buf.getvalue()), "backup.zip")},
        content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.get_json()["added"] == 1
    with target.db() as con:
        row = con.execute("SELECT price, price_hotel, vac_ok FROM price_history").fetchone()
    assert row["price"] == 100.0
    assert row["price_hotel"] is None and row["vac_ok"] is None
