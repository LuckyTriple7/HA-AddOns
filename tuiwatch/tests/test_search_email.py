"""Tests fuer email_search.py (reine HTML-Funktion) und POST /api/search/email
(Hotelsuchen-Trefferliste per Mail -- Zeilen kommen vom Frontend, nicht aus der
DB, siehe offers_routes.py)."""
import importlib

import pytest

pytest.importorskip("flask")

import email_search

ING = {"X-Ingress-Path": "/test"}


def test_html_for_rows_contains_price_and_link():
    rows = [{"name": "Hotel Alcina", "price": 572, "location": "Playa de Palma",
             "country": "Spanien", "offer_url": "https://www.tui.com/x/1/offer/"}]
    html = email_search.html_for_rows(rows)
    assert "Hotel Alcina" in html
    assert "572" in html
    assert "https://www.tui.com/x/1/offer/" in html
    assert "Playa de Palma, Spanien" in html


def test_html_for_rows_escapes_hotel_name():
    # Zeilen kommen vom Client -- Namen duerfen kein HTML einschleusen koennen.
    rows = [{"name": '<script>alert(1)</script>', "price": 100}]
    html = email_search.html_for_rows(rows)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_html_for_rows_ignores_non_dict_entries():
    html = email_search.html_for_rows([{"name": "OK", "price": 1}, "garbage", None])
    assert "OK" in html


def test_html_for_rows_empty_price_shows_dash():
    html = email_search.html_for_rows([{"name": "Ohne Preis"}])
    assert "–" in html


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


def test_route_smtp_not_configured(m, monkeypatch):
    monkeypatch.setattr(m, "smtp_configured", lambda: False)
    c = m.app.test_client()
    r = c.post("/api/search/email", headers=ING, json={"to": "a@b.de", "results": [{"name": "X"}]})
    assert r.status_code == 400
    assert r.get_json()["error"] == "smtp_not_configured"


def test_route_no_recipient(m, monkeypatch):
    monkeypatch.setattr(m, "smtp_configured", lambda: True)
    monkeypatch.setattr(m, "load_config", lambda: {})
    c = m.app.test_client()
    r = c.post("/api/search/email", headers=ING, json={"results": [{"name": "X"}]})
    assert r.status_code == 400
    assert r.get_json()["error"] == "no_recipient"


def test_route_no_results(m, monkeypatch):
    monkeypatch.setattr(m, "smtp_configured", lambda: True)
    monkeypatch.setattr(m, "load_config", lambda: {})
    c = m.app.test_client()
    r = c.post("/api/search/email", headers=ING, json={"to": "a@b.de", "results": []})
    assert r.status_code == 400
    assert r.get_json()["error"] == "no_results"


def test_route_sends_selected_rows(m, monkeypatch):
    monkeypatch.setattr(m, "smtp_configured", lambda: True)
    monkeypatch.setattr(m, "load_config", lambda: {})
    sent = []
    monkeypatch.setattr(m, "send_email", lambda subject, html, to: sent.append((subject, html, to)))
    c = m.app.test_client()
    rows = [{"name": "Hotel A", "price": 500}, {"name": "Hotel B", "price": 600}]
    r = c.post("/api/search/email", headers=ING,
              json={"to": "a@b.de", "results": rows, "dest": "Mallorca"})
    assert r.status_code == 200
    d = r.get_json()
    assert d == {"sent": True, "to": "a@b.de", "count": 2}
    assert len(sent) == 1
    subject, html, to = sent[0]
    assert to == "a@b.de"
    assert "Hotel A" in html and "Hotel B" in html
    assert "Mallorca" in html


def test_route_send_failure_returns_502(m, monkeypatch):
    monkeypatch.setattr(m, "smtp_configured", lambda: True)
    monkeypatch.setattr(m, "load_config", lambda: {})
    def boom(subject, html, to):
        raise RuntimeError("smtp down")
    monkeypatch.setattr(m, "send_email", boom)
    c = m.app.test_client()
    r = c.post("/api/search/email", headers=ING, json={"to": "a@b.de", "results": [{"name": "X"}]})
    assert r.status_code == 502
    assert r.get_json()["error"] == "send_failed"


def test_route_requires_api_auth(m):
    c = m.app.test_client()
    r = c.post("/api/search/email", json={"to": "a@b.de", "results": [{"name": "X"}]})
    assert r.status_code == 401
