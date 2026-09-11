#!/usr/bin/env python3
"""ReactorSim — Kernkraftwerks-Leitstand als Browser-Spiel.

Kein Home-Assistant-Add-on: der Ordner enthaelt bewusst keine config.yaml,
sonst wuerde der Supervisor ihn als Add-on einlesen. Betrieb ausschliesslich
ueber docker-compose (Dockge).

Die gesamte Simulation laeuft im Browser. Dieser Server liefert nur die Seite,
die Uebersetzungen, /health fuer den Healthcheck und spaeter eine kleine
JSON-Schnittstelle fuer Spielstaende und Bestenliste.
"""

import json
import logging
import os
import signal

from flask import (Flask, jsonify, make_response, redirect, render_template,
                   request, send_from_directory)
from waitress import serve

logging.basicConfig(format='[%(levelname)s] [%(asctime)s] %(message)s',
                    level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
for _noisy in ('waitress', 'waitress.queue'):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# ── Pfade ─────────────────────────────────────────────────────────────────────

_BASE = os.environ.get('REACTORSIM_BASE', '/app')
_DATA = os.environ.get('REACTORSIM_DATA', '/data')

LOCALES_PATH = _BASE + '/locales'
STATIC_PATH = _BASE + '/static'
SCENARIO_PATH = STATIC_PATH + '/data/scenarios'
VERSION_PATH = _BASE + '/VERSION'

PORT = int(os.environ.get('REACTORSIM_PORT', '17779'))

# Eine einzige Versionsquelle: die Datei VERSION. Sie ist zugleich der Ausloeser
# des Build-Workflows, deshalb kann sie hier nicht auseinanderlaufen. Der
# Rueckfallwert greift nur, wenn jemand app.py ohne die Datei startet.
_FALLBACK_VERSION = '0.0.1'


def _read_version() -> str:
    try:
        with open(VERSION_PATH, 'r', encoding='utf-8') as f:
            v = f.read().strip()
        return v or _FALLBACK_VERSION
    except OSError:
        return _FALLBACK_VERSION


APP_VERSION = _read_version()

app = Flask(__name__, template_folder=_BASE + '/templates',
            static_folder=STATIC_PATH)
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024

# ── i18n ──────────────────────────────────────────────────────────────────────

_LANGS = ('de', 'en')
_translations: dict[str, dict] = {}


def load_translations(lang: str) -> dict:
    """Uebersetzungen liegen fest im Image, also einmal lesen und behalten."""
    lang = lang if lang in _LANGS else 'en'
    cached = _translations.get(lang)
    if cached is not None:
        return cached
    try:
        with open(f'{LOCALES_PATH}/{lang}.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        log.error("Sprachdatei %s.json nicht lesbar: %s", lang, exc.__class__.__name__)
        data = {}
    _translations[lang] = data
    return data


def detect_language(req) -> str:
    lang = req.cookies.get('lang')
    if lang in _LANGS:
        return lang
    accept = (req.headers.get('Accept-Language') or '').lower()
    return 'de' if accept.startswith('de') else 'en'


# ── Szenarien ─────────────────────────────────────────────────────────────────
# Die Dateien liegen fest im Image. Einmal beim Start einlesen -- das ergibt
# zugleich die Whitelist gueltiger Szenariokennungen fuer die spaetere
# Bestenliste: nur was hier steht, darf ein Client als Szenario nennen.

def _load_scenarios() -> list:
    out = []
    try:
        names = sorted(os.listdir(SCENARIO_PATH))
    except OSError:
        return out
    for name in names:
        if not name.endswith('.json'):
            continue
        try:
            with open(os.path.join(SCENARIO_PATH, name), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            log.error("Szenario %s nicht lesbar: %s", name, exc.__class__.__name__)
            continue
        if not isinstance(data, dict) or not data.get('id'):
            continue
        out.append({
            'id': data['id'],
            'file': name,
            'reactor': data.get('reactor'),
            'difficulty': data.get('difficulty', 1),
            'title_key': data.get('title_key'),
            'brief_key': data.get('brief_key'),
            'duration_s': data.get('duration_s', 0),
        })
    return out


SCENARIOS = _load_scenarios()
SCENARIO_IDS = frozenset(s['id'] for s in SCENARIOS)


@app.route('/api/meta')
def meta():
    return jsonify({
        'version': APP_VERSION,
        'scenarios': SCENARIOS,
    })


# ── Seiten ────────────────────────────────────────────────────────────────────


@app.route('/')
def index():
    lang = detect_language(request)
    return render_template('index.html',
                           t=load_translations(lang),
                           lang=lang,
                           app_version=APP_VERSION)


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': APP_VERSION})


@app.route('/set-lang/<lang>')
def set_lang(lang: str):
    # Feste Literale statt Durchreichen des Pfadsegments: der Cookie-Wert ist
    # immer eine dieser beiden fest verdrahteten Zeichenketten, nie die
    # Anfragedaten selbst.
    lang = {'de': 'de', 'en': 'en'}.get(lang, 'en')
    resp = make_response(redirect('/'))
    resp.set_cookie('lang', lang, max_age=365 * 24 * 3600, samesite='Lax')
    return resp


@app.route('/s/<ver>/<path:filename>')
def vstatic(ver: str, filename: str):
    """Pfadversionierte Statics.

    `?v=` bustet keine ES-Modul-Unterimporte: der Browser holt ./sim/engine.js
    unter genau dieser URL, ohne Query-String, und liefert nach einem Versions-
    sprung eine neue main.js gegen dreissig veraltete Module. Steckt die Version
    im Pfad, erben alle relativen Importe sie automatisch, und die Dateien
    duerfen unbegrenzt gecacht werden.

    `ver` wird nicht geprueft -- der Wert waehlt keine Datei aus, er trennt nur
    Cache-Generationen. send_from_directory verhindert das Ausbrechen aus
    static/ von sich aus.
    """
    return send_from_directory(STATIC_PATH, filename, max_age=31536000)


# ── Start ─────────────────────────────────────────────────────────────────────


def _handle_sigterm(_signum, _frame):
    log.info("ReactorSim wird beendet")
    os._exit(0)


def _serve() -> None:
    """Waitress statt Flasks Entwicklungsserver.

    Werkzeugs Server legt pro Anfrage einen Thread ohne Obergrenze an und kennt
    kein Timeout fuer haengende Verbindungen -- auf einem offenen LAN-Port ist
    das angreifbar. Nebenbei verriet er Framework und exakte Python-Version im
    Server-Header.
    """
    log.info("ReactorSim %s laeuft auf Port %d", APP_VERSION, PORT)
    serve(app, host='0.0.0.0', port=PORT, threads=8,
          ident=None,
          max_request_body_size=app.config['MAX_CONTENT_LENGTH'])


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _handle_sigterm)
    os.makedirs(_DATA, exist_ok=True)
    _serve()
