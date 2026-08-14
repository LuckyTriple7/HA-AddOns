"""Tests für den Zeitplan der Hintergrund-Aufgaben (GET /api/schedule,
Rechtsklick aufs Logo)."""
import importlib
import time

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}
_URL = "https://www.tui.com/pauschalreisen/suchen/angebote/Test-Hotel/12345/offer/"


@pytest.fixture
def m(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        mod = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(mod)
    mod.DB_PATH = str(tmp_path / "tuiwatch.db")
    mod.init_db()
    monkeypatch.setattr(mod, "check_offer", lambda *a, **k: None)  # kein Netz
    return mod


def _tasks(m):
    d = m.app.test_client().get("/api/schedule", headers=ING).get_json()
    return d, {t["key"]: t for t in d["tasks"]}


def test_schedule_liefert_alle_aufgaben(m):
    d, by_key = _tasks(m)
    assert set(by_key) == {"prices", "watches", "calendar", "basket", "aktion",
                           "health", "backup", "digest", "flights"}
    assert d["poll_interval"] >= m.MIN_POLL_INTERVAL
    assert d["poll_gap"] == m.POLL_GAP_DEFAULT


def test_ohne_angebote_nichts_geplant(m):
    _, by_key = _tasks(m)
    assert by_key["prices"]["next"] is None
    assert by_key["watches"]["next"] is None


def test_neues_angebot_ist_sofort_faellig(m):
    c = m.app.test_client()
    assert c.post("/api/offers", headers=ING, json={"url": _URL}).status_code == 200
    _, by_key = _tasks(m)
    assert by_key["prices"]["next"] == 0          # kein Messpunkt → sofort dran
    assert "1 aktiv" in by_key["prices"]["note"]


def test_geprueftes_angebot_erst_nach_intervall(m):
    c = m.app.test_client()
    oid = c.post("/api/offers", headers=ING, json={"url": _URL}).get_json()["id"]
    now = int(time.time())
    with m.db() as con:
        con.execute("INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,1)",
                    (oid, now, 1000.0))
    d, by_key = _tasks(m)
    assert by_key["prices"]["next"] == now + d["poll_interval"]


def test_abgeschaltete_aufgaben_werden_markiert(m, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: {"auto_backup": False,
                                                   "calendar_daily_refresh": False,
                                                   "digest_enabled": False})
    _, by_key = _tasks(m)
    for key in ("backup", "calendar", "digest", "flights"):
        assert by_key[key]["disabled"] is True
        assert by_key[key]["next"] is None


def test_flugplaene_zeigen_aktive_flughaefen(m, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: {"enable_str_flights": True,
                                                   "enable_muc_flights": True})
    _, by_key = _tasks(m)
    assert by_key["flights"].get("disabled") is not True
    assert by_key["flights"]["note"] == "STR/MUC aktiv"
    assert by_key["flights"]["next"] is not None


def test_sortierung_faellige_zuerst_ungeplante_zuletzt(m):
    d, _ = _tasks(m)
    keys = [(t.get("next") is None, t.get("next") or 0) for t in d["tasks"]]
    assert keys == sorted(keys)


def test_dur_klartext(m):
    assert m._dur(21600) == "6 h"
    assert m._dur(1800) == "30 min"
    assert m._dur(86400) == "1 Tag"
    assert m._dur(7 * 86400) == "7 Tage"
