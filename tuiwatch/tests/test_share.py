"""Tests für die öffentlichen Angebots-Links (share_routes.py).

Schwerpunkt Sicherheit: die öffentliche App darf ausschließlich `/s/<token>`
kennen, und im Schnappschuss darf nichts landen, was nicht ausdrücklich in der
Whitelist steht (TUI-URL, Buchungscode, PDF-Link, Wunschpreis …). Beides würde
sonst über einen weitergegebenen Link nach draußen sickern.
"""
import importlib
import json
import time
from pathlib import Path

import pytest

pytest.importorskip("flask")

ROOT = Path(__file__).resolve().parent.parent

CLIMATE = {
    "months": [{"monat": i, "temp_tag": 20 + i, "temp_nacht": 12, "wasser": 18,
                "sonnenstunden": 6, "regentage": 3, "hinweis": ""} for i in range(1, 13)],
    "beste_monate": [5, 6],
    "zusammenfassung": "Ganzjährig mild.",
}
GUIDE = {
    "sections": [{"titel": "Einreise", "einleitung": "Kurz und knapp.",
                  "punkte": [{"label": "Pass", "text": "Noch 6 Monate gültig",
                              "volatil": True}]}],
    "zusammenfassung": ["Personalausweis reicht"],
}
# Angebots-URL mit Region-giataId: Klima/Reiseführer hängen an der Region, nicht
# am Hotel — ohne die Region würde der Schnappschuss beides stumm weglassen.
OFFER_URL = ("https://www.tui.com/pauschalreisen/angebote/Hotel-Sonne/4711/"
             "?regionGiataIds=555")


@pytest.fixture
def m(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(ROOT))   # Templates/Assets liegen im Repo
    try:
        mod = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(mod)
    mod.DB_PATH = str(tmp_path / "tuiwatch.db")
    mod.init_db()
    return mod


@pytest.fixture
def sr(m):
    import share_routes
    importlib.reload(share_routes)
    return share_routes


@pytest.fixture
def offer_id(m):
    now = int(time.time())
    with m.db() as con:
        cur = con.execute(
            "INSERT INTO offers (url, label, hotel, details, room, board, location, "
            "country, stars, rating, rating_count, travellers_count, return_date, "
            "image_url, booking_code, pdf_url, target_price, booked_price, created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (OFFER_URL, "Testangebot", "Hotel Sonne", "7 Nächte ab 12.09.2026",
             "Doppelzimmer", "All Inclusive", "Playa", "Spanien", 4.0, 5.4, 220, 2,
             "2026-09-19", "https://img.example/h.jpg", "GEHEIM123",
             "https://tui.example/geheim.pdf", 999.0, 1234.0, now))
        oid = cur.lastrowid
        con.execute("INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,1)",
                    (oid, now - 86400, 1999.0))
        con.execute("INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,1)",
                    (oid, now, 1899.0))
        con.execute("INSERT INTO climate (giata, label, ts, model, data) VALUES (555,?,?,?,?)",
                    ("Mallorca", now, "m", json.dumps(CLIMATE)))
        con.execute("INSERT INTO guide (giata, label, ts, model, data) VALUES (555,?,?,?,?)",
                    ("Mallorca", now, "m", json.dumps(GUIDE)))
        con.execute("INSERT INTO ai_analyses (kind, title, model, summary, ts) "
                    "VALUES ('advisor','Kanaren','m','## Vorschlag\n- **Teneriffa**',?)",
                    (now,))
    return oid


