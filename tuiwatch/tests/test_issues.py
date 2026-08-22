"""Tests für die Störungsliste (issues.py): Melden/Entwarnen, Zählung im Kopf
(/api/offers → issues), Pausieren je Art und die Wirkung aufs Preisbarometer."""
import importlib
import json

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}


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
    return mod


@pytest.fixture
def iss(m):
    mod = importlib.import_module("issues")
    importlib.reload(mod)
    return mod


def _items(m):
    return m.app.test_client().get("/api/issues", headers=ING).get_json()["items"]


def test_report_zaehlt_serie_und_gesamt(m, iss):
    iss.report("basket", "Malediven (März 2027)", "Malediven (März 2027)", "keine Treffer")
    iss.report("basket", "Malediven (März 2027)", "Malediven (März 2027)", "keine Treffer")
    items = _items(m)
    assert len(items) == 1
    assert items[0]["streak"] == 2 and items[0]["total"] == 2
    assert items[0]["kind_label"] == "Messreihe"


def test_severity_erst_ab_drei_in_folge(m, iss):
    iss.report("basket", "A", "A")
    assert iss.summary() == {"n": 1, "severity": "warn"}
    iss.report("basket", "A", "A")
    iss.report("basket", "A", "A")
    assert iss.summary() == {"n": 1, "severity": "error"}
    assert _items(m)[0]["severity"] == "error"


def test_clear_entfernt_die_stoerung(m, iss):
    iss.report("basket", "A", "A")
    iss.clear("basket", "A")
    assert _items(m) == []
    assert iss.summary()["n"] == 0


def test_summary_haengt_an_api_offers(m, iss):
    iss.report("basket", "A", "A")
    d = m.app.test_client().get("/api/offers", headers=ING).get_json()
    assert d["issues"] == {"n": 1, "severity": "warn"}


def test_pausieren_zaehlt_nicht_mehr_mit_bleibt_aber_sichtbar(m, iss):
    iss.report("basket", "A", "A")
    iid = _items(m)[0]["id"]
    c = m.app.test_client()
    r = c.post(f"/api/issues/{iid}/mute", json={"on": True}, headers=ING)
    assert r.status_code == 200
    assert iss.summary()["n"] == 0
    items = _items(m)
    assert len(items) == 1 and items[0]["muted"] == 1


def test_pausierte_messreihe_faellt_aus_dem_barometer(m, iss, monkeypatch):
    """Der eigentliche Zweck: die tote Suche kostet keinen TUI-Aufruf mehr."""
    mb = importlib.import_module("market_basket")
    importlib.reload(mb)
    with m.db() as con:
        con.execute(
            "INSERT INTO saved_searches (name, payload, ts) VALUES (?,?,0)",
            ("Malediven", json.dumps({"dest": {"giata": 123, "label": "Malediven"},
                                      "vom": "2099-03-01", "bis": "2099-03-15"})))
    monkeypatch.setattr(mb, "_offer_targets", lambda seen: [])
    assert [t["key"] for t in mb._basket_targets()] == ["Malediven"]

    iss.report("basket", "Malediven", "Malediven")
    iid = _items(m)[0]["id"]
    m.app.test_client().post(f"/api/issues/{iid}/mute", json={"on": True}, headers=ING)
    assert mb._basket_targets() == []


def test_reaktivieren_setzt_serie_zurueck_und_nimmt_die_messreihe_wieder_auf(m, iss, monkeypatch):
    mb = importlib.import_module("market_basket")
    importlib.reload(mb)
    with m.db() as con:
        con.execute(
            "INSERT INTO saved_searches (name, payload, ts) VALUES (?,?,0)",
            ("Malediven", json.dumps({"dest": {"giata": 123, "label": "Malediven"},
                                      "vom": "2099-03-01", "bis": "2099-03-15"})))
    monkeypatch.setattr(mb, "_offer_targets", lambda seen: [])
    for _ in range(3):
        iss.report("basket", "Malediven", "Malediven")
    c = m.app.test_client()
    iid = _items(m)[0]["id"]
    c.post(f"/api/issues/{iid}/mute", json={"on": True}, headers=ING)
    c.post(f"/api/issues/{iid}/mute", json={"on": False}, headers=ING)
    items = _items(m)
    assert items[0]["muted"] == 0 and items[0]["streak"] == 0
    assert items[0]["severity"] == "warn"          # nicht sofort wieder rot
    assert [t["key"] for t in mb._basket_targets()] == ["Malediven"]


