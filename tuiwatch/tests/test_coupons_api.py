"""Tests für die MyTUI-Coupon-Logik ohne echten Browser/Login.

- `parse_coupons` (rein) direkt.
- Speicher/Dedup + Benachrichtigung über `_run_coupons` mit gemocktem `fetch_coupons`.
"""
import importlib

import pytest

from coupons import parse_coupons


def test_parse_coupons():
    data = [{
        "name": "CA_MemberPricing10",
        "startDate": "2026-06-30T22:00:00.000Z",
        "endDate": "2026-07-31T21:59:59.000Z",
        "couponId": "abc123",
        "template": {"claim": "10 € myTUI Vorteil", "saving": 150, "mastercodehash": "M_x"},
    }, {"foo": "bar"}]              # zweites Objekt ohne id → ignoriert
    out = parse_coupons(data)
    assert len(out) == 1
    assert out[0]["id"] == "abc123"
    assert out[0]["title"] == "10 € myTUI Vorteil"
    assert out[0]["end"] == "2026-07-31T21:59:59.000Z"
    # toleriert auch {"coupons": [...]}
    assert parse_coupons({"coupons": data})[0]["id"] == "abc123"


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
    m.TRIPS_DIR = str(tmp_path / "trips")
    m._DATA = str(tmp_path)
    m.init_db()
    return m


_COUPONS = [
    {"id": "c1", "title": "100 € sparen", "saving": 100, "start": "", "end": "2026-07-31T21:59:59.000Z"},
    {"id": "c2", "title": "10 € Vorteil", "saving": 10, "start": "", "end": "2026-08-31T21:59:59.000Z"},
]


def test_store_dedupe_and_notify(app_mod, monkeypatch):
    m = app_mod
    sent = []
    monkeypatch.setattr(m, "load_config",
                        lambda: {"tui_user": "u", "tui_pass": "p", "notify_coupons": True})
    monkeypatch.setattr(m, "_notify_ha", lambda *a, **k: sent.append(("ha",) + a))
    monkeypatch.setattr(m, "_notify_telegram", lambda t: sent.append(("tg", t)))
    monkeypatch.setattr(m, "fetch_coupons", lambda *a, **k: {"ok": True, "coupons": _COUPONS})

    m._run_coupons()                                # 1. Lauf → beide neu
    pay = m._coupons_payload()
    assert pay["configured"] is True
    assert len(pay["coupons"]) == 2 and pay["ts"]
    assert pay["error"] is None
    # genau eine Sammel-Benachrichtigung (HA + Telegram) für 2 neue Coupons
    assert any(x[0] == "ha" for x in sent) and any(x[0] == "tg" for x in sent)

    sent.clear()
    m._run_coupons()                                # 2. Lauf → nichts neu → keine Meldung
    assert sent == []
    assert len(m._coupons_payload()["coupons"]) == 2


def test_run_coupons_error_surfaced(app_mod, monkeypatch):
    m = app_mod
    monkeypatch.setattr(m, "load_config",
                        lambda: {"tui_user": "u", "tui_pass": "p", "notify_coupons": False})
    monkeypatch.setattr(m, "fetch_coupons",
                        lambda *a, **k: {"ok": False, "error": "Login blockiert (Captcha)."})
    m._run_coupons()
    pay = m._coupons_payload()
    assert pay["error"] == "Login blockiert (Captcha)."


def test_coupons_endpoint_not_configured(app_mod, monkeypatch):
    m = app_mod
    monkeypatch.setattr(m, "load_config", lambda: {"tui_user": "", "tui_pass": ""})
    c = m.app.test_client()
    ing = {"X-Ingress-Path": "/test"}
    assert c.get("/api/coupons", headers=ing).get_json()["configured"] is False
    assert c.post("/api/coupons", headers=ing).status_code == 400
