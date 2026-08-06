"""Tests für „für andere"-Angebote (`is_foreign`).

Angebote, die nicht für den Nutzer selbst sind, sollen weiter getrackt werden,
aber nicht mehr melden: das Markieren schaltet beide Glocken stumm. Das
Zurücknehmen darf sie NICHT von selbst wieder einschalten — sonst überschreibt es
eine womöglich absichtliche Stummschaltung.
"""
import importlib
import sqlite3

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}
_URL = "https://www.tui.com/pauschalreisen/suchen/angebote/Test-Hotel/12345/offer/"


@pytest.fixture
def app_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        m = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(m)
    m.DB_PATH = str(tmp_path / "tuiwatch.db")
    m.init_db()
    monkeypatch.setattr(m, "check_offer", lambda *a, **k: None)  # kein Netz
    return m


def _add_offer(c):
    r = c.post("/api/offers", headers=ING, json={"url": _URL})
    assert r.status_code == 200
    return r.get_json()["id"]


def _offer(c, oid):
    offers = c.get("/api/offers", headers=ING).get_json()["offers"]
    return next(o for o in offers if o["id"] == oid)


def _patch(c, oid, body):
    r = c.patch(f"/api/offers/{oid}", headers=ING, json=body)
    assert r.status_code == 200, r.get_data(as_text=True)


def test_offer_starts_as_own(app_mod):
    c = app_mod.app.test_client()
    o = _offer(c, _add_offer(c))
    assert o["is_foreign"] is False
    assert o["notify_muted"] is False and o["notify_calendar_muted"] is False


def test_marking_foreign_mutes_both_bells(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    _patch(c, oid, {"is_foreign": True})
    o = _offer(c, oid)
    assert o["is_foreign"] is True
    assert o["notify_muted"] is True and o["notify_calendar_muted"] is True


def test_unmarking_leaves_bells_muted(app_mod):
    """Kein Auto-Einschalten: das würde eine bewusste Stummschaltung überfahren."""
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    _patch(c, oid, {"is_foreign": True})
    _patch(c, oid, {"is_foreign": False})
    o = _offer(c, oid)
    assert o["is_foreign"] is False
    assert o["notify_muted"] is True and o["notify_calendar_muted"] is True


def test_bells_can_be_switched_on_again(app_mod):
    """Manuelles Einschalten muss auch bei einem fremden Angebot funktionieren."""
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    _patch(c, oid, {"is_foreign": True})
    _patch(c, oid, {"notify_muted": False})
    _patch(c, oid, {"notify_calendar_muted": False})
    o = _offer(c, oid)
    assert o["is_foreign"] is True          # Markierung bleibt
    assert o["notify_muted"] is False and o["notify_calendar_muted"] is False


def test_marking_does_not_touch_other_fields(app_mod):
    """Tracking, Tags und Wunschpreis bleiben unberührt — nur die Glocken ändern sich."""
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    _patch(c, oid, {"tags": ["Oma"], "target_price": 1800})
    _patch(c, oid, {"is_foreign": True})
    o = _offer(c, oid)
    assert o["tags"] == ["Oma"] and o["target_price"] == 1800
    assert o["paused"] is False and o["archived"] is False


def test_migration_adds_column_to_old_db(app_mod, tmp_path):
    """Bestandsdatenbanken ohne die Spalte bekommen sie beim Start — bestehende
    Angebote bleiben dabei „eigene" (Default 0)."""
    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("ALTER TABLE offers RENAME TO offers_old")
    con.execute("CREATE TABLE offers (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "url TEXT UNIQUE NOT NULL, created INTEGER NOT NULL)")
    con.execute("INSERT INTO offers (url, created) VALUES (?, 1)", (_URL,))
    con.commit()
    con.close()

    app_mod.init_db()

    con = sqlite3.connect(app_mod.DB_PATH)
    con.row_factory = sqlite3.Row
    cols = {r["name"] for r in con.execute("PRAGMA table_info(offers)").fetchall()}
    assert "is_foreign" in cols
    row = con.execute("SELECT is_foreign FROM offers WHERE url=?", (_URL,)).fetchone()
    con.close()
    assert row["is_foreign"] == 0
