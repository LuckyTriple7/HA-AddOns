#!/usr/bin/env python3
"""Lokaler Teststart — wird nicht ins Image kopiert.

Legt beim ersten Lauf dev_data/options.json an und startet CrowdPanel mit
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
        'lapi_url': 'http://127.0.0.1:8080',
        'machine_id': '',
        'machine_password': '',
        'lapi_tls_verify': True,
        'default_ban_duration': '4h',
        'refresh_interval': 30,
        'page_size': 100,
        'verbose_log': True,
    }, indent=2), encoding='utf-8')
    print(f'angelegt: {OPTIONS} — Zugangsdaten dort eintragen')

os.environ.setdefault('CROWDPANEL_BASE', str(HERE))
os.environ.setdefault('CROWDPANEL_DATA', str(DATA))
os.environ.setdefault('CROWDPANEL_OPTIONS', str(DATA))

import app  # noqa: E402  — erst nach den Umgebungsvariablen importieren

if __name__ == '__main__':
    import threading

    port = int(os.environ.get('CROWDPANEL_PORT', app.PORT))
    app.load_sessions()
    app._startup_checks()
    if app.archive_enabled() and app.get_archive() is not None:
        threading.Thread(target=app._archive_worker, daemon=True).start()
        print(f'Alarm-Archiv: {app.ARCHIVE_PATH}')
    print(f'CrowdPanel dev auf http://127.0.0.1:{port}')
    app.app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