def test_pausieren_eines_angebots_setzt_paused(m, iss):
    with m.db() as con:
        cur = con.execute("INSERT INTO offers (url, label, created) VALUES (?,?,0)",
                          ("https://www.tui.com/x", "Testhotel"))
        oid = cur.lastrowid
    iss.report("offer", oid, "Testhotel", "3× kein Preis")
    iid = _items(m)[0]["id"]
    m.app.test_client().post(f"/api/issues/{iid}/mute", json={"on": True}, headers=ING)
    with m.db() as con:
        assert con.execute("SELECT paused FROM offers WHERE id=?", (oid,)).fetchone()[0] == 1


def test_pausieren_eines_suchabos_schaltet_watch_ab(m, iss):
    with m.db() as con:
        cur = con.execute(
            "INSERT INTO saved_searches (name, payload, ts, watch, max_price) "
            "VALUES (?,?,0,1,999)", ("Abo", "{}"))
        sid = cur.lastrowid
    iss.report("search", sid, "Abo", "Suche fehlgeschlagen")
    iid = _items(m)[0]["id"]
    m.app.test_client().post(f"/api/issues/{iid}/mute", json={"on": True}, headers=ING)
    with m.db() as con:
        assert con.execute("SELECT watch FROM saved_searches WHERE id=?",
                           (sid,)).fetchone()[0] == 0


def test_ausblenden_loescht_nur_den_eintrag(m, iss):
    with m.db() as con:
        cur = con.execute("INSERT INTO offers (url, label, created) VALUES (?,?,0)",
                          ("https://www.tui.com/x", "Testhotel"))
        oid = cur.lastrowid
    iss.report("offer", oid, "Testhotel")
    iid = _items(m)[0]["id"]
    m.app.test_client().delete(f"/api/issues/{iid}", headers=ING)
    assert _items(m) == []
    with m.db() as con:
        assert con.execute("SELECT paused FROM offers WHERE id=?", (oid,)).fetchone()[0] == 0


def test_drop_missing_raeumt_verwaiste_stoerungen_weg(m, iss):
    iss.report("basket", "A", "A")
    iss.report("basket", "B", "B")
    iss.drop_missing("basket", ["A"])
    assert [it["key"] for it in _items(m)] == ["A"]


def test_angebot_ohne_ergebnis_landet_in_der_liste_und_verschwindet_wieder(m, iss, monkeypatch):
    """Der Weg über den Poller: _check_error_alarm meldet, _clear_error_alarm entwarnt."""
    monkeypatch.setattr(m, "_notify_ha", lambda *a, **k: None)
    monkeypatch.setattr(m, "_notify_telegram", lambda *a, **k: None)
    with m.db() as con:
        cur = con.execute("INSERT INTO offers (url, label, created) VALUES (?,?,0)",
                          ("https://www.tui.com/x", "Testhotel"))
        oid = cur.lastrowid
        for ts in (1, 2, 3):
            con.execute("INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,0)",
                        (oid, ts, None))
    offer = {"id": oid, "label": "Testhotel", "url": "https://www.tui.com/x", "paused": 0}
    m._check_error_alarm(offer)
    items = _items(m)
    assert len(items) == 1 and items[0]["kind"] == "offer" and items[0]["key"] == str(oid)
    m._clear_error_alarm(offer)
    assert _items(m) == []


def test_angebot_loeschen_raeumt_die_stoerung_mit_weg(m, iss):
    with m.db() as con:
        cur = con.execute("INSERT INTO offers (url, label, created) VALUES (?,?,0)",
                          ("https://www.tui.com/x", "Testhotel"))
        oid = cur.lastrowid
    iss.report("offer", oid, "Testhotel")
    m.app.test_client().delete(f"/api/offers/{oid}", headers=ING)
    assert _items(m) == []


def test_mute_auf_unbekannte_id_gibt_404(m, iss):
    r = m.app.test_client().post("/api/issues/999/mute", json={"on": True}, headers=ING)
    assert r.status_code == 404
