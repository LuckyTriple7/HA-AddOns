#!/usr/bin/env python3
"""Kommt alles ins Image, was die Seite braucht?

Ein vergessenes Python-Modul stuerzt beim Start ab und faellt sofort auf. Ein
vergessenes ES-Modul nicht: der Browser holt es, bekommt 404, und die
Oberflaeche bleibt halb tot -- ohne Eintrag im Add-on-Protokoll. Dieser Test
laeuft den Importgraph ab main.js ab und prueft jede erreichte Datei gegen die
COPY-Zeilen des Dockerfiles.
"""

import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

IMPORT_RE = re.compile(r"""(?:^|\s)(?:import|export)\s[^'"]*?from\s+['"]([^'"]+)['"]""", re.M)
DYNAMIC_RE = re.compile(r"""import\(\s*['"]([^'"]+)['"]\s*\)""")


def _copy_targets():
    """Pfade, die das Dockerfile nach /app bringt."""
    out = []
    with open(os.path.join(_ROOT, 'Dockerfile'), encoding='utf-8') as f:
        for line in f:
            m = re.match(r'^COPY\s+(\S+)\s+(\S+)\s*$', line.strip())
            if not m:
                continue
            src = m.group(1)
            if src.startswith('/'):
                continue
            out.append(src.rstrip('/'))
    return out


def _covered(rel_path, targets):
    # Die COPY-Ziele stehen mit Schraegstrich im Dockerfile, os.path.relpath()
    # liefert unter Windows aber Backslashes. Ohne die Normalisierung schlug
    # der Test dort bei JEDEM Modul in einem Unterordner fehl -- also genau bei
    # denen, die er pruefen soll, und das ganz ohne echten Befund.
    rel_path = rel_path.replace(os.sep, '/')
    for t in targets:
        if rel_path == t or rel_path.startswith(t + '/'):
            return True
    return False


def _walk_imports(entry):
    seen = set()
    stack = [entry]
    while stack:
        path = stack.pop()
        if path in seen or not os.path.exists(path):
            continue
        seen.add(path)
        with open(path, encoding='utf-8') as f:
            src = f.read()
        for spec in IMPORT_RE.findall(src) + DYNAMIC_RE.findall(src):
            if not spec.startswith('.'):
                continue
            stack.append(os.path.normpath(os.path.join(os.path.dirname(path), spec)))
    return seen


def test_every_reachable_module_is_copied():
    targets = _copy_targets()
    entry = os.path.join(_ROOT, 'static', 'js', 'main.js')
    assert os.path.exists(entry), 'main.js fehlt'
    modules = _walk_imports(entry)
    assert len(modules) > 20, f'nur {len(modules)} Module erreicht -- Graph kaputt?'
    for path in sorted(modules):
        rel = os.path.relpath(path, _ROOT)
        assert _covered(rel, targets), f'{rel} wird nicht ins Image kopiert'


def test_python_modules_are_copied():
    targets = _copy_targets()
    for name in ('app.py', 'auth.py', 'persist.py', 'scoring.py', 'atomic_io.py', 'VERSION'):
        assert _covered(name, targets), f'{name} fehlt im Dockerfile'


def test_dev_only_files_stay_out():
    targets = _copy_targets()
    for name in ('dev_run.py', 'dev_data', 'tests'):
        assert not _covered(name, targets), f'{name} landet im Image'


def test_templates_and_locales_are_copied():
    targets = _copy_targets()
    for rel in ('templates/index.html', 'locales/de.json', 'locales/en.json',
                'static/data/scenarios/pwr_load_follow.json'):
        assert os.path.exists(os.path.join(_ROOT, rel)), f'{rel} fehlt'
        assert _covered(rel, targets), f'{rel} wird nicht ins Image kopiert'
