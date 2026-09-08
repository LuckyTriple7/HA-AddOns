"""Tests fuer den ETag/304-Pfad von `/api/offers`.

Die Liste wird von jedem offenen Browser alle 5 s geholt, aendert sich aber nur,
wenn eine Pruefrunde etwas Neues gefunden hat. Mit `If-None-Match` antwortet der
Server dann mit 304 ohne Rumpf — kein Uebertragen, kein Parsen im Browser.
"""
import importlib
import time

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
    mod.init_db()
    return mod


def _offer(m, url="https://example.invalid/etag"):
    with m.db() as con:
        return con.execute("INSERT INTO offers (url, hotel, created) VALUES (?,?,?)",
                           (url, "Test-Hotel", int(time.time()))).lastrowid


def test_unveraenderte_liste_gibt_304_ohne_rumpf(m):
    _offer(m)
    c = m.app.test_client()
    erst = c.get("/api/offers", headers=ING)
    assert erst.status_code == 200
    etag = erst.headers.get("ETag")
    assert etag and erst.get_json()["offers"]

    zweit = c.get("/api/offers", headers={**ING, "If-None-Match": etag})
    assert zweit.status_code == 304
    assert zweit.data == b""
    assert zweit.headers.get("ETag") == etag


def test_neuer_preis_aendert_den_etag(m):
    """Der Kern: ein ETag, der eine Aenderung verschluckt, wuerde die Oberflaeche
    auf einem alten Stand einfrieren."""
    oid = _offer(m)
    c = m.app.test_client()
    etag = c.get("/api/offers", headers=ING).headers["ETag"]
    with m.db() as con:
        con.execute("INSERT INTO price_history (offer_id, ts, price, ok, available) "
                    "VALUES (?,?,?,1,1)", (oid, int(time.time()), 777))
    r = c.get("/api/offers", headers={**ING, "If-None-Match": etag})
    assert r.status_code == 200
    assert r.headers["ETag"] != etag
    assert r.get_json()["offers"][0]["price"] == 777


def test_antwort_bleibt_gueltiges_json(m):
    """Die Route baut die Antwort jetzt selbst statt ueber jsonify — Inhaltstyp und
    Aufbau muessen unveraendert sein."""
    _offer(m)
    r = m.app.test_client().get("/api/offers", headers=ING)
    assert r.headers["Content-Type"].startswith("application/json")
    assert r.headers["Cache-Control"] == "no-cache"
    d = r.get_json()
    assert set(d) == {"offers", "busy", "issues"}
    assert d["offers"][0]["hotel"] == "Test-Hotel"
