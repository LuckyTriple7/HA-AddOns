"""Tests für den API-Selbsttest: er darf nicht am Zustand eines einzelnen
Referenz-Angebots hängen (ausgebuchtes Testangebot ≠ kaputter Endpunkt) und muss
sich nach einem Fehler wieder starten lassen."""
import importlib

import pytest


@pytest.fixture
def sc():
    return importlib.import_module("scraper")


def _offer(temp_id, cheapest=False):
    return {"tempId": temp_id, "cheapest": cheapest, "rooms": [], "travellers": []}


def _stub_endpoints(sc, monkeypatch):
    """Alle Nicht-Angebots-Endpunkte des Selbsttests neutral stellen."""
    class _R:
        status_code = 200

        def json(self):
            return {}

    monkeypatch.setattr(sc, "fetch_search_params",
                        lambda **k: {"ok": True, "total": 1,
                                     "results": [{"giata": "999", "name": "Ersatz"}]})
    monkeypatch.setattr(sc, "fetch_destinations", lambda: {"items": [{"id": 1}]})
    monkeypatch.setattr(sc, "fetch_airports", lambda: [{"code": "DUS"}])
    monkeypatch.setattr(sc, "fetch_payment_terms", lambda *a, **k: {"deposit_pct": 20})
    monkeypatch.setattr(sc, "_get", lambda *a, **k: _R())
    monkeypatch.setattr(sc, "_post", lambda *a, **k: _R())


def _check(res, name):
    return next(c for c in res["checks"] if c["name"] == name)


def test_offer_api_ok_even_if_first_window_is_sold_out(sc, monkeypatch):
    """Leeres erstes Fenster darf den Selbsttest nicht abwürgen — es wird ein
    weiteres Anreise-Fenster probiert."""
    seen = []

    def fake_offers(giata, sd, ed):
        seen.append((giata, sd))
        if len(seen) == 1:
            return {"offers": []}, "HTTP 200"
        return {"offers": [_offer("t1", cheapest=True)]}, "HTTP 200"

    _stub_endpoints(sc, monkeypatch)
    monkeypatch.setattr(sc, "_hc_fetch_offers", fake_offers)
    monkeypatch.setattr(sc, "_fetch_vacancy", lambda *a, **k: {"vac_status": "OK"})

    res = sc.api_healthcheck()

    assert len(seen) == 2                      # zweites Fenster wurde genutzt
    assert _check(res, "Preis/Angebot-API")["ok"]
    assert _check(res, "Buchbarkeits-API")["ok"]


def test_vacancy_tries_further_offers_before_reporting_a_problem(sc, monkeypatch):
    """Ein ausgebuchtes Angebot (FAILED) ist kein API-Ausfall: der Check probiert
    weitere Angebote und meldet OK, sobald eines bestätigt wird."""
    _stub_endpoints(sc, monkeypatch)
    monkeypatch.setattr(sc, "_hc_fetch_offers", lambda *a: (
        {"offers": [_offer("a", cheapest=True), _offer("b"), _offer("c")]}, "HTTP 200"))
    seen = []

    def fake_vacancy(data, offer, **k):
        seen.append(offer["tempId"])
        return {"vac_status": "OK" if offer["tempId"] == "b" else "FAILED"}

    monkeypatch.setattr(sc, "_fetch_vacancy", fake_vacancy)

    res = sc.api_healthcheck()

    assert seen == ["a", "b"]
    assert _check(res, "Buchbarkeits-API")["ok"]


def test_vacancy_reports_failure_only_when_no_offer_is_confirmed(sc, monkeypatch):
    _stub_endpoints(sc, monkeypatch)
    monkeypatch.setattr(sc, "_hc_fetch_offers", lambda *a: (
        {"offers": [_offer("a", cheapest=True), _offer("b")]}, "HTTP 200"))
    monkeypatch.setattr(sc, "_fetch_vacancy", lambda *a, **k: {"vac_status": "FAILED"})

    res = sc.api_healthcheck()

    c = _check(res, "Buchbarkeits-API")
    assert not c["ok"] and "2 Testangeboten" in c["detail"]


def test_search_hotel_serves_as_fallback_test_offer(sc, monkeypatch):
    """Liefert das Referenz-Hotel in keinem Fenster ein Angebot, springt ein Hotel
    aus der Suche ein — statt „kein Testangebot" für Buchbarkeit und Zahlung."""
    _stub_endpoints(sc, monkeypatch)

    def fake_offers(giata, sd, ed):
        if giata == "999":
            return {"offers": [_offer("x", cheapest=True)]}, "HTTP 200"
        return {"offers": []}, "HTTP 200"

    monkeypatch.setattr(sc, "_hc_fetch_offers", fake_offers)
    monkeypatch.setattr(sc, "_fetch_vacancy", lambda *a, **k: {"vac_status": "OK"})
    giatas = []
    monkeypatch.setattr(sc, "fetch_payment_terms",
                        lambda offer, giata, **k: giatas.append(giata) or {"deposit_pct": 20})

    res = sc.api_healthcheck()

    assert _check(res, "Buchbarkeits-API")["ok"]
    assert _check(res, "Zahlungs-API")["ok"]
    assert giatas == ["999"]            # Zahlungs-Check nutzt dasselbe Ersatz-Hotel


def test_healthcheck_can_be_restarted_after_a_crash(monkeypatch, tmp_path):
    """Nach einem Fehler im Selbsttest darf die running-Flagge nicht stehen bleiben —
    sonst gäbe „Erneut prüfen" nur noch den alten Stand zurück."""
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        m = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(m)
    m.DB_PATH = str(tmp_path / "tuiwatch.db")
    m.init_db()
    monkeypatch.setattr(m, "_check_api_alarm", lambda res: None)
    monkeypatch.setattr(m, "_push_health_sensor", lambda res: None)

    def boom():
        raise RuntimeError("Flugplan kaputt")

    monkeypatch.setattr(m, "api_healthcheck", lambda **k: {"ok": True, "ts": 1, "checks": []})
    monkeypatch.setattr(m, "_flight_healthchecks", boom)
    m._run_healthcheck()
    assert not m._health_state.get("running")

    monkeypatch.setattr(m, "_flight_healthchecks", lambda: [])
    monkeypatch.setattr(m, "api_healthcheck", lambda **k: {
        "ok": True, "ts": 2, "checks": [{"name": "Preis/Angebot-API", "ok": True,
                                         "critical": True}]})
    res = m._run_healthcheck(wait=True)
    assert res["checks"] and res["ts"] == 2
