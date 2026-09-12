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


def _quoted_controls(text: str) -> set:
    """Bedienelemente, die ein Hilfetext in Anfuehrungszeichen nennt.

    Deutsche Texte benutzen die typografischen Zeichen, englische die geraden.
    """
    import re
    out = set()
    for m in re.finditer(r'[\u201e\u201c"]([^\u201c\u201d"\n]{2,40})[\u201c\u201d"]', text):
        out.add(m.group(1).strip())
    return out


def test_help_texts_only_name_controls_that_exist():
    """Jedes in einem Hilfetext genannte Bedienelement muss es geben.

    Genau diese Pruefung fehlte, als die Hilfe zu "Frischdampf abgesperrt" als
    einzige Handlung das Oeffnen eines Ventils nannte, das die Stoerung in
    jedem Rechenschritt wieder zudrueckt. Sie faengt nicht jede falsche
    Aussage -- ob eine Handlung in DIESER Lage wirkt, weiss nur der Code --,
    aber sie faengt die haeufigste: ein Bedienelement nennen, das unter diesem
    Namen gar nicht existiert.

    Erlaubt sind ausserdem Anzeigen, Meldungen und Reaktortypen, weil Texte
    sinnvollerweise auch auf sie verweisen.
    """
    import re
    for lang in ('de', 'en'):
        data = _load(lang)
        # Alles, was auf dem Schirm einen Namen hat.
        known = set()
        for key, value in data.items():
            if not isinstance(value, str):
                continue
            if key.split('_')[0] in ('ctl', 'btn', 'val', 'panel', 'tab', 'alarm',
                                     'trip', 'state', 'reactor', 'mimic', 'trend',
                                     'status', 'unit', 'scn', 'ev', 'event', 'opt',
                                     'gl'):   # gl_* = Glossareintraege
                known.add(value.strip())
        # Zusammengesetzte Verweise einzeln pruefen: "Steuerstäbe → Einfahren"
        # nennt Kachel und Knopf, "Ziehen/Einfahren" die beiden Fahrtrichtungen.
        # Jeder Teil muss fuer sich existieren. Es gibt bewusst KEINE
        # Ausnahmeliste -- wer etwas in Anfuehrungszeichen setzt, soll es genau
        # so schreiben, wie es auf dem Schirm steht.
        extra = set()
        missing = []
        for key, text in data.items():
            if not (key.endswith('_help') or key.endswith('_brief')):
                continue
            for quoted in _quoted_controls(text):
                # Erst das Ganze: der Glossartitel "SCRAM / RESA / AZ-5" ist
                # EINE Beschriftung und keine Aufzaehlung. Erst wenn sie so
                # nicht existiert, als zusammengesetzten Verweis zerlegen.
                if quoted in known or quoted in extra:
                    continue
                for part in (p.strip() for p in re.split(r'[→/]', quoted)):
                    if part and part not in known and part not in extra:
                        missing.append(f'{lang}/{key}: „{part}"')
        assert not missing, ('Hilfetext nennt etwas, das es nicht gibt:\n'
                             + '\n'.join(missing))
