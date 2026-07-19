"""Tests für PATCH /api/offers/<id> mit check24_link (Check24-Hotel verknüpfen/lösen).

Importiert die volle Flask-App; check_offer wird gemonkeypatcht (kein Netz).
"""
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


def _add_offer(c):
    r = c.post("/api/offers", headers=ING, json={"url": _URL})
    assert r.status_code == 200
    return r.get_json()["id"]


def _offer(c, oid):
    offers = c.get("/api/offers", headers=ING).get_json()["offers"]
    return next(o for o in offers if o["id"] == oid)


def test_offer_starts_unlinked(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    assert _offer(c, oid)["check24_linked"] is False


def test_patch_valid_check24_link(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    r = c.patch(f"/api/offers/{oid}", headers=ING, json={"check24_link": _C24_URL})
    assert r.status_code == 200
    assert _offer(c, oid)["check24_linked"] is True


def test_patch_invalid_check24_link_rejected(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    r = c.patch(f"/api/offers/{oid}", headers=ING,
                json={"check24_link": "https://urlaub.check24.de/suche/hotel?areaId=551"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_check24_url"
    assert _offer(c, oid)["check24_linked"] is False


def test_patch_empty_check24_link_unlinks(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    c.patch(f"/api/offers/{oid}", headers=ING, json={"check24_link": _C24_URL})
    assert _offer(c, oid)["check24_linked"] is True
    c.patch(f"/api/offers/{oid}", headers=ING, json={"check24_link": ""})
    assert _offer(c, oid)["check24_linked"] is False


def test_patch_link_clears_stale_check24_cache(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    c.patch(f"/api/offers/{oid}", headers=ING, json={"check24_link": _C24_URL})
    with app_mod.db() as con:
        con.execute("INSERT INTO check24_cache (offer_id, ts, rows) VALUES (?,?,?)",
                    (oid, 1, "[]"))
    # erneutes Verknüpfen (neuer Link) muss den alten Cache verwerfen
    c.patch(f"/api/offers/{oid}", headers=ING, json={"check24_link": _C24_URL})
    with app_mod.db() as con:
        row = con.execute("SELECT 1 FROM check24_cache WHERE offer_id=?", (oid,)).fetchone()
    assert row is None


# ── check24_hotel_id: Hauptpfad (Klick auf Treffer der automatischen Hotelsuche) ──

def test_patch_check24_hotel_id_links(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    r = c.patch(f"/api/offers/{oid}", headers=ING,
                json={"check24_hotel_id": "11829", "check24_hotel_name": "Gloria Palace Amadores"})
    assert r.status_code == 200
    assert _offer(c, oid)["check24_linked"] is True


def test_patch_check24_hotel_id_invalid_rejected(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    r = c.patch(f"/api/offers/{oid}", headers=ING, json={"check24_hotel_id": "abc"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_check24_hotel_id"
    assert _offer(c, oid)["check24_linked"] is False


def test_patch_check24_hotel_id_empty_unlinks(app_mod):
    c = app_mod.app.test_client()
    oid = _add_offer(c)
    c.patch(f"/api/offers/{oid}", headers=ING, json={"check24_hotel_id": "11829"})
    assert _offer(c, oid)["check24_linked"] is True
    c.patch(f"/api/offers/{oid}", headers=ING, json={"check24_hotel_id": ""})
    assert _offer(c, oid)["check24_linked"] is False
