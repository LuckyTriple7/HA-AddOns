"""Jeder inline-Handler in index.html muss auch eine Funktion haben.

Diese Fehlerart faellt sonst nirgends auf: `node --check` sieht nur die Datei,
in der die Funktion fehlt, nicht das Template, das sie aufruft. Ein umbenannter
oder entfernter Handler bleibt bis zum Klick unbemerkt -- und dann passiert
schlicht nichts, ohne Meldung in der Oberflaeche.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "templates" / "index.html"
JS = ROOT / "static" / "app.js"

_HANDLER = re.compile(r'on(?:click|change|input|submit)="([A-Za-z_$][\w$]*)\s*\(')
_FUNC = re.compile(r'function\s+([A-Za-z_$][\w$]*)\s*\(')
_ASSIGNED = re.compile(r'(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function|\()')
_WINDOW = re.compile(r'window\.([A-Za-z_$][\w$]*)\s*=')


def test_jeder_inline_handler_ist_definiert():
    html = HTML.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    defined = set(_FUNC.findall(js)) | set(_ASSIGNED.findall(js)) | set(_WINDOW.findall(js))
    defined |= set(_FUNC.findall(html))          # wenige Handler stehen im Template selbst
    used = set(_HANDLER.findall(html))
    assert used, "keine Handler gefunden — Regex passt nicht mehr zum Template"
    assert sorted(used - defined) == []


def test_markdown_knopf_kopiert_statt_herunterzuladen():
    """Regression: der Markdown-Knopf der KI-Antworten war erst ein Datei-Download.
    Gewuenscht ist dieselbe Zwischenablage wie bei Klimatabelle und Reisefuehrer."""
    html = HTML.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    assert 'onclick="copyAiMd()"' in html
    assert "exportAiMarkdown" not in html and "exportAiMarkdown" not in js
    assert "copyText(md," in js          # geht ueber denselben Helfer wie copyGuideMd
