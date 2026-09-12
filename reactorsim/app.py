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
import secrets
import signal

from urllib.parse import quote

from flask import (Flask, g, jsonify, make_response, redirect, render_template,
                   request, send_from_directory)
from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix

import auth as authmod
import persist
import scoring

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

# Zugangsdaten aus der Umgebung, also aus der Dockge-Konfiguration. Ist kein
# Passwort gesetzt, erzeugt auth.Auth beim ersten Start eines und schreibt es
# ins Protokoll -- offen steht die Seite nie.
REACTORSIM_USER = os.environ.get('REACTORSIM_USER', 'admin')
REACTORSIM_PASSWORD = os.environ.get('REACTORSIM_PASSWORD', '')

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

# Hinter einem Reverse Proxy traegt jede Anfrage dieselbe Absenderadresse,
# naemlich die des Proxys. Ohne ProxyFix teilen sich dann alle Spieler
# dieselbe Ratenbegrenzung. Wer den Port direkt erreicht, kann
# X-Forwarded-For faelschen -- das ist der Preis und aendert nichts daran,
# dass der Punktestand ohnehin serverseitig gerechnet wird.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

STORE = persist.Store(_DATA)
LIMITS = persist.RateLimit()
AUTH = authmod.Auth(_DATA, REACTORSIM_USER, REACTORSIM_PASSWORD)

PLAYER_COOKIE = 'rs_player'

# Was ohne Anmeldung erreichbar bleibt. /health muss offen sein, sonst meldet
# der Healthcheck den Container als krank; die Anmeldeseite selbst kann nicht
# hinter der Anmeldung liegen; /set-lang stellt nur ein Cookie und existiert
# auch auf der Anmeldeseite.
_PUBLIC_ENDPOINTS = frozenset({'health', 'login', 'set_lang'})


@app.before_request
def _require_login():
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    if AUTH.valid(request.cookies.get(authmod.SESSION_COOKIE)):
        return None
    # Anfragen aus dem Spiel heraus bekommen eine Zahl, keine Anmeldeseite --
    # sonst landete HTML im JSON-Parser und der Fehler waere unlesbar.
    if request.path.startswith('/api/'):
        return jsonify({'error': 'unauthorized'}), 401
    return redirect('/login?next=' + quote(authmod.safe_next(request.full_path.rstrip('?')), safe=''))


@app.route('/login', methods=['GET', 'POST'])
def login():
    lang = detect_language(request)
    t = load_translations(lang)
    nxt = authmod.safe_next(request.values.get('next'))
    error = None

    if request.method == 'POST':
        # Gegen Durchprobieren: zehn Versuche je Minute und Absenderadresse.
        addr = request.remote_addr or '-'
        if not LIMITS.hit(f'login:{addr}', 10, 60):
            error = 'login_rate_limited'
        elif not AUTH.csrf_ok(request.form.get('csrf')):
            # Abgelaufenes Formular -- kein Angriff, nur eine alte Seite.
            error = 'login_expired'
        elif AUTH.check(request.form.get('user', ''), request.form.get('password', '')):
            resp = make_response(redirect(nxt))
            resp.set_cookie(authmod.SESSION_COOKIE, AUTH.issue(),
                            max_age=authmod.SESSION_MAX_AGE, httponly=True,
                            samesite='Lax', secure=request.is_secure)
            return resp
        else:
            error = 'login_failed'

    resp = make_response(render_template(
        'login.html', t=t, lang=lang, app_version=APP_VERSION,
        csrf=AUTH.csrf_token(), next_url=nxt, error=error,
        prefill=request.form.get('user', '') if request.method == 'POST' else ''))
    resp.headers['Cache-Control'] = 'no-store'
    return resp, (401 if error else 200)


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    resp = make_response(redirect('/login'))
    resp.delete_cookie(authmod.SESSION_COOKIE)
    return resp


# ── i18n ──────────────────────────────────────────────────────────────────────

_LANGS = ('de', 'en')
_translations: dict[str, dict] = {}


_LOCALE_FILES = {'de': 'de.json', 'en': 'en.json'}


def load_translations(lang: str) -> dict:
    """Uebersetzungen liegen fest im Image, also einmal lesen und behalten.

    Der Dateiname kommt aus `_LOCALE_FILES`, einem festen Literal je Sprache --
    `lang` selbst geht nie in den Pfad ein, egal was hereinkommt."""
    lang = lang if lang in _LANGS else 'en'
    cached = _translations.get(lang)
    if cached is not None:
        return cached
    filename = _LOCALE_FILES.get(lang, 'en.json')
    try:
        with open(os.path.join(LOCALES_PATH, filename), 'r', encoding='utf-8') as f:
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
SCENARIO_BY_ID = {s['id']: s for s in SCENARIOS}

# Nennleistung je Reaktortyp. Sie begrenzt, wie viel Energie ein Lauf
# ueberhaupt geliefert haben kann -- ohne diese Obergrenze waere die
# Plausibilitaetspruefung der Bestenliste zahnlos.
REACTOR_P0 = {'pwr': 1400.0, 'bwr': 1344.0, 'rbmk': 1000.0}


