"""`X-Ingress-Path` darf nur mit HA-Supervisor als Authentifizierung gelten.

Der Header kommt vom Client. Im Add-on setzt ihn ausschliesslich der Supervisor,
und `_auth_ok` behandelt einen daraus gesetzten SCRIPT_NAME als bereits
authentifiziert. Laeuft TUIWatch ohne Supervisor (eigener Docker-Host, Server im
Netz), waere derselbe Header eine Login-Umgehung — genau das pruefen die Tests.
"""
import importlib

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}


def _load(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        m = importlib.import_module("app")
    except Exception as exc:                     # pragma: no cover
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(m)
    m.DB_PATH = str(tmp_path / "tuiwatch.db")
    m.init_db()
    return m


def test_header_ignored_without_supervisor(tmp_path, monkeypatch):
    monkeypatch.delenv("TUIWATCH_TRUST_INGRESS", raising=False)
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    m = _load(tmp_path, monkeypatch)
    assert m.TRUST_INGRESS is False
    assert m.app.test_client().get("/api/offers", headers=ING).status_code == 401


def test_header_trusted_with_supervisor_token(tmp_path, monkeypatch):
    monkeypatch.delenv("TUIWATCH_TRUST_INGRESS", raising=False)
    monkeypatch.setenv("SUPERVISOR_TOKEN", "dummy")
    m = _load(tmp_path, monkeypatch)
    assert m.TRUST_INGRESS is True
    assert m.app.test_client().get("/api/offers", headers=ING).status_code == 200


def test_override_forces_trust(tmp_path, monkeypatch):
    """Eigener Reverse-Proxy, der den Header selbst setzt: bewusst einschaltbar."""
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setenv("TUIWATCH_TRUST_INGRESS", "1")
    m = _load(tmp_path, monkeypatch)
    assert m.TRUST_INGRESS is True
    assert m.app.test_client().get("/api/offers", headers=ING).status_code == 200


def test_override_can_disable_inside_addon(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "dummy")
    monkeypatch.setenv("TUIWATCH_TRUST_INGRESS", "0")
    m = _load(tmp_path, monkeypatch)
    assert m.TRUST_INGRESS is False
    assert m.app.test_client().get("/api/offers", headers=ING).status_code == 401
