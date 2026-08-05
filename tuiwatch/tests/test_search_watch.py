"""Tests für das Suchabo (gespeicherte Suche beobachten, Sammel-Alarm).

Die TUI-Suche wird gemonkeypatcht (kein Netz); geprüft werden Schwellen-Logik,
Nachfilter, Dedup über `seen` (neu / weiter gefallen / Wiederkehr) und die API-Routen.
"""
import importlib

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}

_PAYLOAD = {"dest": {"giata": 123, "label": "Kanaren"}, "airport": "DUS",
            "vom": "2027-03-01", "bis": "2027-03-15", "dur": 7, "exact": False,
            "trav": 2, "tui": True, "direct": False, "boards": ["AI"],
            "location": [9], "airlines": [], "stars": 4, "rec": 0}


def _result(giata, name, price, stars=5):
    return {"giata": giata, "name": name, "price": price, "stars": stars,
            "recommendation": 95, "reviews": 100, "location": "Playa, Gran Canaria",
            "country": "Spanien", "board": "All Inclusive", "nights": 7,
            "date": "2027-03-04", "image": "", "offer_url": "https://www.tui.com/x"}


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
    mod.TRIPS_DIR = str(tmp_path / "trips")
    mod.init_db()
    mod._tg = []
    monkeypatch.setattr(mod, "_notify_telegram", lambda t: mod._tg.append(t))
    monkeypatch.setattr(mod, "_notify_ha", lambda *a, **k: None)
    return mod


def _mk_watch(m, c, max_price=1000):
    r = c.post("/api/searches", headers=ING,
               json={"name": "Kanaren AI", "payload": _PAYLOAD})
    sid = r.get_json()["id"]
    assert c.patch(f"/api/searches/{sid}", headers=ING,
                   json={"watch": True, "max_price": max_price}).status_code == 200
    return sid


def _fake_search(m, monkeypatch, results):
    calls = {}

    def fake(**kw):
        calls.update(kw)
        return {"ok": True, "total": len(results), "results": list(results)}
    monkeypatch.setattr(m, "fetch_search_params", fake)
    return calls


def test_watch_threshold_filter_and_dedup(m, monkeypatch):
    c = m.app.test_client()
    sid = _mk_watch(m, c)
    # Hotel A unter Schwelle, B darüber, C unter Schwelle aber zu wenige Sterne
    calls = _fake_search(m, monkeypatch, [
        _result(1, "Hotel A", 900), _result(2, "Hotel B", 1200),
        _result(3, "Hotel C", 800, stars=3)])

    r = c.post(f"/api/searches/{sid}/check", headers=ING)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"]
    assert [h["name"] for h in d["hits"]] == ["Hotel A"]   # Schwelle + Sterne-Nachfilter
    assert d["new"] == 1
    assert len(m._tg) == 1 and "Hotel A" in m._tg[0] and "900" in m._tg[0]
    # Suchparameter aus der Fav-Payload übernommen
    assert calls["region"] == 123 and calls["airports"] == ["DUS"]
    assert calls["boards"] == ["AI"] and calls["travellers"] == 2
    assert calls["location"] == [9]

    # Zweiter Lauf, unveränderte Preise → keine neue Meldung
    # (Cooldown zwischen manuellen Prüfungen desselben Suchabos — im Test wird die
    # Wartezeit übersprungen, siehe app.py:_cooldown_remaining)
    m._route_cooldowns.clear()
    assert c.post(f"/api/searches/{sid}/check", headers=ING).get_json()["new"] == 0
    assert len(m._tg) == 1

    # Preis fällt weiter → erneut melden
    _fake_search(m, monkeypatch, [_result(1, "Hotel A", 850)])
    m._route_cooldowns.clear()
    assert c.post(f"/api/searches/{sid}/check", headers=ING).get_json()["new"] == 1
    assert len(m._tg) == 2 and "850" in m._tg[1]

    # Über die Schwelle → vergessen; erneutes Unterschreiten → wieder melden
    _fake_search(m, monkeypatch, [_result(1, "Hotel A", 1100)])
    m._route_cooldowns.clear()
    assert c.post(f"/api/searches/{sid}/check", headers=ING).get_json()["hits"] == []
    _fake_search(m, monkeypatch, [_result(1, "Hotel A", 950)])
    m._route_cooldowns.clear()
    assert c.post(f"/api/searches/{sid}/check", headers=ING).get_json()["new"] == 1

    # GET liefert Abo-Zustand + letzte Treffer
    lst = c.get("/api/searches", headers=ING).get_json()["searches"]
    assert lst[0]["watch"] is True and lst[0]["max_price"] == 1000
    assert lst[0]["hits"][0]["name"] == "Hotel A"
    assert lst[0]["last_checked"] > 0


def test_watch_diff_markers(m, monkeypatch):
    """Diff gegen den letzten Lauf: 🆕 erstmals unter der Schwelle, 📉 weiter
    gefallen (mit Vorher-Preis) — in Meldung UND gespeicherter Trefferliste."""
    c = m.app.test_client()
    sid = _mk_watch(m, c)
    _fake_search(m, monkeypatch, [_result(1, "Hotel A", 900)])
    d = c.post(f"/api/searches/{sid}/check", headers=ING).get_json()
    assert d["hits"][0].get("is_new") is True
    assert "prev" not in d["hits"][0]
    assert "🆕" in m._tg[0] and "1 neu" in m._tg[0]

    _fake_search(m, monkeypatch, [_result(1, "Hotel A", 850)])
    m._route_cooldowns.clear()
    d = c.post(f"/api/searches/{sid}/check", headers=ING).get_json()
    assert d["hits"][0].get("prev") == 900
    assert "is_new" not in d["hits"][0]
    assert "📉" in m._tg[1] and "1 billiger" in m._tg[1] and "vorher" in m._tg[1]


def test_watch_api_guards(m, monkeypatch):
    c = m.app.test_client()
    r = c.post("/api/searches", headers=ING, json={"name": "X", "payload": _PAYLOAD})
    sid = r.get_json()["id"]
    # ohne aktives Abo → 400; unbekannte ID → 404; ohne Auth → 401
    assert c.post(f"/api/searches/{sid}/check", headers=ING).status_code == 400
    assert c.post("/api/searches/9999/check", headers=ING).status_code == 404
    assert c.post(f"/api/searches/{sid}/check").status_code == 401
    # Suche schlägt fehl → 502, last_checked trotzdem gesetzt (kein Hämmern)
    c.patch(f"/api/searches/{sid}", headers=ING, json={"watch": True, "max_price": 500})
    monkeypatch.setattr(m, "fetch_search_params", lambda **kw: None)
    m._route_cooldowns.clear()
    assert c.post(f"/api/searches/{sid}/check", headers=ING).status_code == 502
    with m.db() as con:
        assert con.execute("SELECT last_checked FROM saved_searches WHERE id=?",
                           (sid,)).fetchone()["last_checked"] > 0


def test_maybe_check_watches_respects_interval(m, monkeypatch):
    c = m.app.test_client()
    sid = _mk_watch(m, c)
    runs = []
    monkeypatch.setattr(m, "_check_search_watch", lambda s: runs.append(s))
    monkeypatch.setattr(m, "load_config", lambda: {"poll_interval": 3600})
    m._maybe_check_watches()
    assert runs == [sid]                       # fällig (last_checked=0 nach Aktivierung)
    with m.db() as con:                        # gerade geprüft → nicht erneut fällig
        con.execute("UPDATE saved_searches SET last_checked=strftime('%s','now') WHERE id=?",
                    (sid,))
    m._maybe_check_watches()
    assert runs == [sid]
