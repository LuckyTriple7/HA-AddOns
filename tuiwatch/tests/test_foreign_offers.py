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


def test_is_foreign_true_uses_default_list(app_mod):
    """Der alte Bool-Schalter legt in der Standardliste ab."""
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    _patch(c, oid, {"is_foreign": True})
    assert _offer(c, oid)["foreign_list"] == app_mod.FOREIGN_LIST_DEFAULT


def test_named_list_sets_flag_and_mutes(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    _patch(c, oid, {"foreign_list": "  Oma  und   Opa "})
    o = _offer(c, oid)
    assert o["foreign_list"] == "Oma und Opa"      # normalisiert
    assert o["is_foreign"] is True
    assert o["notify_muted"] is True and o["notify_calendar_muted"] is True


def test_empty_list_name_takes_offer_back(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    _patch(c, oid, {"foreign_list": "Kollegen"})
    _patch(c, oid, {"foreign_list": ""})
    o = _offer(c, oid)
    assert o["is_foreign"] is False and o["foreign_list"] == ""
    assert o["notify_muted"] is True               # Glocken bleiben stumm


def test_is_foreign_true_keeps_existing_list(app_mod):
    """Erneutes Markieren darf ein Angebot nicht aus seiner Liste reißen."""
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    _patch(c, oid, {"foreign_list": "Kollegen"})
    _patch(c, oid, {"is_foreign": True})
    assert _offer(c, oid)["foreign_list"] == "Kollegen"


def test_several_lists_side_by_side(app_mod):
    c = app_mod.app.test_client()
    a = _add_offer(c)
    r = c.post("/api/offers", headers=ING,
               json={"url": _URL.replace("12345", "67890")})
    assert r.status_code == 200
    b = r.get_json()["id"]
    _patch(c, a, {"foreign_list": "Oma"})
    _patch(c, b, {"foreign_list": "Kollegen"})
    lists = c.get("/api/foreign-lists", headers=ING).get_json()["lists"]
    assert lists == [{"name": "Kollegen", "count": 1}, {"name": "Oma", "count": 1}]


def test_rename_list(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    _patch(c, oid, {"foreign_list": "Oma"})
    r = c.post("/api/foreign-lists/rename", headers=ING,
               json={"from": "Oma", "to": "Oma und Opa"})
    assert r.status_code == 200 and r.get_json()["moved"] == 1
    assert _offer(c, oid)["foreign_list"] == "Oma und Opa"


def test_rename_unknown_list_is_404(app_mod):
    c = app_mod.app.test_client()
    r = c.post("/api/foreign-lists/rename", headers=ING,
               json={"from": "Gibts nicht", "to": "Egal"})
    assert r.status_code == 404


def test_dissolve_list_frees_offers(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    _patch(c, oid, {"foreign_list": "Kollegen"})
    r = c.delete("/api/foreign-lists/Kollegen", headers=ING)
    assert r.status_code == 200 and r.get_json()["freed"] == 1
    o = _offer(c, oid)
    assert o["is_foreign"] is False and o["foreign_list"] == ""
    assert c.get("/api/foreign-lists", headers=ING).get_json()["lists"] == []


def test_migration_names_existing_foreign_offers(app_mod):
    """Bestand aus der Ein-Listen-Zeit bekommt den bisherigen Anzeigenamen."""
    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("ALTER TABLE offers RENAME TO offers_old")
    con.execute("CREATE TABLE offers (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "url TEXT UNIQUE NOT NULL, is_foreign INTEGER NOT NULL DEFAULT 0, "
                "created INTEGER NOT NULL)")
    con.execute("INSERT INTO offers (url, created, is_foreign) VALUES (?, 1, 1)",
                (_URL,))
    con.commit()
    con.close()

    app_mod.init_db()

    con = sqlite3.connect(app_mod.DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT is_foreign, foreign_list FROM offers WHERE url=?",
                      (_URL,)).fetchone()
    con.close()
    assert row["is_foreign"] == 1
    assert row["foreign_list"] == app_mod.FOREIGN_LIST_DEFAULT


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
