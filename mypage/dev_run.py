#!/usr/bin/env python3
"""
Lokales Entwicklungs-Startskript für MyPage.

Verwendung:
    python dev_run.py
    python dev_run.py --token ghp_xxxx

Voraussetzungen:  pip install flask requests
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
DATA = HERE / 'dev_data'

# .env aus Workspace-Root automatisch laden
_env_file = HERE.parent / '.env'
if _env_file.exists():
    for _line in _env_file.read_text(encoding='utf-8').splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

parser = argparse.ArgumentParser(description='MyPage lokal starten')
parser.add_argument('--token',    default=os.environ.get('GITHUB_TOKEN', ''), help='GitHub Token')
parser.add_argument('--user',     default='admin', help='Login-Benutzername')
parser.add_argument('--password', default='admin', help='Login-Passwort')
args = parser.parse_args()

DATA.mkdir(exist_ok=True)

options_path = DATA / 'options.json'
if not options_path.exists() or args.token:
    options = {
        'username':      args.user,
        'password':      args.password,
        'session_hours': 24,
        'github_token':  args.token,
    }
    options_path.write_text(json.dumps(options, indent=2), encoding='utf-8')
    print(f'Config: {options_path}')

for k, v in {'MYPAGE_BASE': str(HERE), 'MYPAGE_DATA': str(DATA),
             'MYPAGE_OPTIONS': str(DATA)}.items():
    os.environ[k] = v

print('MyPage startet:')
print('  Öffentlich: http://localhost:17760')
print('  Admin:      http://localhost:17761')
print(f'  Login: {args.user} / {args.password}')
print('Strg+C zum Beenden\n')

sys.exit(subprocess.call([sys.executable, str(HERE / 'app.py')]))
