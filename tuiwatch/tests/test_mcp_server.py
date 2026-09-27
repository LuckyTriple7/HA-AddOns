"""MCP-Server unter /mcp (0.119.0)."""
import importlib
import json
import os
import time

import pytest

pytest.importorskip("flask")

TOKEN = "t" * 32
AUTH = {"Authorization": "Bearer " + TOKEN}


@pytest.fixture
def m(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", os.path.dirname(os.path.dirname(__file__)))
    try:
        mod = importlib.import_module("app")
    except Exception as exc:                     # pragma: no cover
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(mod)
    mod.DB_PATH = str(tmp_path / "tuiwatch.db")
    mod.init_db()
    cfg = {"enable_mcp": True, "mcp_token": TOKEN, "mcp_allow_actions": False}
    mod._real_load_config = mod.load_config
    monkeypatch.setattr(mod, "load_config", lambda: cfg)
    monkeypatch.setattr(mod, "_spawn", lambda *a, **k: None)
    mod._failed_attempts.clear()
    mod._blocked_ips.clear()
    mod._cfg = cfg
    return mod


def rpc(c, method, params=None, mid=1, headers=AUTH):
    body = {"jsonrpc": "2.0", "method": method}
    if mid is not None:
        body["id"] = mid
    if params is not None:
        body["params"] = params
    return c.post("/mcp", data=json.dumps(body), content_type="application/json",
                  headers=headers)


def call(c, name, args=None):
    r = rpc(c, "tools/call", {"name": name, "arguments": args or {}})
    return r.get_json()["result"]


def _add_offer(m):
    with m.db() as con:
        cur = con.execute("INSERT INTO offers (url, label, hotel, created) VALUES (?,?,?,?)",
                          ("https://www.tui.com/x/1/", "Kreta", "Hotel Test", 1750000000))
        oid = cur.lastrowid
        con.execute("INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,1)",
                    (oid, int(time.time()) - 3600, 999.0))
    return oid


def test_disabled_and_auth(m):
    c = m.app.test_client()
    m._cfg["enable_mcp"] = False
    assert rpc(c, "ping").status_code == 404
    m._cfg["enable_mcp"] = True
    m._cfg["mcp_token"] = "kurz"
    assert rpc(c, "ping").status_code == 503
    m._cfg["mcp_token"] = TOKEN
    assert rpc(c, "ping", headers={"Authorization": "Bearer falsch"}).status_code == 401
    assert rpc(c, "ping", headers={}).status_code == 401
    assert rpc(c, "ping", headers={"X-API-Key": TOKEN}).status_code == 200
    r = rpc(c, "ping", headers=dict(AUTH, Origin="https://boese.example"))
    assert r.status_code == 403


def test_initialize_and_notification(m):
    c = m.app.test_client()
    d = rpc(c, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                              "clientInfo": {"name": "t", "version": "1"}}).get_json()
    assert d["result"]["protocolVersion"] == "2025-03-26"
    assert d["result"]["capabilities"]["tools"] is not None
    assert rpc(c, "notifications/initialized", mid=None).status_code == 202
    assert c.get("/mcp", headers=AUTH).status_code == 405
    assert rpc(c, "gibtsnicht").get_json()["error"]["code"] == -32601


def test_tools_readonly_by_default(m):
    c = m.app.test_client()
    names = {t["name"] for t in rpc(c, "tools/list").get_json()["result"]["tools"]}
    assert {"list_offers", "get_offer", "list_trips", "get_trip", "next_trip"} <= names
    assert "set_target_price" not in names
    r = rpc(c, "tools/call", {"name": "set_target_price",
                              "arguments": {"offer_id": 1, "price": 500}}).get_json()
    assert r["error"]["code"] == -32602
    m._cfg["mcp_allow_actions"] = True
    names = {t["name"] for t in rpc(c, "tools/list").get_json()["result"]["tools"]}
    assert {"check_offer", "set_target_price", "pause_offer"} <= names


def test_offer_tools(m):
    oid = _add_offer(m)
    c = m.app.test_client()
    res = call(c, "list_offers")
    assert res["structuredContent"]["count"] == 1
    assert res["structuredContent"]["offers"][0]["name"] == "Kreta"
    det = call(c, "get_offer", {"offer_id": oid})["structuredContent"]
    assert det["price_history"][-1]["price"] == 999.0
    miss = call(c, "get_offer", {"offer_id": 4711})
    assert miss["isError"] is True
    m._cfg["mcp_allow_actions"] = True
    assert call(c, "set_target_price", {"offer_id": oid, "price": 850})["structuredContent"]["target_price"] == 850
    with m.db() as con:
        assert con.execute("SELECT target_price FROM offers WHERE id=?", (oid,)).fetchone()[0] == 850
    call(c, "pause_offer", {"offer_id": oid, "paused": True})
    with m.db() as con:
        assert con.execute("SELECT paused FROM offers WHERE id=?", (oid,)).fetchone()[0] == 1


