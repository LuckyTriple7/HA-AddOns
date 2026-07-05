"""Tests für die konfigurierbare Websuche-Obergrenze (`ai_max_web_searches`):
_ai_request() muss `max_uses` am web_search-Tool passend zur Add-on-Option
setzen (Default 12, geklammert auf 1..50), um Ausreisser bei den
Input-Tokens/Kosten zu verhindern.
"""
import importlib
import json

import pytest

pytest.importorskip("flask")


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
    return m


class _FakeUsage:
    input_tokens = 100
    output_tokens = 50
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0


class _FakeTextBlock:
    type = "text"
    text = "Antwort"


class _FakeResponse:
    stop_reason = "end_turn"
    content = [_FakeTextBlock()]
    usage = _FakeUsage()


class _FakeMessages:
    def __init__(self, captured):
        self._captured = captured

    def create(self, **kwargs):
        self._captured.append(kwargs)
        return _FakeResponse()


class _FakeClient:
    def __init__(self, captured, **_kwargs):
        self.messages = _FakeMessages(captured)


def _patch_anthropic(app_mod, monkeypatch):
    captured = []
    monkeypatch.setattr(app_mod.anthropic, "Anthropic",
                        lambda **kw: _FakeClient(captured, **kw))
    return captured


def _write_options(app_mod, **opts):
    with open(app_mod.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(opts, f)


def test_web_search_max_uses_defaults_to_12(app_mod, monkeypatch):
    captured = _patch_anthropic(app_mod, monkeypatch)
    app_mod._ai_request("key", "claude-sonnet-5", "Prompt", max_tokens=100, log_ctx="Test")
    assert captured[0]["tools"][0]["max_uses"] == 12


def test_web_search_max_uses_reads_config(app_mod, monkeypatch):
    _write_options(app_mod, ai_max_web_searches=5)
    captured = _patch_anthropic(app_mod, monkeypatch)
    app_mod._ai_request("key", "claude-sonnet-5", "Prompt", max_tokens=100, log_ctx="Test")
    assert captured[0]["tools"][0]["max_uses"] == 5


def test_web_search_max_uses_clamped_to_50(app_mod, monkeypatch):
    _write_options(app_mod, ai_max_web_searches=9999)
    captured = _patch_anthropic(app_mod, monkeypatch)
    app_mod._ai_request("key", "claude-sonnet-5", "Prompt", max_tokens=100, log_ctx="Test")
    assert captured[0]["tools"][0]["max_uses"] == 50


def test_web_search_max_uses_clamped_to_1(app_mod, monkeypatch):
    _write_options(app_mod, ai_max_web_searches=0)
    captured = _patch_anthropic(app_mod, monkeypatch)
    app_mod._ai_request("key", "claude-sonnet-5", "Prompt", max_tokens=100, log_ctx="Test")
    assert captured[0]["tools"][0]["max_uses"] == 1


def test_web_search_disabled_has_no_tools(app_mod, monkeypatch):
    captured = _patch_anthropic(app_mod, monkeypatch)
    app_mod._ai_request("key", "claude-sonnet-5", "Prompt", max_tokens=100, log_ctx="Test",
                        use_web_search=False)
    assert "tools" not in captured[0]