@pytest.fixture
def admin(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    m.app.config["TESTING"] = True
    return m.app.test_client()


@pytest.fixture
def public(sr):
    sr.share_app.config["TESTING"] = True
    return sr.share_app.test_client()


def _create(admin, offer_id, **kw):
    body = {"offer_ids": [offer_id], "title": "Unsere Auswahl", "note": "Schau mal"}
    body.update(kw)
    r = admin.post("/api/shares", json=body)
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


# ── Schnappschuss ─────────────────────────────────────────────────────────────

def test_payload_only_contains_whitelisted_fields(m, sr, admin, offer_id):
    """Der Schnappschuss darf keine Felder enthalten, die nicht in _OFFER_FIELDS
    stehen — sonst wandert eine neue Angebots-Spalte automatisch nach draußen."""
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        payload = json.loads(con.execute("SELECT payload FROM shares WHERE token=?",
                                         (tok,)).fetchone()["payload"])
    item = payload["offers"][0]
    allowed = set(sr._OFFER_FIELDS) | set(sr._LIVE_FIELDS) | {"history", "spark", "id"}
    assert set(item) <= allowed
    for forbidden in ("booking_code", "room_booking_code",
                      "target_price", "booked_price"):
        assert forbidden not in item


def test_public_page_leaks_nothing_sensitive(public, admin, offer_id):
    tok = _create(admin, offer_id, include={"climate": True})["token"]
    body = public.get("/s/" + tok).get_data(as_text=True)
    assert "Testangebot" in body and "Mallorca" in body
    for secret in ("GEHEIM123", "geheim.pdf", "999", "1234"):
        assert secret not in body


def test_price_and_availability_are_live(m, public, admin, offer_id):
    """Preis und Verfügbarkeit sollen dem aktuellen Stand folgen — sonst zeigt ein
    weitergegebener Link Wochen später einen Fantasiepreis."""
    tok = _create(admin, offer_id)["token"]
    assert "1.899" in public.get("/s/" + tok).get_data(as_text=True)
    with m.db() as con:
        con.execute("INSERT INTO price_history (offer_id, ts, price, ok, available) "
                    "VALUES (?,?,?,1,0)", (offer_id, int(time.time()) + 60, 4444.0))
    body = public.get("/s/" + tok).get_data(as_text=True)
    assert "4.444" in body and "1.899" not in body
    assert "nicht mehr verfügbar" in body


def test_description_stays_frozen(m, public, admin, offer_id):
    """Nur Preis/Verfügbarkeit sind live — Beschreibung bleibt der Stand vom Erzeugen."""
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        con.execute("UPDATE offers SET label='Umbenannt', room='Suite' WHERE id=?",
                    (offer_id,))
    body = public.get("/s/" + tok).get_data(as_text=True)
    assert "Testangebot" in body and "Umbenannt" not in body


def test_deleted_offer_keeps_last_known_state(m, public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        con.execute("DELETE FROM offers WHERE id=?", (offer_id,))
    body = public.get("/s/" + tok).get_data(as_text=True)
    assert "Testangebot" in body and "1.899" in body
    assert "Letzter bekannter Stand" in body


def test_links_to_tui_and_holidaycheck(public, admin, offer_id):
    body = public.get("/s/" + _create(admin, offer_id)["token"]).get_data(as_text=True)
    assert OFFER_URL.replace("&", "&amp;") in body or OFFER_URL in body
    assert "site%3Aholidaycheck.de" in body


def test_hotel_pdf_is_linked(m, public, admin, offer_id):
    """Hotelbeschreibung als PDF gehört auf die Seite — aber nur die echte
    TUI-Adresse; die Fixture hat bewusst eine fremde (siehe Leck-Test)."""
    with m.db() as con:
        con.execute("UPDATE offers SET pdf_url=? WHERE id=?",
                    ("https://www.tui.com/api/hotelInfoPdf?giata=4711", offer_id))
    body = public.get("/s/" + _create(admin, offer_id)["token"]).get_data(as_text=True)
    assert "hotelInfoPdf" in body and "Hotelbeschreibung" in body


def test_only_tui_urls_are_linked(m, sr):
    """Die Angebots-URL landet als Link auf einer öffentlichen Seite — alles außer
    tui.com per https bleibt draußen."""
    assert sr._tui_link({"url": "https://www.tui.com/x"})
    assert not sr._tui_link({"url": "http://www.tui.com/x"})
    assert not sr._tui_link({"url": "https://evil.example/tui.com"})
    assert not sr._tui_link({"url": "javascript:alert(1)"})
    assert not sr._tui_link({"url": ""})


def test_extras_only_when_requested(public, admin, offer_id):
    plain = public.get("/s/" + _create(admin, offer_id)["token"]).get_data(as_text=True)
    assert "Klima" not in plain and "Reiseführer" not in plain

    full = _create(admin, offer_id, include={"climate": True, "guide": True,
                                             "history": True, "advisor": True},
                   advisor_id=1)
    body = public.get("/s/" + full["token"]).get_data(as_text=True)
    assert "Klima" in body and "Reiseführer" in body and "Reiseberater" in body
    assert "Preisverlauf" in body  # SVG-Sparkline


def test_create_requires_existing_offers(admin):
    assert admin.post("/api/shares", json={"offer_ids": [9999]}).status_code == 400
    assert admin.post("/api/shares", json={"offer_ids": []}).status_code == 400


# ── Gültigkeit / Widerruf ─────────────────────────────────────────────────────

def test_unknown_token_is_404(public):
    assert public.get("/s/" + "x" * 20).status_code == 404
    assert public.get("/s/kurz").status_code == 404


def test_expired_token_is_410(m, public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        con.execute("UPDATE shares SET expires_ts=? WHERE token=?",
                    (int(time.time()) - 10, tok))
    assert public.get("/s/" + tok).status_code == 410


def test_revoked_token_is_404(public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    assert admin.delete("/api/shares/" + tok).status_code == 200
    assert public.get("/s/" + tok).status_code == 404


def test_views_are_counted(public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    public.get("/s/" + tok)
    public.get("/s/" + tok)
    item = admin.get("/api/shares").get_json()["items"][0]
    assert item["token"] == tok and item["views"] == 2


def test_edit_keeps_token_and_swaps_offers(m, public, admin, offer_id):
    """Angebot austauschen, ohne dass Empfänger einen neuen Link brauchen."""
    tok = _create(admin, offer_id)["token"]
    public.get("/s/" + tok)          # ein Aufruf, muss erhalten bleiben
    with m.db() as con:
        second = con.execute(
            "INSERT INTO offers (url, label, hotel, created) VALUES "
            "('https://www.tui.com/pauschalreisen/angebote/Zweites/4712/','Zweitangebot',"
            "'Hotel Zwei',?)", (int(time.time()),)).lastrowid

    r = admin.patch("/api/shares/" + tok, json={"offer_ids": [second]})
    assert r.status_code == 200 and r.get_json()["token"] == tok

    body = public.get("/s/" + tok).get_data(as_text=True)
    assert "Zweitangebot" in body and "Testangebot" not in body
    item = admin.get("/api/shares").get_json()["items"][0]
    assert item["token"] == tok and item["views"] == 2


def test_edit_detail_prefills_current_state(admin, offer_id):
    created = _create(admin, offer_id, include={"climate": True, "history": True},
                      title="Titel", note="Notiz")
    d = admin.get("/api/shares/" + created["token"]).get_json()
    assert d["offer_ids"] == [offer_id]
    assert d["title"] == "Titel" and d["note"] == "Notiz"
    assert d["include"]["climate"] is True and d["include"]["history"] is True
    assert d["include"]["guide"] is False
    assert 1 <= d["days"] <= 31


def test_edit_keeps_creation_date(m, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        con.execute("UPDATE shares SET created_ts=? WHERE token=?", (1000, tok))
    admin.patch("/api/shares/" + tok, json={"offer_ids": [offer_id]})
    with m.db() as con:
        row = con.execute("SELECT created_ts, payload FROM shares WHERE token=?",
                          (tok,)).fetchone()
    assert row["created_ts"] == 1000
    assert json.loads(row["payload"])["created"] == 1000


def test_edit_rejects_empty_selection(admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    assert admin.patch("/api/shares/" + tok, json={"offer_ids": []}).status_code == 400
    assert admin.patch("/api/shares/" + tok,
                       json={"offer_ids": [9999]}).status_code == 400


def test_destinations_report_missing_extras(m, admin, offer_id):
    """Grundlage für die Rückfrage „Klimatabelle fehlt — jetzt erstellen?"."""
    d = admin.post("/api/shares/destinations", json={"offer_ids": [offer_id]}).get_json()
    assert d["items"] == [{"giata": 555, "label": "Spanien", "has_climate": True,
                           "has_guide": True}]
    with m.db() as con:
        con.execute("DELETE FROM climate WHERE giata=555")
    d = admin.post("/api/shares/destinations", json={"offer_ids": [offer_id]}).get_json()
    assert d["items"][0]["has_climate"] is False
    assert d["items"][0]["has_guide"] is True


def test_share_extra_generation_bypasses_prompt_preview(m, monkeypatch):
    """Die Rückfrage im Teilen-Dialog ist bereits die Bestätigung — der Aufruf muss
    daher `_prompt_confirmed` schicken, sonst antwortet der Endpunkt bei aktiver
    Option `ai_prompt_preview` nur mit der Prompt-Vorschau und erzeugt nichts
    (v0.78.1: Fenster ging kurz auf, dann kam sofort der Link)."""
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    monkeypatch.setattr(m, "load_config", lambda: {"anthropic_api_key": "sk-test",
                                                   "ai_prompt_preview": True})
    monkeypatch.setattr(m, "_ai_request",
                        lambda *a, **kw: (json.dumps(CLIMATE), {"input_tokens": 1,
                                                                "output_tokens": 1}, None))
    m.app.config["TESTING"] = True
    c = m.app.test_client()

    without = c.post("/api/ai/climate", json={"giata": 777, "label": "Kreta"}).get_json()
    assert "prompt_preview" in without          # so lief es in die Falle

    withflag = c.post("/api/ai/climate", json={"giata": 777, "label": "Kreta",
                                               "_prompt_confirmed": True}).get_json()
    assert "prompt_preview" not in withflag
    import ai_routes
    assert ai_routes._climate_load(777) is not None


def test_destinations_needs_auth(m):
    m.app.config["TESTING"] = True
    assert m.app.test_client().post("/api/shares/destinations",
                                    json={"offer_ids": [1]}).status_code == 401


def test_detail_of_unknown_token_is_404(admin):
    assert admin.get("/api/shares/" + "x" * 20).status_code == 404


def test_patch_extends_validity(admin, offer_id):
    created = _create(admin, offer_id, days=1)
    r = admin.patch("/api/shares/" + created["token"], json={"days": 60})
    assert r.status_code == 200
    assert r.get_json()["expires_ts"] > created["expires_ts"]


# ── Abschottung der öffentlichen App ──────────────────────────────────────────

@pytest.mark.parametrize("path", ["/", "/login", "/api/offers", "/api/shares",
                                  "/static/app.js", "/a/app.js", "/icon-192.png"])
def test_public_app_serves_nothing_else(public, path):
    """Die öffentliche App kennt weder die Oberfläche noch irgendeine API — ein
    versehentlich dort registrierter Blueprint fliegt hier auf."""
    assert public.get(path).status_code == 404


def test_public_assets_are_whitelisted(public):
    for name in ("share.css", "share.js", "aimd.js"):
        assert public.get("/a/" + name).status_code == 200
    assert public.get("/robots.txt").get_data(as_text=True).startswith("User-agent")


def test_security_headers(public, admin, offer_id):
    r = public.get("/s/" + _create(admin, offer_id)["token"])
    assert r.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_admin_routes_need_auth(m, offer_id):
    """Ohne Session ist die Verwaltung dicht (echte _auth_ok-Prüfung, kein Ingress)."""
    m.app.config["TESTING"] = True
    c = m.app.test_client()
    assert c.get("/api/shares").status_code == 401
    assert c.post("/api/shares", json={"offer_ids": [offer_id]}).status_code == 401
    assert c.delete("/api/shares/abcdefgh").status_code == 401


def test_token_has_enough_entropy(admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    assert len(tok) >= 16
    assert len({_create(admin, offer_id)["token"] for _ in range(5)}) == 5


def test_cleanup_removes_long_expired(m, sr, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        con.execute("UPDATE shares SET expires_ts=? WHERE token=?",
                    (int(time.time()) - 30 * 86400, tok))
    assert sr.cleanup_expired() == 1
    with m.db() as con:
        assert con.execute("SELECT COUNT(*) c FROM shares").fetchone()["c"] == 0


# ── Kommentare der Empfänger ──────────────────────────────────────────────────

def _comment(public, token, text="Sieht gut aus!", author="Oma"):
    return public.post(f"/s/{token}/comment", data={"text": text, "author": author})


def test_comment_is_stored_and_shown(public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    r = _comment(public, tok)
    assert r.status_code == 303 and f"/s/{tok}" in r.headers["Location"]
    page = public.get("/s/" + tok).get_data(as_text=True)
    assert "Sieht gut aus!" in page and "Oma" in page


def test_comment_is_escaped_on_public_page(public, admin, offer_id):
    """Kommentare sind Fremdeingaben — HTML darf niemals durchschlagen."""
    tok = _create(admin, offer_id)["token"]
    _comment(public, tok, text="<script>alert(1)</script>", author="<b>x</b>")
    page = public.get("/s/" + tok).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_comment_length_is_capped(m, public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    _comment(public, tok, text="x" * 900, author="y" * 90)
    with m.db() as con:
        row = con.execute("SELECT author, text FROM share_comments").fetchone()
    assert len(row["text"]) == 500
    assert len(row["author"]) == 40


def test_empty_comment_is_rejected(m, public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    r = _comment(public, tok, text="   ")
    assert r.status_code == 303 and "k=leer" in r.headers["Location"]
    with m.db() as con:
        assert con.execute("SELECT COUNT(*) c FROM share_comments").fetchone()["c"] == 0


def test_comment_rate_limit_per_ip(m, sr, public, admin, offer_id):
    """Öffentlich beschreibbar → gedeckelt, sonst ist die Seite ein Gästebuch für Bots."""
    sr._comment_hits.clear()
    tok = _create(admin, offer_id)["token"]
    for i in range(sr._COMMENT_MAX_PER_WINDOW):
        assert "k=ok" in _comment(public, tok, text=f"Nr {i}").headers["Location"]
    assert "k=takt" in _comment(public, tok, text="einer zu viel").headers["Location"]
    with m.db() as con:
        n = con.execute("SELECT COUNT(*) c FROM share_comments").fetchone()["c"]
    assert n == sr._COMMENT_MAX_PER_WINDOW


def test_comment_on_expired_link_is_gone(m, public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        con.execute("UPDATE shares SET expires_ts=? WHERE token=?",
                    (int(time.time()) - 60, tok))
    assert _comment(public, tok).status_code == 410


def test_comment_on_unknown_token_is_404(public):
    assert public.post("/s/gibtsnichtxx/comment", data={"text": "hallo"}).status_code == 404


def test_admin_sees_new_comment_flag(sr, public, admin, offer_id):
    sr._comment_hits.clear()
    tok = _create(admin, offer_id)["token"]
    _comment(public, tok)
    item = next(i for i in admin.get("/api/shares").get_json()["items"] if i["token"] == tok)
    assert item["comments"] == 1 and item["new_comments"] == 1
    # Öffnen markiert als gelesen
    assert len(admin.get(f"/api/shares/{tok}/comments").get_json()["items"]) == 1
    item = next(i for i in admin.get("/api/shares").get_json()["items"] if i["token"] == tok)
    assert item["comments"] == 1 and item["new_comments"] == 0


def test_admin_can_edit_and_delete_comment(sr, public, admin, offer_id):
    sr._comment_hits.clear()
    tok = _create(admin, offer_id)["token"]
    _comment(public, tok)
    cid = admin.get(f"/api/shares/{tok}/comments").get_json()["items"][0]["id"]
    r = admin.patch(f"/api/shares/{tok}/comments/{cid}",
                    json={"text": "Korrigiert", "author": "Opa"})
    assert r.status_code == 200
    page = public.get("/s/" + tok).get_data(as_text=True)
    assert "Korrigiert" in page and "Opa" in page
    assert admin.delete(f"/api/shares/{tok}/comments/{cid}").status_code == 200
    assert admin.get(f"/api/shares/{tok}/comments").get_json()["items"] == []


def test_comment_admin_routes_need_auth(m):
    """Ohne Session bleibt die Kommentarverwaltung dicht (kein `admin`-Fixture,
    damit die echte _auth_ok-Prüfung greift)."""
    m.app.config["TESTING"] = True
    c = m.app.test_client()
    tok = "abcdefghijkl"
    assert c.get(f"/api/shares/{tok}/comments").status_code == 401
    assert c.patch(f"/api/shares/{tok}/comments/1", json={"text": "x"}).status_code == 401
    assert c.delete(f"/api/shares/{tok}/comments/1").status_code == 401


def test_revoking_share_removes_its_comments(m, sr, public, admin, offer_id):
    sr._comment_hits.clear()
    tok = _create(admin, offer_id)["token"]
    _comment(public, tok)
    admin.delete("/api/shares/" + tok)
    with m.db() as con:
        assert con.execute("SELECT COUNT(*) c FROM share_comments").fetchone()["c"] == 0


def test_comment_stores_client_ip(m, sr, public, admin, offer_id):
    sr._comment_hits.clear()
    tok = _create(admin, offer_id)["token"]
    public.post(f"/s/{tok}/comment", data={"text": "Hallo"},
                headers={"CF-Connecting-IP": "93.184.216.34"})
    items = admin.get(f"/api/shares/{tok}/comments").get_json()["items"]
    assert items[0]["ip"] == "93.184.216.34"


def test_public_page_never_shows_ips(sr, public, admin, offer_id):
    """Die IP ist nur für den Besitzer — auf der öffentlichen Seite hat sie nichts
    verloren (sonst sieht jeder Empfänger, woher die anderen schreiben)."""
    sr._comment_hits.clear()
    tok = _create(admin, offer_id)["token"]
    public.post(f"/s/{tok}/comment", data={"text": "Hallo"},
                headers={"CF-Connecting-IP": "93.184.216.34"})
    assert "93.184.216.34" not in public.get("/s/" + tok).get_data(as_text=True)


def test_comment_triggers_notification(m, sr, public, admin, offer_id, monkeypatch):
    sr._comment_hits.clear()
    monkeypatch.setattr(m, "_spawn", lambda fn, *a, **k: fn(*a, **k))  # synchron
    ha, tg = [], []
    monkeypatch.setattr(m, "_notify_ha", lambda t, msg, tag, muted=False: ha.append((t, msg)))
    monkeypatch.setattr(m, "_notify_telegram", lambda text, muted=False: tg.append(text))
    tok = _create(admin, offer_id)["token"]
    public.post(f"/s/{tok}/comment", data={"text": "Gefällt mir", "author": "Oma"},
                headers={"CF-Connecting-IP": "45.83.12.7"})
    assert len(ha) == 1 and len(tg) == 1
    assert "Oma" in ha[0][1] and "45.83.12.7" in ha[0][1] and "Gefällt mir" in ha[0][1]
    assert "45.83.12.7" in tg[0]


def test_comment_notification_can_be_switched_off(m, sr, public, admin, offer_id, monkeypatch):
    sr._comment_hits.clear()
    monkeypatch.setattr(m, "_spawn", lambda fn, *a, **k: fn(*a, **k))
    monkeypatch.setattr(m, "load_config", lambda: {"notify_share_comments": False})
    sent = []
    monkeypatch.setattr(m, "_notify_ha", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(m, "_notify_telegram", lambda *a, **k: sent.append(a))
    tok = _create(admin, offer_id)["token"]
    public.post(f"/s/{tok}/comment", data={"text": "Still bitte"})
    assert sent == []


def test_notification_escapes_html_for_telegram(m, sr, public, admin, offer_id, monkeypatch):
    """Kommentartext geht als HTML an Telegram — ungeschützt zerlegt er die Nachricht."""
    sr._comment_hits.clear()
    monkeypatch.setattr(m, "_spawn", lambda fn, *a, **k: fn(*a, **k))
    tg = []
    monkeypatch.setattr(m, "_notify_telegram", lambda text, muted=False: tg.append(text))
    monkeypatch.setattr(m, "_notify_ha", lambda *a, **k: None)
    tok = _create(admin, offer_id)["token"]
    public.post(f"/s/{tok}/comment", data={"text": "<b>fett</b> & weg", "author": "<i>x</i>"})
    assert "<b>fett</b>" not in tg[0]
    assert "&lt;b&gt;fett&lt;/b&gt;" in tg[0] and "&amp;" in tg[0]


# ── Client-IP hinter mehreren Proxy-Ebenen ────────────────────────────────────

class _Req:
    def __init__(self, headers, remote_addr="172.30.32.1"):
        self.headers = headers
        self.remote_addr = remote_addr


def test_client_ip_prefers_cloudflare_header(m):
    assert m.get_client_ip(_Req({"CF-Connecting-IP": "93.184.216.34",
                                 "X-Forwarded-For": "10.0.0.9"})) == "93.184.216.34"


def test_client_ip_takes_first_public_from_chain(m):
    """Reverse Proxy hängt sich hinten an — links steht der echte Client."""
    assert m.get_client_ip(_Req(
        {"X-Forwarded-For": "93.184.216.34, 172.30.32.1, 10.0.0.9"})) == "93.184.216.34"


def test_client_ip_skips_internal_proxy_headers(m):
    """172.30.32.1 (Docker-Bridge) ist keine Client-Adresse, nur der letzte Hop."""
    assert m.get_client_ip(_Req({"X-Real-IP": "172.30.32.1",
                                 "X-Forwarded-For": "45.83.12.7, 172.30.32.1"})) == "45.83.12.7"


def test_client_ip_keeps_lan_address_when_thats_all(m):
    """Aus dem eigenen Netz gibt es keine öffentliche IP — dann eben die private."""
    assert m.get_client_ip(_Req({"X-Forwarded-For": "192.168.1.50"})) == "192.168.1.50"


def test_client_ip_falls_back_to_remote_addr(m):
    assert m.get_client_ip(_Req({})) == "172.30.32.1"


def test_comment_uses_forwarded_chain(m, sr, public, admin, offer_id):
    sr._comment_hits.clear()
    tok = _create(admin, offer_id)["token"]
    public.post(f"/s/{tok}/comment", data={"text": "Aus dem Netz"},
                headers={"X-Forwarded-For": "45.83.12.7, 172.30.32.1"})
    items = admin.get(f"/api/shares/{tok}/comments").get_json()["items"]
    assert items[0]["ip"] == "45.83.12.7"


# ── Kommentare je Link an/aus ─────────────────────────────────────────────────

def test_comments_enabled_by_default(admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    assert admin.get(f"/api/shares/{tok}").get_json()["comments_enabled"] is True
    item = next(i for i in admin.get("/api/shares").get_json()["items"] if i["token"] == tok)
    assert item["comments_enabled"] is True


def test_share_can_be_created_without_comments(m, public, admin, offer_id):
    tok = _create(admin, offer_id, comments_enabled=False)["token"]
    page = public.get("/s/" + tok).get_data(as_text=True)
    assert "cmt-form" not in page
    r = public.post(f"/s/{tok}/comment", data={"text": "trotzdem"})
    assert r.status_code == 303 and "k=zu" in r.headers["Location"]
    with m.db() as con:
        assert con.execute("SELECT COUNT(*) c FROM share_comments").fetchone()["c"] == 0


def test_toggle_comments_keeps_existing_ones_visible(sr, public, admin, offer_id):
    """Zumachen heißt „nichts Neues", nicht „alles weg"."""
    sr._comment_hits.clear()
    tok = _create(admin, offer_id)["token"]
    _comment(public, tok, text="Steht schon da")
    admin.patch(f"/api/shares/{tok}", json={"comments_enabled": False})
    page = public.get("/s/" + tok).get_data(as_text=True)
    assert "Steht schon da" in page and "cmt-form" not in page
    admin.patch(f"/api/shares/{tok}", json={"comments_enabled": True})
    assert "cmt-form" in public.get("/s/" + tok).get_data(as_text=True)


def test_toggle_does_not_change_validity(admin, offer_id):
    """Nur den Schalter umlegen darf die Gültigkeit nicht auf 30 Tage zurücksetzen."""
    tok = _create(admin, offer_id, days=200)["token"]
    before = admin.get(f"/api/shares/{tok}").get_json()["expires_ts"]
    admin.patch(f"/api/shares/{tok}", json={"comments_enabled": False})
    assert admin.get(f"/api/shares/{tok}").get_json()["expires_ts"] == before


def test_edit_keeps_comment_setting(sr, public, admin, offer_id):
    tok = _create(admin, offer_id, comments_enabled=False)["token"]
    admin.patch(f"/api/shares/{tok}", json={"offer_ids": [offer_id], "title": "Neu"})
    assert admin.get(f"/api/shares/{tok}").get_json()["comments_enabled"] is False


def test_client_ip_rejects_garbage_headers(m):
    """Header sind Fremdeingaben: nur geprüfte IP-Literale dürfen weiter, sonst
    landet beliebiger Text in Log, Datenbank und Oberfläche."""
    assert m.get_client_ip(_Req({"X-Real-IP": "nicht-l\nog-sicher"})) == "172.30.32.1"
    assert m.get_client_ip(_Req({"X-Forwarded-For": "<script>, 45.83.12.7"})) == "45.83.12.7"
    assert m.get_client_ip(_Req({"CF-Connecting-IP": "1.2.3.4.5.6"})) == "172.30.32.1"


def test_log_safe_strips_control_chars(m):
    assert "\n" not in m.log_safe("Zeile1\nZeile2 INFO gefälscht")
    assert m.log_safe("x" * 300).endswith("…")