def test_trip_tools(m):
    with m.db() as con:
        cur = con.execute(
            "INSERT INTO trips (booking_code, destination, hotel, start_date, end_date, nights, "
            "travellers, total_price, data, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("B123", "Kreta", "Hotel Test", "2099-06-01", "2099-06-08", 7, 2, 2400.0,
             json.dumps({"hinflug": "STR 06:45"}), 1))
        tid = cur.lastrowid
        con.execute("INSERT INTO trips (booking_code, destination, start_date, end_date, data, created) "
                    "VALUES ('ALT', 'Mallorca', '2020-05-01', '2020-05-08', '{}', 1)")
    c = m.app.test_client()
    up = call(c, "list_trips")["structuredContent"]
    assert up["count"] == 1 and up["trips"][0]["own_share"] == 1200.0
    assert call(c, "list_trips", {"include_past": True})["structuredContent"]["count"] == 2
    det = call(c, "get_trip", {"trip_id": tid})["structuredContent"]
    assert "booking_code" not in det and "packing" in det


def test_trip_details_contain_no_personal_data(m, caplog):
    data = {"buchungsnummer": "TUI-GEHEIM-99", "reiseziel": "Kreta",
            "hotel": {"name": "Hotel Test", "code": "HER123"},
            "reisende": [{"name": "Erika Mustermann", "geburtsdatum": "01.02.1980", "preis": "1.200,00"},
                         {"name": "Max Mustermann", "geburtsdatum": "03.04.1978", "preis": "1.200,00"}],
            "sonderwuensche": ["Zimmer neben Familie Mustermann"],
            "fluege": [{"datum": "01.06.2099", "typ": "Hinflug", "abflug_zeit": "06:45",
                        "von": "Stuttgart", "nach": "Heraklion", "flugnummer": "X3 2150",
                        "passagier": "Erika Mustermann"}],
            "gesamtpreis": "2.400,00", "anzahlung": {"betrag": "480,00", "faelligkeit": "01.02.2099"}}
    with m.db() as con:
        tid = con.execute(
            "INSERT INTO trips (booking_code, destination, hotel, start_date, end_date, data, created) "
            "VALUES ('TUI-GEHEIM-99', 'Kreta', 'Hotel Test', '2099-06-01', '2099-06-08', ?, 1)",
            (json.dumps(data),)).lastrowid
    c = m.app.test_client()
    with caplog.at_level("INFO"):
        det = call(c, "get_trip", {"trip_id": tid})
        lst = call(c, "list_trips", {"include_past": True})
    text = json.dumps(det) + json.dumps(lst)
    for secret in ("Mustermann", "Erika", "1980", "TUI-GEHEIM", "Familie"):
        assert secret not in text, secret
    d = det["structuredContent"]["details"]
    assert d["reisende_anzahl"] == 2 and d["hotel"]["name"] == "Hotel Test"
    assert d["fluege"][0]["abflug_zeit"] == "06:45" and d["anzahlung"]["betrag"] == "480,00"
    assert "MCP: get_trip(trip_id=%d)" % tid in caplog.text


def test_token_generated_once_and_hidden(m, monkeypatch, tmp_path):
    if not m.settings_store.crypto_ready():
        pytest.skip("cryptography fehlt")
    monkeypatch.setattr(m, "load_config", m._real_load_config)   # echte Einstellungen
    m.settings_store.init(str(tmp_path))
    ING = {"X-Ingress-Path": "/test"}
    c = m.app.test_client()
    assert c.post("/api/mcp/token").status_code == 401
    tok = c.post("/api/mcp/token", headers=ING).get_json()["token"]
    assert len(tok) == 64
    st = c.get("/api/mcp/status", headers=ING).get_json()
    assert st == {"enabled": True, "token_set": True, "actions": False}
    keys = {i["key"] for g in c.get("/api/settings", headers=ING).get_json()["groups"]
            for i in g["items"]}
    assert "mcp_token" not in keys and "enable_mcp" in keys
    assert tok not in c.get("/api/settings", headers=ING).get_data(as_text=True)
    assert rpc(c, "ping", headers={"Authorization": "Bearer " + tok}).status_code == 200
    tok2 = c.post("/api/mcp/token", headers=ING).get_json()["token"]
    assert rpc(c, "ping", headers={"Authorization": "Bearer " + tok}).status_code == 401
    assert rpc(c, "ping", headers={"Authorization": "Bearer " + tok2}).status_code == 200


