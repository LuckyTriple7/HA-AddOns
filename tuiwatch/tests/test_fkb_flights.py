"""Tests für fkb_flights_client.py (Saisonflugplan Karlsruhe/Baden-Baden).

Das Markup stammt 1:1 aus der echten Antwort von `admin-ajax.php?action=flightmap`
(siehe SCRAPING_FKB.md) — gekürzt auf zwei Zeilen, aber mit allen Eigenheiten:
Wochentage in zwei `flight-days-row`-Blöcken, Sitzplatzangabe im `data-bs-title`
des Info-Knopfs, Airline als Link. Kein Netzabruf im Testlauf.
"""
import pytest

import fkb_flights_client as fkb


@pytest.fixture(autouse=True)
def _reset_cache():
    with fkb._cache_lock:
        fkb._cache.update(rows=None, fetched_at=0.0)
    yield
    with fkb._cache_lock:
        fkb._cache.update(rows=None, fetched_at=0.0)


POSTS = """
<div class="flight-table__body" role="rowgroup" tabindex="0">
  <div role="row" class="flight-table__row gx-3 row g-0 border-bottom">
    <div role="cell" class="flight-table__col flight-table__col__origin d-flex flex-column col">
      <div class="my-auto">
        <span class="body-lg d-block fw-bold position-relative">Palma de Mallorca (PMI)</span>
        <span class="body-lg d-block pt-1 position-relative">FR 5182</span>
      </div>
    </div>
    <div role="cell" class="flight-table__col flight-table__col__type d-flex col py-3">
      <div class="my-auto">
        <span class="body-lg text-uppercase">06:00 - 07:55
        </span>
        <div class="flight-days body-lg d-block d-xl-flex">
  <div class="flight-days-row d-flex">
    <span class="flight-day flight-day--0">-</span>
    <span class="flight-day flight-day--1">-</span>
    <span class="flight-day flight-day--2">Mi</span>
  </div>
  <div class="flight-days-row d-flex">
    <span class="flight-day flight-day--3">-</span>
    <span class="flight-day flight-day--4">Fr</span>
    <span class="flight-day flight-day--5">-</span>
    <span class="flight-day flight-day--6">-</span>
  </div>
</div>
      </div>
    </div>
    <div role="cell" class="flight-table__col flight-table__col__validity d-flex col py-3">
      <span class="body-lg text-uppercase my-auto">
        01.04.2026 - 21.10.2026
          <span class="body-md">(Sommerflugplan 2026)</span>
      </span>
    </div>
    <div role="cell" class="flight-table__col flight-table__col__plane d-flex col py-3">
      <div class="d-flex my-auto">
        <span class="body-lg text-uppercase my-auto">Boeing 737-800</span>
        <button title="Info zum Flugezugtyp" class="flight-table-info-button"
          type="button" data-bs-toggle="popover" data-bs-title="189 Sitzpl&auml;tze"
          data-bs-placement="top" data-bs-trigger="hover"></button>
      </div>
    </div>
    <div role="cell" class="flight-table__col flight-table__col__airline d-flex col py-3">
      <a href="https://www.ryanair.com/" class="body-lg textlink">Ryanair</a>
    </div>
  </div>
  <div role="row" class="flight-table__row gx-3 row g-0 border-bottom">
    <div role="cell" class="flight-table__col flight-table__col__origin d-flex flex-column col">
      <div class="my-auto">
        <span class="body-lg d-block fw-bold position-relative">Antalya (AYT)</span>
        <span class="body-lg d-block pt-1 position-relative">XQ 351</span>
      </div>
    </div>
    <div role="cell" class="flight-table__col flight-table__col__type d-flex col py-3">
      <div class="my-auto">
        <span class="body-lg text-uppercase">14:20 - 18:35</span>
        <div class="flight-days body-lg d-block d-xl-flex">
  <div class="flight-days-row d-flex">
    <span class="flight-day flight-day--0">Mo</span>
    <span class="flight-day flight-day--1">Di</span>
    <span class="flight-day flight-day--2">Mi</span>
  </div>
  <div class="flight-days-row d-flex">
    <span class="flight-day flight-day--3">Do</span>
    <span class="flight-day flight-day--4">Fr</span>
    <span class="flight-day flight-day--5">Sa</span>
    <span class="flight-day flight-day--6">So</span>
  </div>
</div>
      </div>
    </div>
    <div role="cell" class="flight-table__col flight-table__col__validity d-flex col py-3">
      <span class="body-lg text-uppercase my-auto">
        01.11.2026 - 27.03.2027
          <span class="body-md">(Winterflugplan 2026/2027)</span>
      </span>
    </div>
    <div role="cell" class="flight-table__col flight-table__col__plane d-flex col py-3">
      <div class="d-flex my-auto">
        <span class="body-lg text-uppercase my-auto">Airbus A 321</span>
      </div>
    </div>
    <div role="cell" class="flight-table__col flight-table__col__airline d-flex col py-3">
      SunExpress
    </div>
  </div>
</div>
"""


# ── Reine Helfer ───────────────────────────────────────────────────────────────

def test_iso_date():
    assert fkb._iso_date("01.04.2026") == "2026-04-01"
    assert fkb._iso_date("") == ""
    assert fkb._iso_date("1.4.26") == ""


