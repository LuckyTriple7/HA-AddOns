"""Tests fuer den Statistik-Cache in `_collect_offers` (`_offer_price_stats`).

`/api/offers` holt jeder offene Browser alle 5 s. Die Gesamtstatistik je Angebot
(min/max/Schnitt/Anzahl) liest dafuer die KOMPLETTE Historie des Angebots — auf
einer Testdatenbank mit 58.000 Zeilen waren das 14 der 68 ms, und zwischen zwei
Pruefrunden aendert sich daran nichts. Gecacht wird unter dem Zeitstempel der
letzten Messzeile: kommt eine neue dazu, wird neu gerechnet.

Die Tests halten fest, dass der Cache nie veraltete Zahlen ausliefert.
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


def _offer(m, url="https://example.invalid/stats"):
    with m.db() as con:
        cur = con.execute(
            "INSERT INTO offers (url, hotel, created) VALUES (?,?,?)",
            (url, "Test-Hotel", int(time.time())))
        return cur.lastrowid


def _price(m, oid, ts, price, ok=1):
    with m.db() as con:
        con.execute(
            "INSERT INTO price_history (offer_id, ts, price, ok, available) "
            "VALUES (?,?,?,?,1)", (oid, ts, price, ok))


def _stats(m, oid):
    o = next(x for x in m._collect_offers() if x["id"] == oid)
    return o["min_price"], o["max_price"], o["avg_price"], o["samples"]


def test_neue_preiszeile_aktualisiert_die_statistik(m):
    """Der Kern: ein Cache, der eine neue Messung verschluckt, waere schlimmer als
    gar keiner."""
    oid = _offer(m)
    _price(m, oid, 1000, 500)
    _price(m, oid, 2000, 600)
    assert _stats(m, oid) == (500, 600, 550, 2)
    _price(m, oid, 3000, 400)                  # neuer Tiefstand
    assert _stats(m, oid) == (400, 600, 500, 3)


def test_zweiter_aufruf_ohne_neue_zeile_rechnet_nicht_nochmal(m):
    """Der eigentliche Zweck: ohne neue Messzeile faellt die teure Abfrage weg."""
    oid = _offer(m)
    _price(m, oid, 1000, 500)
    _price(m, oid, 2000, 600)
    m._collect_offers()                        # fuellt den Cache

    with m.db() as con:
        gezaehlt = []
        orig = con.execute

        class Counting:
            def execute(self, sql, *a):
                gezaehlt.append(sql)
                return orig(sql, *a)
        m._offer_price_stats(Counting(), oid, 2000)
    assert gezaehlt == []                       # kein Weg in die Datenbank


def test_cache_gilt_je_angebot(m):
    a = _offer(m, "https://example.invalid/a")
    b = _offer(m, "https://example.invalid/b")
    _price(m, a, 1000, 500)
    _price(m, b, 1000, 900)
    assert _stats(m, a)[0] == 500 and _stats(m, b)[0] == 900


def test_zuruecksetzen_leert_den_cache(m):
    """Beim Zuruecksetzen verschwinden Zeilen, ohne dass eine neue dazukommt — genau
    der Fall, den der Zeitstempel-Schluessel allein nicht erkennen wuerde."""
    oid = _offer(m)
    _price(m, oid, 1000, 500)
    _price(m, oid, 2000, 600)
    assert _stats(m, oid)[3] == 2
    r = m.app.test_client().post(f"/api/reset/{oid}", headers=ING)
    assert r.status_code == 200
    assert _stats(m, oid) == (None, None, None, 0)


def test_nur_gueltige_messungen_zaehlen(m):
    """Fehlschlaege (ok=0) gehoeren nicht in die Statistik — auch nicht ueber den
    Cache-Pfad."""
    oid = _offer(m)
    _price(m, oid, 1000, 500)
    _price(m, oid, 2000, 900, ok=0)
    assert _stats(m, oid) == (500, 500, 500, 1)