# ── Erweiterung 0.120.0 ───────────────────────────────────────────────────────

def test_new_tools_listed(m):
    names = {t["name"] for t in rpc(m.app.test_client(), "tools/list").get_json()["result"]["tools"]}
    assert {"get_problems", "get_api_status", "search_flights", "list_flight_destinations",
            "get_notifications", "get_price_calendar", "get_market_trend",
            "get_promo_codes"} <= names


def test_problems_and_api_status(m):
    import issues
    issues.report("offer", "7", "Hotel Test", "Kein Angebot im Zeitraum")
    c = m.app.test_client()
    p = call(c, "get_problems")["structuredContent"]
    assert p["problems"][0]["title"] == "Hotel Test" and p["problems"][0]["kind"] == "Angebot"
    m._health_state.update(ok=False, ts=int(time.time()), checks=[
        {"name": "Preis-API", "ok": False, "detail": "HTTP 503", "critical": True}])
    s = call(c, "get_api_status")["structuredContent"]
    assert s["ok"] is False and s["checks"][0]["note"] == "HTTP 503"


def test_notifications_hide_share_comments(m):
    with m.db() as con:
        con.execute("INSERT INTO notify_log (ts, channel, title, message, tag, ok) VALUES "
                    "(1000, 'ha', 'Preis gesunken', 'Kreta jetzt 899 €', 'price_1', 1)")
        con.execute("INSERT INTO notify_log (ts, channel, title, message, tag, ok) VALUES "
                    "(1000, 'telegram', 'Preis gesunken', 'Kreta jetzt 899 €', 'price_1', 1)")
        con.execute("INSERT INTO notify_log (ts, channel, title, message, tag, ok) VALUES "
                    "(1001, 'ha', 'Kommentar', 'Erika (93.184.216.34): super', 'share_comment', 1)")
    n = call(m.app.test_client(), "get_notifications")["structuredContent"]["notifications"]
    assert len(n) == 1 and n[0]["title"] == "Preis gesunken"
    assert "Erika" not in json.dumps(n)


def test_flights_tools(m, monkeypatch):
    import all_flights_routes as afr
    c = m.app.test_client()
    monkeypatch.setattr(afr, "search_all", lambda q, a="", b="": None)
    assert call(c, "search_flights", {"destination": "HER"})["isError"] is True
    monkeypatch.setattr(afr, "search_all", lambda q, a="", b="": {
        "str": {"rows": [{"to": "HER", "time": "06:45"}] * 100}, "muc": {"error": True}})
    r = call(c, "search_flights", {"destination": "HER"})["structuredContent"]
    assert r["Stuttgart"]["count"] == 100 and len(r["Stuttgart"]["flights"]) == 80
    assert r["Stuttgart"]["truncated"] is True and r["München"] == {"error": True}
    monkeypatch.setattr(afr, "destinations_all", lambda: [
        {"code": "HER", "name": "Heraklion", "country": "Griechenland", "airports": ["str"]},
        {"code": "PMI", "name": "Palma", "country": "Spanien", "airports": ["str"]}])
    d = call(c, "list_flight_destinations", {"filter": "griech"})["structuredContent"]
    assert d["count"] == 1 and d["destinations"][0]["code"] == "HER"


def test_calendar_market_promo(m):
    oid = _add_offer(m)
    c = m.app.test_client()
    cal = call(c, "get_price_calendar", {"offer_id": oid})["structuredContent"]
    assert cal["status"] == "idle"
    assert "global" in call(c, "get_market_trend")["structuredContent"]
    assert "codes" in call(c, "get_promo_codes")["structuredContent"]


def test_missing_token_does_not_lock_out_and_valid_token_always_wins(m):
    c = m.app.test_client()
    for _ in range(10):                          # Erreichbarkeits-Tests ohne Token
        assert rpc(c, "ping", headers={}).status_code == 401
    assert rpc(c, "ping").status_code == 200     # nicht gesperrt
    for _ in range(10):                          # echtes Raten sperrt die IP …
        rpc(c, "ping", headers={"Authorization": "Bearer falsch"})
    assert rpc(c, "ping", headers={"Authorization": "Bearer falsch"}).status_code == 429
    assert rpc(c, "ping").status_code == 200     # … das richtige Token gilt trotzdem
