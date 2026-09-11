#!/usr/bin/env python3
"""Beide Sprachdateien muessen dieselben Schluessel und dieselben Platzhalter
tragen. Ein fehlender Schluessel zeigt im Spiel den Schluesselnamen an -- gut
sichtbar, aber peinlich; ein abweichender Platzhalter zeigt "{n}" im Satz.
"""

import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
PLACEHOLDER = re.compile(r'\{(\w+)\}')


def _load(lang):
    with open(os.path.join(_ROOT, 'locales', f'{lang}.json'), encoding='utf-8') as f:
        return json.load(f)


def test_same_keys():
    de, en = _load('de'), _load('en')
    assert set(de) == set(en), f"nur de: {sorted(set(de) - set(en))}, nur en: {sorted(set(en) - set(de))}"
    assert len(de) > 250


def test_same_placeholders():
    de, en = _load('de'), _load('en')
    for key in de:
        a = set(PLACEHOLDER.findall(de[key]))
        b = set(PLACEHOLDER.findall(en[key]))
        assert a == b, f'{key}: de {sorted(a)} gegen en {sorted(b)}'


def test_no_empty_values():
    for lang in ('de', 'en'):
        data = _load(lang)
        for key, value in data.items():
            assert isinstance(value, str) and value.strip(), f'{lang}: {key} ist leer'


def test_no_german_hardcoded_in_templates_or_js():
    """Stichprobe auf Umlaute ausserhalb von Kommentaren.

    Der Code ist durchgehend deutsch kommentiert, deshalb wird nur
    ausgewertet, was NICHT in einem Kommentar steht.
    """
    suspicious = []
    for rel_dir in ('templates', os.path.join('static', 'js')):
        for root, _dirs, files in os.walk(os.path.join(_ROOT, rel_dir)):
            for name in files:
                if not name.endswith(('.html', '.js')):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding='utf-8') as f:
                    src = f.read()
                src = re.sub(r'/\*[\s\S]*?\*/', '', src)
                src = re.sub(r'(^|\s)//.*$', '', src, flags=re.M)
                src = re.sub(r'<!--[\s\S]*?-->', '', src)
                for line in src.splitlines():
                    if re.search(r'[äöüÄÖÜß]', line) and 'locales' not in line:
                        suspicious.append(f'{os.path.relpath(path, _ROOT)}: {line.strip()[:80]}')
    assert not suspicious, 'fest verdrahteter deutscher Text:\n' + '\n'.join(suspicious)