@app.route('/api/meta')
def meta():
    return jsonify({
        'version': APP_VERSION,
        'scenarios': SCENARIOS,
    })


# ── Spielerkennung ────────────────────────────────────────────────────────────


def _player_id() -> str:
    """Token aus dem Cookie, oder ein neues. Keine Anmeldung, keine Daten zur
    Person -- das Token erkennt ein Geraet wieder und sonst nichts."""
    if 'player' in g:
        return g.player
    raw = request.cookies.get(PLAYER_COOKIE)
    if STORE.valid_player(raw):
        g.player = raw
        g.player_is_new = False
    else:
        g.player = STORE.new_player_id()
        g.player_is_new = True
    return g.player


@app.after_request
def _set_player_cookie(resp):
    if g.get('player_is_new') and g.get('player'):
        resp.set_cookie(PLAYER_COOKIE, g.player, max_age=365 * 24 * 3600,
                        httponly=True, samesite='Lax')
    return resp


# ── Sicherheits-Kopfzeilen ────────────────────────────────────────────────────
#
# Die Seite laedt ausschliesslich eigene Dateien: kein fremdes CDN, keine
# eingebettete Schrift, kein Zaehlpixel. Die Richtlinie darf deshalb streng
# sein -- 'self' und sonst nichts.
#
# Zwei Inline-Bloecke gibt es trotzdem, beide aus gutem Grund: die
# Uebersetzungstabelle in index.html (als Datei waere sie ein zweiter
# Rundlauf fuer etwas, das ohnehin zur Seite gehoert) und das vollstaendige
# CSS in login.html (die Anmeldeseite darf keine Datei nachladen, die hinter
# derselben Anmeldung liegt). Beide bekommen eine Nonce je Antwort statt
# 'unsafe-inline' -- sonst waere jedes eingeschleuste <script> mit erlaubt,
# und die Richtlinie haette gegen genau den Fall nichts mehr zu sagen.
#
# `frame-ancestors 'none'` ist der Grund fuer den ganzen Block: ohne ihn
# laesst sich das Anmeldeformular in einen fremden Rahmen setzen, und der
# Dienst haengt auf einem offenen LAN-Port.

_STATIC_HEADERS = {
    # Aelteren Browsern, die frame-ancestors noch nicht kennen, dasselbe sagen.
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    # Nichts davon braucht das Spiel, und was nicht gebraucht wird, bleibt zu.
    'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
}


def _csp_nonce() -> str:
    """Eine Nonce je Antwort. Wiederverwendung ueber Antworten hinweg waere
    dasselbe wie keine."""
    if 'csp_nonce' not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce


@app.context_processor
def _inject_nonce():
    """`csp_nonce` steht damit in jedem Template, ohne dass jeder
    render_template()-Aufruf sie durchreichen muss."""
    return {'csp_nonce': _csp_nonce}


@app.after_request
def _security_headers(resp):
    for key, value in _STATIC_HEADERS.items():
        resp.headers.setdefault(key, value)
    # Nur bauen, wenn die Antwort ueberhaupt eine Nonce gezogen hat -- fuer
    # eine JSON-Antwort oder eine Datei aus static/ gibt es nichts inline,
    # und eine Nonce ohne Traeger ist nur Rauschen im Kopf.
    nonce = f" 'nonce-{g.csp_nonce}'" if 'csp_nonce' in g else ''
    resp.headers.setdefault('Content-Security-Policy', (
        "default-src 'self'; img-src 'self' data:; media-src 'self'; "
        f"style-src 'self'{nonce}; script-src 'self'{nonce}; "
        "connect-src 'self'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'"
    ))
    return resp


def _limited(bucket: str, limit: int, window_s: float) -> bool:
    """Ratenbegrenzung je Spieler UND je Absenderadresse."""
    pid = _player_id()
    addr = request.remote_addr or '-'
    return not (LIMITS.hit(f'{bucket}:p:{pid}', limit, window_s)
                and LIMITS.hit(f'{bucket}:a:{addr}', limit * 4, window_s))


# ── Spielstaende ──────────────────────────────────────────────────────────────


@app.route('/api/saves')
def saves_list():
    return jsonify({'saves': STORE.list_saves(_player_id())})


@app.route('/api/saves/<slot>', methods=['GET'])
def save_read(slot: str):
    blob = STORE.read_save(_player_id(), slot)
    if blob is None:
        return jsonify({'error': 'not_found'}), 404
    return jsonify(blob)


@app.route('/api/saves/<slot>', methods=['PUT'])
def save_write(slot: str):
    if _limited('save', 30, 60):
        return jsonify({'error': 'rate_limited'}), 429
    if not persist.SLOT_RE.match(slot):
        return jsonify({'error': 'bad_slot'}), 400
    blob = request.get_json(silent=True)
    if not isinstance(blob, dict):
        return jsonify({'error': 'bad_body'}), 400
    reactor = blob.get('reactor')
    if reactor is not None and not isinstance(reactor, str):
        return jsonify({'error': 'bad_reactor'}), 400
    err = STORE.write_save(_player_id(), slot, blob)
    if err:
        return jsonify({'error': err}), 413 if err == 'too_large' else 400
    return jsonify({'ok': True})


