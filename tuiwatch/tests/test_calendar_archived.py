"""Tests für den weiterlaufenden Preiskalender bei archivierten Angeboten.

Kernpunkte: das archivierte Angebot wird weiter abgerufen (aber seltener und nie vor
den aktiven), der Fehlerzähler pausiert erst nach mehreren Fehlschlägen IN FOLGE, und
ein Erfolg setzt ihn zurück.
"""
import importlib
import time
from datetime import date, timedelta

import pytest

pytest.importorskip("flask")


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


@pytest.fixture
def pc(m):
    return importlib.import_module("price_calendar")


def _offer(m, *, archived=0, cal_age_days=10, paused=0):
    """Angebot mit vorhandenem Kalender-Snapshot anlegen; Rückgabe: offer_id."""
    ts = int(time.time()) - cal_age_days * 86400
    with m.db() as con:
        cur = con.execute(
            "INSERT INTO offers (url, label, created, archived, calendar_paused) "
            "VALUES (?,?,?,?,?)",
            (f"https://www.tui.com/pauschalreisen/angebote/h/{int(time.time()*1000)%10**6}/"
             f"?duration=7", "Testhotel", int(time.time()), archived, paused))
        oid = cur.lastrowid
        con.execute("INSERT INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (oid, ts, '{"days": []}'))
    return oid


# ── Planung: wer wird abgerufen? ───────────────────────────────────────────────

def test_archived_offer_is_refreshed(m, monkeypatch):
    """Der eigentliche Punkt: ein archiviertes Angebot faellt nicht mehr aus dem
    Kalender-Refresh heraus."""
    oid = _offer(m, archived=1)
    seen = []
    monkeypatch.setattr(m, "_run_calendar", lambda i: seen.append(i))
    m._maybe_refresh_calendars()
    assert seen == [oid]


def test_archived_respects_longer_interval(m, monkeypatch):
    """Ein Tag alt reicht bei archivierten nicht — die laufen alle 3 Tage."""
    _offer(m, archived=1, cal_age_days=1)
    seen = []
    monkeypatch.setattr(m, "_run_calendar", lambda i: seen.append(i))
    m._maybe_refresh_calendars()
    assert seen == []


def test_active_offers_come_first_and_keep_the_quota(m, monkeypatch):
    """Zehn faellige aktive Angebote schoepfen das Kontingent aus; das archivierte
    darf sie nicht verdraengen."""
    arch = _offer(m, archived=1)
    active = [_offer(m) for _ in range(10)]
    seen = []
    monkeypatch.setattr(m, "_run_calendar", lambda i: seen.append(i))
    m._maybe_refresh_calendars()
    assert sorted(seen) == sorted(active)
    assert arch not in seen


def test_archived_refresh_can_be_switched_off(m, monkeypatch):
    oid = _offer(m, archived=1)
    monkeypatch.setattr(m, "load_config", lambda: {"calendar_archived_refresh": False})
    seen = []
    monkeypatch.setattr(m, "_run_calendar", lambda i: seen.append(i))
    m._maybe_refresh_calendars()
    assert seen == []
    assert oid


def test_paused_calendar_is_skipped(m, monkeypatch):
    _offer(m, archived=1, paused=1)
    _offer(m, paused=1)
    seen = []
    monkeypatch.setattr(m, "_run_calendar", lambda i: seen.append(i))
    m._maybe_refresh_calendars()
    assert seen == []


# ── Fehlerzähler und Pause ─────────────────────────────────────────────────────

def _fails(m, oid):
    with m.db() as con:
        r = con.execute("SELECT calendar_fails f, calendar_paused p FROM offers WHERE id=?",
                        (oid,)).fetchone()
    return r["f"], r["p"]


def test_pause_only_after_consecutive_failures(m, pc, monkeypatch):
    oid = _offer(m, archived=1)
    monkeypatch.setattr(m, "fetch_calendar", lambda url, **kw: None)
    for i in range(1, pc.CALENDAR_MAX_FAILS):
        pc._run_calendar(oid)
        assert _fails(m, oid) == (i, 0), f"nach {i} Fehlschlaegen noch nicht pausieren"
    pc._run_calendar(oid)
    assert _fails(m, oid) == (pc.CALENDAR_MAX_FAILS, 1)


def test_success_resets_the_counter(m, pc, monkeypatch):
    """Eine voruebergehende Stoerung darf den Kalender nicht dauerhaft abschalten."""
    oid = _offer(m, archived=1)
    monkeypatch.setattr(m, "fetch_calendar", lambda url, **kw: None)
    for _ in range(pc.CALENDAR_MAX_FAILS - 1):
        pc._run_calendar(oid)
    assert _fails(m, oid)[0] == pc.CALENDAR_MAX_FAILS - 1
    monkeypatch.setattr(m, "fetch_calendar",
                        lambda url, **kw: {"ok": True, "days": [{"date": "2027-05-01",
                                                                  "price": 1000.0}]})
    pc._run_calendar(oid)
    assert _fails(m, oid) == (0, 0)


def test_paused_offer_stops_counting(m, pc, monkeypatch):
    """Ist bereits pausiert, zaehlt ein manueller Fehlversuch nicht weiter hoch —
    sonst stuende in der UI irgendwann eine sinnlos grosse Zahl."""
    oid = _offer(m, archived=1, paused=1)
    with m.db() as con:
        con.execute("UPDATE offers SET calendar_fails=? WHERE id=?",
                    (pc.CALENDAR_MAX_FAILS, oid))
    monkeypatch.setattr(m, "fetch_calendar", lambda url, **kw: None)
    pc._run_calendar(oid)
    assert _fails(m, oid) == (pc.CALENDAR_MAX_FAILS, 1)


def test_manual_refresh_revives_a_paused_calendar(m, pc, monkeypatch):
    """„Neu abfragen" auf einem pausierten Kalender: gelingt der Abruf, ist die Pause
    weg — ohne dass der Nutzer zusaetzlich etwas druecken muss."""
    oid = _offer(m, archived=1, paused=1)
    monkeypatch.setattr(m, "fetch_calendar",
                        lambda url, **kw: {"ok": True, "days": [{"date": "2027-05-01",
                                                                  "price": 900.0}]})
    pc._run_calendar(oid)
    assert _fails(m, oid) == (0, 0)


# ── Payload ────────────────────────────────────────────────────────────────────

def test_payload_reports_pause_state(m, pc):
    oid = _offer(m, archived=1, paused=1)
    with m.db() as con:
        con.execute("UPDATE offers SET calendar_fails=7 WHERE id=?", (oid,))
    p = pc._calendar_payload(oid)
    assert p["paused"] is True and p["fails"] == 7 and p["archived"] is True
    assert p["max_fails"] == pc.CALENDAR_MAX_FAILS
    assert p["archived_days"] == m.CALENDAR_ARCHIVED_INTERVAL // 86400


def test_calendar_window_ignores_the_expired_travel_date(m):
    """Der Grund, warum das Ganze ueberhaupt funktioniert: die Kalender-API-URL wird
    mit einem selbst berechneten Fenster ab HEUTE gebaut, das alte (abgelaufene)
    Reisedatum aus der Angebots-URL geht nicht ein."""
    import scraper
    past = (date.today() - timedelta(days=200)).isoformat()
    url = ("https://www.tui.com/pauschalreisen/angebote/h/12345/?duration=7"
           f"&startDate={past}&endDate={past}&travellers=2")
    today = date.today().isoformat()
    far = (date.today() + timedelta(days=540)).isoformat()
    api_url = scraper.build_calendar_api_url(url, start=today, end=far)
    assert past not in api_url
    assert f"startDate={today}" in api_url and f"endDate={far}" in api_url
    assert "giatas=12345" in api_url and "duration=7" in api_url
