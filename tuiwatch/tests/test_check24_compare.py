"""Tests für POST/GET /api/check24/<id> — Job-Start, Cooldown, Feature-Flag-Gate,
Reset/Delete löscht Cache+State. _run_check24_compare wird gemonkeypatcht (kein
Netz/Playwright); die Route-/Job-Verdrahtung selbst wird getestet, nicht der
tatsächliche Check24-Abruf (siehe test_check24_client.py für die Parsing-Logik)."""
import importlib

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}
_URL = "https://www.tui.com/pauschalreisen/suchen/angebote/Test-Hotel/12345/offer/"
_C24_URL = ("https://urlaub.check24.de/suche/hotel?airport=STR&transportType=flight"
            "&roomAllocation=A&departureDate=2027-04-28&returnDate=2027-05-09&days=exact"
            "&pageArea=package&areaId=551&dhs=11829&ds=h&hotelId=11829")


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


def _add_offer(c, link=None):
    r = c.post("/api/offers", headers=ING, json={"url": _URL})
    assert r.status_code == 200
    oid = r.get_json()["id"]
    if link:
        c.patch(f"/api/offers/{oid}", headers=ING, json={"check24_link": link})
    return oid


def _enable(app_mod, monkeypatch):
    cfg = dict(app_mod.load_config())
    cfg['enable_check24_compare'] = True
    monkeypatch.setattr(app_mod, "load_config", lambda: cfg)


def test_start_when_disabled_returns_404(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c, _C24_URL)
    r = c.post(f"/api/check24/{oid}", headers=ING)
    assert r.status_code == 404
    assert r.get_json()["error"] == "disabled"


def test_start_when_unlinked_returns_409(app_mod, monkeypatch):
    _enable(app_mod, monkeypatch)
    c = app_mod.app.test_client()
    oid = _add_offer(c)  # kein Check24-Link
    r = c.post(f"/api/check24/{oid}", headers=ING)
    assert r.status_code == 409
    assert r.get_json()["error"] == "not_linked"


def test_start_unknown_offer_returns_404(app_mod, monkeypatch):
    _enable(app_mod, monkeypatch)
    c = app_mod.app.test_client()
    r = c.post("/api/check24/999999", headers=ING)
    assert r.status_code == 404
    assert r.get_json()["error"] == "not_found"


def test_start_runs_then_get_returns_done(app_mod, monkeypatch):
    _enable(app_mod, monkeypatch)
    c = app_mod.app.test_client()
    oid = _add_offer(c, _C24_URL)

    def fake_run(offer_id):
        with app_mod.db() as con:
            con.execute("INSERT OR REPLACE INTO check24_cache (offer_id, ts, rows) "
                        "VALUES (?,?,?)", (offer_id, 12345, '[{"room":"DZ","board":"AI","price":999.0}]'))
        with app_mod._check24_lock:
            app_mod._check24_state.pop(offer_id, None)
    monkeypatch.setattr(app_mod, "_spawn", lambda fn, *a: fake_run(*a))

    r = c.post(f"/api/check24/{oid}", headers=ING)
    assert r.status_code == 200 and r.get_json()["started"] is True

    g = c.get(f"/api/check24/{oid}", headers=ING).get_json()
    assert g["status"] == "done"
    assert g["rows"][0]["price"] == 999.0


def test_repeat_post_within_cooldown_returns_429(app_mod, monkeypatch):
    _enable(app_mod, monkeypatch)
    c = app_mod.app.test_client()
    oid = _add_offer(c, _C24_URL)
    monkeypatch.setattr(app_mod, "_spawn", lambda fn, *a: None)  # Job bleibt "running"

    r1 = c.post(f"/api/check24/{oid}", headers=ING)
    assert r1.status_code == 200
    with app_mod._check24_lock:  # Job manuell beenden, um den Cooldown isoliert zu testen
        app_mod._check24_state.pop(oid, None)
    r2 = c.post(f"/api/check24/{oid}", headers=ING)
    assert r2.status_code == 429
    assert r2.get_json()["retry_after"] > 0


def test_reset_clears_check24_cache_and_state(app_mod, monkeypatch):
    _enable(app_mod, monkeypatch)
    c = app_mod.app.test_client()
    oid = _add_offer(c, _C24_URL)
    with app_mod.db() as con:
        con.execute("INSERT INTO check24_cache (offer_id, ts, rows) VALUES (?,?,?)",
                    (oid, 1, "[]"))
    with app_mod._check24_lock:
        app_mod._check24_state[oid] = {'status': 'error', 'note': 'x'}
    r = c.post(f"/api/reset/{oid}", headers=ING)
    assert r.status_code == 200
    with app_mod.db() as con:
        row = con.execute("SELECT 1 FROM check24_cache WHERE offer_id=?", (oid,)).fetchone()
    assert row is None
    with app_mod._check24_lock:
        assert oid not in app_mod._check24_state


def test_delete_clears_check24_cache(app_mod, monkeypatch):
    _enable(app_mod, monkeypatch)
    c = app_mod.app.test_client()
    oid = _add_offer(c, _C24_URL)
    with app_mod.db() as con:
        con.execute("INSERT INTO check24_cache (offer_id, ts, rows) VALUES (?,?,?)",
                    (oid, 1, "[]"))
    assert c.delete(f"/api/offers/{oid}", headers=ING).status_code == 200
    with app_mod.db() as con:
        row = con.execute("SELECT 1 FROM check24_cache WHERE offer_id=?", (oid,)).fetchone()
    assert row is None