@app.route('/api/saves/<slot>', methods=['DELETE'])
def save_delete(slot: str):
    if not persist.SLOT_RE.match(slot):
        return jsonify({'error': 'bad_slot'}), 400
    return jsonify({'ok': STORE.delete_save(_player_id(), slot)})


# ── Einstellungen ───────────────────────────────────────────────────────────────
#
# Undurchsichtig wie ein Spielstand (siehe persist.py): der Server speichert
# und gibt zurueck, ohne die Struktur zu kennen. Sie gehoert der Oberflaeche,
# z.B. welche Werte je Reaktortyp in der Kopfzeile stehen.


@app.route('/api/prefs', methods=['GET'])
def prefs_read():
    return jsonify(STORE.read_prefs(_player_id()))


@app.route('/api/prefs', methods=['PUT'])
def prefs_write():
    if _limited('prefs', 30, 60):
        return jsonify({'error': 'rate_limited'}), 429
    blob = request.get_json(silent=True)
    if not isinstance(blob, dict):
        return jsonify({'error': 'bad_body'}), 400
    err = STORE.write_prefs(_player_id(), blob)
    if err:
        return jsonify({'error': err}), 413 if err == 'too_large' else 400
    return jsonify({'ok': True})


# ── Bestenliste ───────────────────────────────────────────────────────────────


@app.route('/api/highscores', methods=['GET'])
def scores_list():
    reactor = request.args.get('reactor')
    scenario = request.args.get('scenario')
    if reactor is not None and reactor not in REACTOR_P0:
        return jsonify({'error': 'bad_reactor'}), 400
    if scenario is not None and scenario not in SCENARIO_IDS:
        return jsonify({'error': 'bad_scenario'}), 400
    try:
        limit = int(request.args.get('limit', 20))
    except ValueError:
        limit = 20
    return jsonify({'scores': STORE.list_scores(reactor, scenario, limit)})


@app.route('/api/highscores', methods=['POST'])
def scores_add():
    """Der Client schickt Kennzahlen, NIE einen Punktestand.

    Gepruefte Reihenfolge: Ratenbegrenzung, Kennungen gegen die Whitelist,
    Plausibilitaet der Kennzahlen, dann erst rechnen. Ein mitgeschicktes
    Feld "score" wird nicht gelesen -- es kommt gar nicht vor.
    """
    # Zwei Stufen. Oben eine weite Grenze gegen das blosse Fluten; die enge
    # Grenze steht weiter unten, kurz vor dem Schreiben. Stuende sie hier,
    # wuerde eine einzige fehlerhafte Anfrage den naechsten gueltigen Eintrag
    # fuer eine Minute blockieren -- und wer haendisch herumprobiert, sperrt
    # sich damit selbst aus.
    if _limited('score_burst', 60, 60):
        return jsonify({'error': 'rate_limited'}), 429

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'error': 'bad_body'}), 400

    summary = body.get('summary')
    if not isinstance(summary, dict):
        return jsonify({'error': 'bad_summary'}), 400

    reactor = summary.get('reactor') or body.get('reactor')
    scenario = summary.get('scenario') or body.get('scenario')
    if reactor not in REACTOR_P0:
        return jsonify({'error': 'bad_reactor'}), 400
    if scenario not in SCENARIO_IDS:
        return jsonify({'error': 'bad_scenario'}), 400

    scn = SCENARIO_BY_ID[scenario]
    if scn.get('reactor') != reactor:
        return jsonify({'error': 'reactor_mismatch'}), 400

    why = scoring.validate_summary(summary, scn, REACTOR_P0[reactor])
    if why:
        return jsonify({'error': 'implausible', 'detail': why}), 400

    # Der Schwierigkeitsgrad kommt AUS DER SZENARIODATEI, nie aus der Anfrage.
    # Er geht als Faktor in den Abschlussbonus ein, und zwar ungedeckelt: mit
    # dem mitgeschickten Wert liess sich der Punktestand beliebig hoch
    # schrauben (difficulty=1e6, completed=true ergab 250 Mio Punkte, und
    # validate_summary sah nichts Unplausibles -- es prueft jede andere
    # Kennzahl, nur diese nicht). Ueberschreiben statt pruefen: so kann das
    # Feld gar nicht erst falsch sein.
    summary = dict(summary)
    summary['difficulty'] = scn.get('difficulty', 1)

    name = STORE.clean_name(body.get('name'))
    if not name:
        return jsonify({'error': 'bad_name'}), 400

    # Jetzt erst die enge Grenze: ein Eintrag je Minute, zweihundert am Tag.
    if _limited('score', 1, 60) or _limited('score_day', 200, 86400):
        return jsonify({'error': 'rate_limited'}), 429

    result = scoring.score(summary)
    entry = STORE.add_score(reactor, scenario, name, result['score'], summary)
    return jsonify({'ok': True, 'entry': entry, 'score': result['score'],
                    'parts': result['parts']})


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
