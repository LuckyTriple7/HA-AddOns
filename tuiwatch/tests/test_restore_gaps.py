"""Luecken, die eine Wiederherstellung bis 0.113.6 still verschluckt hat.

1. Die Zuordnung eines Angebots zu einer „Fuer andere“-Liste (`is_foreign`,
   `foreign_list`, `foreign_icon`) sowie `history_only` und die Stummschalter
   standen zwar im Backup, fehlten aber in `_OFFER_RESTORE_COLS` — die Angebote
   kamen zurueck, ihre Einsortierung nicht.
2. Einstellungen wurden nur uebernommen, wenn noch keine `settings.json` existierte.
   Da `migrate()` die Datei beim ersten Start immer anlegt, war das auf einer
   frischen Installation nie der Fall; gemeldet wurde der Uebersprung auch nicht.
3. Der Schluessel liess sich nicht zusammen mit dem Backup sichern — ohne ihn sind
   die geheimen Felder aus `settings.json` auf einem anderen System unlesbar.
"""
import importlib
import io
import json
import zipfile

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}
_URL = ("https://www.tui.com/pauschalreisen/suchen/angebote/Test-Hotel/12345/offer/"
        "?startDate=2027-09-01&endDate=2027-09-08&duration=7&travellers=2")


@pytest.fixture
def app_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    # Der Schluessel-Export verlangt das Login-Passwort zur Bestaetigung; ohne
    # options.json liest `_key_gate_check` einen leeren String und lehnt alles ab.
    (tmp_path / "options.json").write_text(
        json.dumps({"username": "admin", "password": "secret", "session_hours": 24}),
        encoding="utf-8")
    try:
        m = importlib.import_module("app")
    except Exception as exc:                     # pragma: no cover
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(m)
    m.DB_PATH = str(tmp_path / "tuiwatch.db")
    m.init_db()
    monkeypatch.setattr(m, "check_offer", lambda *a, **k: None)   # kein Netz
    return m


def _backup(c):
    r = c.get("/api/backup", headers=ING)
    assert r.status_code == 200
    return r.data


def _restore(c, blob, **fields):
    data = {"file": (io.BytesIO(blob), "backup.zip")}
    data.update(fields)
    r = c.post("/api/restore", headers=ING, data=data,
               content_type="multipart/form-data")
    assert r.status_code == 200, r.data
    return r.get_json()


# ── 1. Listen-Zuordnung ───────────────────────────────────────────────────────

def test_foreign_list_survives_restore(app_mod):
    m = app_mod
    c = m.app.test_client()
    with m.db() as con:
        con.execute(
            "INSERT INTO offers (url, label, hotel, is_foreign, foreign_list, "
            "foreign_icon, history_only, notify_muted, created) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (_URL, "Test", "Test Hotel", 1, "Familie Mueller", "🏖️", 1, 1, 1750000000))
    blob = _backup(c)

    with m.db() as con:                          # frische Datenbank simulieren
        con.execute("DELETE FROM offers")
    assert _restore(c, blob)["added"] == 1

    with m.db() as con:
        row = con.execute(
            "SELECT is_foreign, foreign_list, foreign_icon, history_only, notify_muted "
            "FROM offers WHERE url=?", (_URL,)).fetchone()
    assert row["foreign_list"] == "Familie Mueller"
    assert row["foreign_icon"] == "🏖️"
    assert row["is_foreign"] == 1
    assert row["history_only"] == 1
    assert row["notify_muted"] == 1


def test_foreign_flag_follows_list_name(app_mod):
    """Schema-Invariante: is_foreign=1 <=> foreign_list<>'' — auch aus dem Backup."""
    m = app_mod
    c = m.app.test_client()
    with m.db() as con:
        con.execute(
            "INSERT INTO offers (url, hotel, is_foreign, foreign_list, foreign_icon, created) "
            "VALUES (?,?,?,?,?,?)", (_URL, "Test Hotel", 1, "", "👥", 1750000000))
    blob = _backup(c)
    with m.db() as con:
        con.execute("DELETE FROM offers")
    _restore(c, blob)
    with m.db() as con:
        row = con.execute("SELECT is_foreign, foreign_icon FROM offers WHERE url=?",
                          (_URL,)).fetchone()
    assert row["is_foreign"] == 0
    assert row["foreign_icon"] == ""


# ── 2. Einstellungen ──────────────────────────────────────────────────────────

def test_settings_skipped_is_reported_and_overridable(app_mod, tmp_path):
    m = app_mod
    c = m.app.test_client()
    m.settings_store.save({"poll_interval": 12345})
    blob = _backup(c)

    m.settings_store.save({"poll_interval": 999})
    assert m.settings_store.load()["poll_interval"] == 999

    res = _restore(c, blob)
    assert res["options_skipped"] is True        # bis 0.113.6 still verschluckt
    assert res["options_restored"] is False
    assert m.settings_store.load()["poll_interval"] == 999

    res = _restore(c, blob, replace_settings="1")
    assert res["options_restored"] is True
    assert res["options_skipped"] is False
    assert m.settings_store.load()["poll_interval"] == 12345


def test_settings_restored_when_absent(app_mod):
    m = app_mod
    c = m.app.test_client()
    m.settings_store.save({"poll_interval": 4242})
    blob = _backup(c)

    import os
    os.remove(m.settings_store.path())
    m.settings_store.reset_cache()

    assert _restore(c, blob)["options_restored"] is True
    assert m.settings_store.load()["poll_interval"] == 4242


# ── 3. Schluessel im Backup ───────────────────────────────────────────────────

def test_backup_with_key_roundtrip(app_mod):
    m = app_mod
    c = m.app.test_client()
    m.settings_store.save({"telegram_bot_token": "geheim-123"})
    assert m.settings_store.key_exists()

    r = c.post("/api/backup", headers=ING,
               json={"passphrase": "passphrase-lang", "password": "secret"})
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.data)).namelist()
    assert "settings.key.json" in names and "settings.json" in names

    # Frische Installation: Schluessel und Einstellungen weg
    import os
    os.remove(m.settings_store.key_path())
    os.remove(m.settings_store.path())
    m.settings_store.reset_cache()

    res = _restore(c, r.data, passphrase="passphrase-lang", password="secret")
    assert res["key_restored"] is True
    assert res["options_restored"] is True
    assert m.settings_store.load()["telegram_bot_token"] == "geheim-123"


def test_backup_with_key_needs_password(app_mod):
    m = app_mod
    c = m.app.test_client()
    m.settings_store.save({"telegram_bot_token": "geheim-123"})
    r = c.post("/api/backup", headers=ING,
               json={"passphrase": "passphrase-lang", "password": "falsch"})
    assert r.status_code == 403


def test_plain_backup_has_no_key(app_mod):
    m = app_mod
    c = m.app.test_client()
    m.settings_store.save({"telegram_bot_token": "geheim-123"})
    assert "settings.key.json" not in zipfile.ZipFile(io.BytesIO(_backup(c))).namelist()


def test_wrong_passphrase_leaves_key_alone(app_mod):
    m = app_mod
    c = m.app.test_client()
    m.settings_store.save({"telegram_bot_token": "geheim-123"})
    r = c.post("/api/backup", headers=ING,
               json={"passphrase": "passphrase-lang", "password": "secret"})
    before = open(m.settings_store.key_path(), "rb").read()

    res = _restore(c, r.data, passphrase="falsche-passphrase", password="secret")
    assert res["key_restored"] is False
    assert res["key_error"] == "wrong_passphrase"
    assert open(m.settings_store.key_path(), "rb").read() == before
