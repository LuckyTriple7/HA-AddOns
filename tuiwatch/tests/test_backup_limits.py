"""Restore gegen aufgeblähte Archive und Fremdschlüssel-Erzwingung in `db()`.

Das Flask-Limit `MAX_CONTENT_LENGTH` deckelt nur die **komprimierte** Uploadgröße.
Ein ZIP, das darunter bleibt, kann sich beim Entpacken auf ein Vielfaches aufblähen
— hier wird geprüft, dass der Restore das erkennt, statt den Container über den
Speicher abzuschießen.
"""
import importlib
import io
import json
import sqlite3
import time
import zipfile

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}


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
    m.init_db()
    monkeypatch.setattr(m, "check_offer", lambda *a, **k: None)
    return m


def _zip(members: dict) -> bytes:
    """ZIP mit maximaler Kompression — genau der Fall, der klein hochlädt und
    groß entpackt."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, blob in members.items():
            z.writestr(name, blob)
    return buf.getvalue()


def _restore(client, blob: bytes):
    return client.post("/api/restore", headers=ING,
                       data={"file": (io.BytesIO(blob), "backup.zip")},
                       content_type="multipart/form-data")


# ── Entpackte Größe ─────────────────────────────────────────────────────────

def test_restore_rejects_oversized_data_json(app_mod, monkeypatch):
    """data.json über dem Einzel-Limit wird abgelehnt, ohne vorher komplett im
    Speicher zu landen."""
    backup_routes = importlib.import_module("backup_routes")
    monkeypatch.setattr(backup_routes, "_RESTORE_MAX_JSON_BYTES", 1024)
    blob = _zip({"data.json": b" " * 20_000 + b'{"offers": []}'})
    assert len(blob) < 1024, "Testvoraussetzung: komprimiert winzig, entpackt zu groß"
    r = _restore(app_mod.app.test_client(), blob)
    assert r.status_code == 413
    assert r.get_json()["error"] == "too_large"


def test_restore_rejects_too_many_members(app_mod, monkeypatch):
    backup_routes = importlib.import_module("backup_routes")
    monkeypatch.setattr(backup_routes, "_RESTORE_MAX_MEMBERS", 5)
    members = {"data.json": b'{"offers": []}'}
    for i in range(10):
        members[f"trips/f{i}.pdf"] = b"%PDF-1.4"
    r = _restore(app_mod.app.test_client(), _zip(members))
    assert r.status_code == 413


def test_restore_stops_when_total_budget_is_used_up(app_mod, monkeypatch):
    """Ein einzelnes Mitglied darf klein genug sein — in Summe muss trotzdem
    Schluss sein, sonst schöpft ein Archiv das Einzel-Limit beliebig oft aus."""
    backup_routes = importlib.import_module("backup_routes")
    monkeypatch.setattr(backup_routes, "_RESTORE_MAX_TOTAL_BYTES", 8192)
    members = {"data.json": b'{"offers": []}'}
    for i in range(20):
        members[f"trips/f{i}.pdf"] = b"%PDF-1.4" + b"\x00" * 4096
    r = _restore(app_mod.app.test_client(), _zip(members))
    assert r.status_code == 413


def test_restore_accepts_a_normal_archive(app_mod):
    """Gegenprobe: ein gewöhnliches Backup darf von den Limits nichts merken."""
    payload = {"tuiwatch_backup": 7, "offers": [], "trips": [], "saved_searches": []}
    blob = _zip({"data.json": json.dumps(payload).encode("utf-8"),
                 "trips/reise.pdf": b"%PDF-1.4 klein"})
    r = _restore(app_mod.app.test_client(), blob)
    assert r.status_code == 200


def test_restore_skips_a_single_huge_pdf_but_keeps_going(app_mod, monkeypatch):
    """Eine zu große Einzeldatei wird übersprungen, nicht das ganze Backup
    verworfen — der Rest der Wiederherstellung ist deshalb nicht wertlos."""
    monkeypatch.setattr(app_mod, "MAX_PDF_BYTES", 64)
    payload = {"tuiwatch_backup": 7, "offers": [], "trips": [], "saved_searches": []}
    blob = _zip({"data.json": json.dumps(payload).encode("utf-8"),
                 "trips/riesig.pdf": b"%PDF-1.4" + b"\x00" * 100_000,
                 "trips/klein.pdf": b"%PDF-1.4"})
    r = _restore(app_mod.app.test_client(), blob)
    assert r.status_code == 200


# ── Fremdschlüssel ──────────────────────────────────────────────────────────

def test_db_connection_enforces_foreign_keys(app_mod):
    with app_mod.db() as con:
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_child_row_without_parent_is_rejected(app_mod):
    """Vorher hing so eine Zeile unbemerkt in der Luft und tauchte in Auswertungen
    auf, obwohl das Angebot dazu nicht existierte."""
    with app_mod.db() as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO price_history (offer_id, ts, price, ok) "
                        "VALUES (?,?,?,?)", (999999, int(time.time()), 100.0, 1))


def test_deleting_an_offer_cascades_to_its_history(app_mod):
    with app_mod.db() as con:
        oid = con.execute("INSERT INTO offers (url, created) VALUES (?,?)",
                          ("https://x.invalid/a/", int(time.time()))).lastrowid
        con.execute("INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,?)",
                    (oid, 1000, 100.0, 1))
        con.execute("DELETE FROM offers WHERE id=?", (oid,))
        assert con.execute("SELECT COUNT(*) FROM price_history WHERE offer_id=?",
                           (oid,)).fetchone()[0] == 0
