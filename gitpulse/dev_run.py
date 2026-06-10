#!/usr/bin/env python3
"""
Lokales Entwicklungs-Startskript für GitPulse.

Verwendung:
    python dev_run.py
    python dev_run.py --token ghp_xxxx
    python dev_run.py --repo LuckyTriple7/HA-AddOns

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

parser = argparse.ArgumentParser(description='GitPulse lokal starten')
parser.add_argument('--token',    default=os.environ.get('GITHUB_TOKEN', ''), help='GitHub Token')
parser.add_argument('--user',     default='admin',  help='Login-Benutzername')
parser.add_argument('--password', default='admin',  help='Login-Passwort')
parser.add_argument('--repo',     default='',       help='Eigenes Repo (owner/repo)')
args = parser.parse_args()

DATA.mkdir(exist_ok=True)

options_path = DATA / 'options.json'
if not options_path.exists() or args.token:
    options = {
        'username':           args.user,
        'password':           args.password,
        'session_hours':      24,
        'github_token':       args.token,
        'my_repos':           [args.repo] if args.repo else [],
        'watch_repos':        ['home-assistant/core'],
        'include_ha_betas':   True,
        'poll_interval':      60,
        'verbose_log':        True,
        'workflow_run_limit': 25,
        'addon_manager':      True,
        'digest_hour':        -1,
        'telegram_bot_token': '',
        'telegram_chat_id':   '',
        'webhook_secret':     '',
        'smtp_host':          '',
        'smtp_port':          587,
        'smtp_user':          '',
        'smtp_password':      '',
        'smtp_to':            '',
        'smtp_tls':           True,
    }
    options_path.write_text(json.dumps(options, indent=2), encoding='utf-8')
    print(f'Config: {options_path}')

env = {**os.environ,
       'GITPULSE_BASE': str(HERE),
       'GITPULSE_DATA': str(DATA)}

print(f'GitPulse startet auf http://localhost:17792')
print(f'Login: {args.user} / {args.password}')
print('Strg+C zum Beenden\n')

subprocess.run([sys.executable, str(HERE / 'app.py')], env=env)
