#!/usr/bin/env python3
"""Lokaler Teststart — wird nicht ins Image kopiert.

Legt beim ersten Lauf dev_data/options.json an und startet NetToolbox mit
Pfaden im Projektordner statt unter /app und /data.
"""
import json
import os
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / 'dev_data'
DATA.mkdir(exist_ok=True)

OPTIONS = DATA / 'options.json'
if not OPTIONS.exists():
    OPTIONS.write_text(json.dumps({
        'username': 'admin',
        'password': 'devpass',
        'session_hours': 24,
        'worker_url': '',
        'worker_token': '',
        'worker_tls_verify': True,
        'worker_enabled': False,
        'resolvers': ['9.9.9.9', '1.1.1.1'],
        'dns_timeout': 5,
        'http_timeout': 10,
        'allow_private_targets': False,
        'rate_limit_per_min': 60,
        'history_size': 200,
        'verbose_log': True,
    }, indent=2), encoding='utf-8')
    print(f'angelegt: {OPTIONS} — Zugangsdaten dort eintragen')

os.environ.setdefault('NETTOOLBOX_BASE', str(HERE))
os.environ.setdefault('NETTOOLBOX_DATA', str(DATA))
os.environ.setdefault('NETTOOLBOX_OPTIONS', str(DATA))

import app  # noqa: E402  — erst nach den Umgebungsvariablen importieren

if __name__ == '__main__':
    port = int(os.environ.get('NETTOOLBOX_PORT', app.PORT))
    app.load_sessions()
    app.load_blocks()
    app.history_load()
    app._startup_checks()
    print(f'NetToolbox dev auf http://127.0.0.1:{port}')
    # Bewusst derselbe Server wie im Container (app._serve, Waitress) statt
    # app.app.run: sonst prueft der Testlauf einen anderen Stack als den, der
    # ausgeliefert wird -- der fehlende Server-Header etwa waere hier nie
    # aufgefallen.
    app._serve(port)