def test_weekdays_short():
    rows = fkb._parse_rows(POSTS, "departure")
    assert rows[0]["weekdays_short"] == "Mi, Fr"
    assert rows[1]["weekdays_short"] == "täglich"


# ── Parsen ─────────────────────────────────────────────────────────────────────

def test_parse_rows_reads_all_columns():
    rows = fkb._parse_rows(POSTS, "departure")
    assert len(rows) == 2
    r = rows[0]
    assert r == {
        "direction": "departure", "airline_code": "FR", "airline_name": "Ryanair",
        "flight_no": "FR 5182", "airport_code": "PMI", "airport_name": "Palma de Mallorca",
        "country": "", "departure": "06:00", "arrival": "07:55",
        "weekdays_short": "Mi, Fr", "date_from": "2026-04-01", "date_till": "2026-10-21",
        "season": "Sommerflugplan 2026", "plane": "Boeing 737-800",
        "seats": "189 Sitzplätze",
    }
    # Airline auch ohne Link, Flugzeugtyp auch ohne Sitzplatz-Knopf
    assert rows[1]["airline_name"] == "SunExpress"
    assert rows[1]["plane"] == "Airbus A 321"
    assert rows[1]["seats"] == ""


def test_parse_rows_skips_incomplete():
    """Zeilen ohne Ziel oder Zeiten fliegen raus, ohne den Rest zu verlieren."""
    broken = POSTS.replace("06:00 - 07:55", "")
    rows = fkb._parse_rows(broken, "departure")
    assert [r["airport_code"] for r in rows] == ["AYT"]
    assert fkb._parse_rows("", "departure") == []


# ── Abruf, Cache, Filter ───────────────────────────────────────────────────────

class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _ok(monkeypatch, counter=None):
    def fake_post(url, **kw):
        if counter is not None:
            counter.append(kw.get("json"))
        direction = (kw.get("json") or {}).get("type")
        posts = POSTS if direction == "departures" else POSTS.replace("PMI", "TFS")
        return _Resp({"success": True, "data": {"posts": posts, "mapRoutes": []}})
    monkeypatch.setattr(fkb.requests, "post", fake_post)


def test_search_both_directions_and_cache(monkeypatch):
    calls: list = []
    _ok(monkeypatch, calls)
    res = fkb.search("")
    assert res["total"] == 4 and res["count"] == 4
    assert {r["direction"] for r in res["rows"]} == {"departure", "arrival"}
    # zwei Abrufe (je Richtung einer), danach bedient der Cache
    assert [c["type"] for c in calls] == ["departures", "arrivals"]
    fkb.search("")
    assert len(calls) == 2


def test_search_filters(monkeypatch):
    _ok(monkeypatch)
    assert fkb.search("PMI", direction="departure")["total"] == 1
    assert fkb.search("ryanair")["total"] == 2          # Airline zählt zur Suche
    assert fkb.search("", direction="arrival")["total"] == 2
    # Zeitraum: Überschneidung genügt, Winterstrecke fällt im Sommerfenster raus
    assert fkb.search("AYT", date_from="2026-05", date_till="2026-06")["total"] == 0
    assert fkb.search("AYT", date_from="2027-01", date_till="2027-02")["total"] == 2


def test_list_destinations_only_departures(monkeypatch):
    _ok(monkeypatch)
    dests = fkb.list_destinations()
    assert [d["code"] for d in dests] == ["AYT", "PMI"]


def test_type_must_be_string_not_list(monkeypatch):
    """Der Client schickt `type` als String — als Liste antwortet die Seite mit
    success:false (siehe SCRAPING_FKB.md)."""
    calls: list = []
    _ok(monkeypatch, calls)
    fkb.search("")
    assert all(isinstance(c["type"], str) for c in calls)
    assert all(c["limit"] == -1 and c["airport"] == "all" for c in calls)


def test_error_keeps_previous_cache(monkeypatch):
    _ok(monkeypatch)
    assert fkb.search("")["total"] == 4
    with fkb._cache_lock:      # Cache künstlich altern lassen
        fkb._cache["fetched_at"] = 0.0

    def failing_post(url, **kw):
        return _Resp({"success": False, "data": "FlightType::tryFrom(): …"}, 200)
    monkeypatch.setattr(fkb.requests, "post", failing_post)
    res = fkb.search("")
    assert res is not None and res["total"] == 4   # alter Stand bleibt nutzbar
    assert fkb.refresh() is False


def test_fetch_failure_without_cache_returns_none(monkeypatch):
    def boom(url, **kw):
        raise RuntimeError("Netz weg")
    monkeypatch.setattr(fkb.requests, "post", boom)
    assert fkb.search("") is None
    assert fkb.list_destinations() is None


def test_empty_marker_is_not_parsed(monkeypatch):
    """`posts: "empty"` heißt „Anfrageform stimmt nicht" — leere Liste, kein Crash."""
    monkeypatch.setattr(fkb.requests, "post",
                        lambda url, **kw: _Resp({"success": True, "data": {"posts": "empty"}}))
    res = fkb.search("")
    assert res is not None and res["total"] == 0
