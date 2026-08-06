"""Tests für `GET /api/offers/<id>/dest` — die Region zu einem Angebot.

Klimatabelle und Reiseführer hängen an der Region-giataId, das Angebot kennt aber
nur die Hotel-giataId. Aufgelöst wird über die Breadcrumb-API (einmal je Hotel,
danach aus dem Prozess-Cache); `regionGiataIds` aus der URL ist nur der Notnagel,
weil dort die u. U. viel gröbere Such-Region steht.
"""
import importlib

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}
_URL = "https://www.tui.com/pauschalreisen/suchen/angebote/Test-Hotel/12345/offer/"
_URL_REGION = _URL + "?regionGiataIds=128&duration=7"


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
    monkeypatch.setattr(mod, "check_offer", lambda *a, **k: None)  # kein Netz
    # Der Prozess-Cache überlebt den Reload des Moduls nicht, wohl aber den eines
    # einzelnen Tests — sonst würde der zweite Test den Treffer des ersten sehen.
    import offers_routes
    offers_routes._offer_dest_cache.clear()
    return mod


def _add(c, url, region="Gran Canaria"):
    oid = c.post("/api/offers", headers=ING, json={"url": url}).get_json()["id"]
    import app as A
    with A.db() as con:
        con.execute("UPDATE offers SET region=? WHERE id=?", (region, oid))
    return oid


def test_breadcrumb_beats_region_in_url(m, monkeypatch):
    """Die Insel des Hotels schlägt die Region der Suche.

    Zwei Malediven-Hotels aus einer Landessuche trugen beide dieselbe
    `regionGiataIds` und teilten sich dadurch Klimatabelle und Reiseführer — beim
    zweiten Angebot öffnete sich der Reiseführer des ersten (v0.79.0)."""
    monkeypatch.setattr(m, "region_giata_from_breadcrumb", lambda g: 1151)
    c = m.app.test_client()
    oid = _add(c, _URL_REGION, region="Malediven: Nord Male Atoll")
    d = c.get(f"/api/offers/{oid}/dest", headers=ING).get_json()
    assert d == {"giata": 1151, "label": "Malediven: Nord Male Atoll"}


def test_region_from_url_is_the_fallback(m, monkeypatch):
    """Liefert die Breadcrumb-API nichts, rettet `regionGiataIds` die Auflösung."""
    monkeypatch.setattr(m, "region_giata_from_breadcrumb", lambda g: None)
    c = m.app.test_client()
    oid = _add(c, _URL_REGION)
    d = c.get(f"/api/offers/{oid}/dest", headers=ING).get_json()
    assert d == {"giata": 128, "label": "Gran Canaria"}


def test_region_resolved_via_breadcrumb_and_cached(m, monkeypatch):
    calls = []
    monkeypatch.setattr(m, "region_giata_from_breadcrumb",
                        lambda g: calls.append(g) or 128)
    c = m.app.test_client()
    oid = _add(c, _URL)
    assert c.get(f"/api/offers/{oid}/dest", headers=ING).get_json()["giata"] == 128
    assert c.get(f"/api/offers/{oid}/dest", headers=ING).get_json()["giata"] == 128
    assert len(calls) == 1    # zweiter Aufruf aus dem Prozess-Cache


def test_country_is_used_when_region_is_empty(m, monkeypatch):
    monkeypatch.setattr(m, "region_giata_from_breadcrumb", lambda g: 128)
    c = m.app.test_client()
    oid = _add(c, _URL, region="")
    import app as A
    with A.db() as con:
        con.execute("UPDATE offers SET country='Spanien' WHERE id=?", (oid,))
    assert c.get(f"/api/offers/{oid}/dest", headers=ING).get_json()["label"] == "Spanien"


def test_unresolvable_region_is_an_error(m, monkeypatch):
    monkeypatch.setattr(m, "region_giata_from_breadcrumb", lambda g: None)
    c = m.app.test_client()
    oid = _add(c, _URL)
    r = c.get(f"/api/offers/{oid}/dest", headers=ING)
    assert r.status_code == 400 and r.get_json()["error"] == "no_region"


def test_unknown_offer_is_404(m):
    c = m.app.test_client()
    assert c.get("/api/offers/9999/dest", headers=ING).status_code == 404
