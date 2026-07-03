"""Tests für frei vergebbare Tags auf Angeboten (PATCH tags, GET /api/offers).

Importiert die volle Flask-App; `check_offer` wird gemonkeypatcht (kein Netz).
"""
import importlib

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


def test_offer_starts_without_tags(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    assert _offer(c, oid)["tags"] == []


def test_patch_tags_add_and_replace(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    r = c.patch(f"/api/offers/{oid}", headers=ING, json={"tags": ["Strand", "Familie"]})
    assert r.status_code == 200
    assert _offer(c, oid)["tags"] == ["Strand", "Familie"]

    # Voller Ersatz, Trim + Dedup
    c.patch(f"/api/offers/{oid}", headers=ING, json={"tags": ["Strand", " Strand ", "Winter"]})
    assert _offer(c, oid)["tags"] == ["Strand", "Winter"]


def test_patch_tags_clear(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    c.patch(f"/api/offers/{oid}", headers=ING, json={"tags": ["Strand"]})
    c.patch(f"/api/offers/{oid}", headers=ING, json={"tags": []})
    assert _offer(c, oid)["tags"] == []
