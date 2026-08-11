"""TripPilot-Fragebogen aus JSON statt hartcodiert.

Die Fragen lagen bis v0.89.11 doppelt im Code: als `ADV_STEPS` in static/app.js
(Anzeige/Reihenfolge/Sichtbarkeit) und als `_ADVISOR_FIELDS`/`_ADVISOR_LABELS`
in ai_routes.py (Prompt-Aufbau). Jetzt ist eine JSON-Datei die einzige Quelle;
beide Seiten leiten daraus ab.

Ablage: `/config/trippilot/questions.json` (per `map: app_config:rw` im
Dateimanager/Samba editierbar, direkt neben `/config/backups`). Fehlt sie,
wird die mitgelieferte Version aus dem Image dorthin kopiert. Ist sie kaputt,
gilt weiter die Image-Version — der Fragebogen bricht nie weg, die Fehler
stehen im Log und in der API-Antwort.

Wichtig fürs Update: `questions.json` gehört dem Nutzer und wird nach dem
ersten Anlegen **nie** überschrieben. Der jeweils aktuelle Auslieferungsstand
landet bei jedem Start zusätzlich als `questions.default.json` daneben — daran
lässt sich nach einem Add-on-Update ablesen, welche Fragen neu hinzugekommen
sind, ohne eigene Änderungen zu verlieren.

Schema — siehe auch die beim ersten Start geschriebene README.md:

    {"version": 1,
     "daytrip_value": "Tagesausflug in der Nähe",
     "steps": [{"key": "region",              # Profil-Feldname, eindeutig
                "title": "Wohin ...?",        # Frage im Wizard
                "label": "Ziel-Region",       # Bezeichnung im KI-Prompt
                "type": "multi|single|text",
                "options": [...],             # multi/single
                "exclusive": [...],           # multi: schließt andere aus
                "placeholder": "...",         # text
                "required": true,             # blockiert "Weiter"
                "show_if": <Bedingung>}]}

Bedingungen sind deklarativ (kein Code in der JSON):

    {"key": K, "contains": "X"}          Antwort enthält X (Liste) bzw. == X
    {"key": K, "contains_any": [...]}    Antwort enthält einen der Werte
    {"key": K, "equals": "X"}            Antwort ist exakt X
    {"key": K, "in": [...]}              Antwort ist einer der Werte
    {"key": K, "answered": true|false}   Frage (nicht) beantwortet
    {"all": [...]} / {"any": [...]} / {"not": {...}}
"""
import json
import logging
import os
import shutil

log = logging.getLogger(__name__)

# Die Auslieferungsdatei liegt immer neben diesem Modul (im Image /app, unter
# pytest im Repo) — bewusst nicht über TUIWATCH_BASE, das nur für Templates/
# static gilt.
BUNDLED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'trippilot_questions.json')
QUESTIONS_DIR = os.environ.get('TUIWATCH_TRIPPILOT_DIR', '/config/trippilot')
QUESTIONS_PATH = QUESTIONS_DIR + '/questions.json'          # gehört dem Nutzer
DEFAULT_COPY_PATH = QUESTIONS_DIR + '/questions.default.json'  # Referenz, wird erneuert
README_PATH = QUESTIONS_DIR + '/README.md'                  # Doku, wird erneuert

TYPES = ('multi', 'single', 'text')
_LEAF_OPS = ('contains', 'contains_any', 'equals', 'in', 'answered')
_MAX_STEPS = 100
_MAX_OPTIONS = 200

_cache = {'mtime': None, 'path': None, 'data': None, 'errors': [], 'source': 'bundled'}


# ── Validierung ────────────────────────────────────────────────────────────────

def _check_condition(cond, path: str, keys: set, errors: list):
    if not isinstance(cond, dict):
        errors.append(f'{path}: Bedingung muss ein Objekt sein')
        return
    for combi in ('all', 'any'):
        if combi in cond:
            if not isinstance(cond[combi], list) or not cond[combi]:
                errors.append(f'{path}.{combi}: muss eine nicht-leere Liste sein')
                return
            for i, sub in enumerate(cond[combi]):
                _check_condition(sub, f'{path}.{combi}[{i}]', keys, errors)
            return
    if 'not' in cond:
        _check_condition(cond['not'], f'{path}.not', keys, errors)
        return
    key = cond.get('key')
    if not isinstance(key, str) or not key:
        errors.append(f'{path}: "key" fehlt (oder all/any/not verwenden)')
        return
    if keys and key not in keys:
        errors.append(f'{path}: verweist auf unbekannten Fragen-Key "{key}"')
    ops = [o for o in _LEAF_OPS if o in cond]
    if len(ops) != 1:
        errors.append(f'{path}: genau einer von {", ".join(_LEAF_OPS)} nötig, gefunden {len(ops)}')
        return
    op = ops[0]
    val = cond[op]
    if op in ('contains_any', 'in') and (not isinstance(val, list) or not val):
        errors.append(f'{path}.{op}: muss eine nicht-leere Liste sein')
    elif op in ('contains', 'equals') and not isinstance(val, str):
        errors.append(f'{path}.{op}: muss ein Text sein')
    elif op == 'answered' and not isinstance(val, bool):
        errors.append(f'{path}.answered: muss true oder false sein')


def validate(data) -> list:
    """Gibt eine Liste lesbarer Fehlermeldungen zurück (leer = Datei ist gültig)."""
    errors = []
    if not isinstance(data, dict):
        return ['Datei enthält kein JSON-Objekt']
    steps = data.get('steps')
    if not isinstance(steps, list) or not steps:
        return ['"steps" fehlt oder ist leer']
    if len(steps) > _MAX_STEPS:
        return [f'"steps": maximal {_MAX_STEPS} Fragen erlaubt, gefunden {len(steps)}']
    daytrip = data.get('daytrip_value')
    if daytrip is not None and not isinstance(daytrip, str):
        errors.append('"daytrip_value": muss ein Text sein')

    keys = set()
    for i, s in enumerate(steps):
        at = f'steps[{i}]'
        if not isinstance(s, dict):
            errors.append(f'{at}: muss ein Objekt sein')
            continue
        key = s.get('key')
        if not isinstance(key, str) or not key.strip():
            errors.append(f'{at}: "key" fehlt')
        elif key in keys:
            errors.append(f'{at}: doppelter Key "{key}"')
        else:
            keys.add(key)
        for field in ('title', 'label'):
            if not isinstance(s.get(field), str) or not s[field].strip():
                errors.append(f'{at} ({key}): "{field}" fehlt')
        typ = s.get('type')
        if typ not in TYPES:
            errors.append(f'{at} ({key}): "type" muss {"/".join(TYPES)} sein, ist "{typ}"')
            continue
        if typ == 'text':
            for field in ('options', 'exclusive'):
                if field in s:
                    errors.append(f'{at} ({key}): "{field}" ist bei type "text" nicht erlaubt')
        else:
            opts = s.get('options')
            if not isinstance(opts, list) or not opts:
                errors.append(f'{at} ({key}): "options" fehlt oder ist leer')
            elif len(opts) > _MAX_OPTIONS:
                errors.append(f'{at} ({key}): maximal {_MAX_OPTIONS} Optionen')
            elif not all(isinstance(o, str) and o.strip() for o in opts):
                errors.append(f'{at} ({key}): "options" darf nur nicht-leere Texte enthalten')
            elif len(set(opts)) != len(opts):
                errors.append(f'{at} ({key}): doppelte Option')
            excl = s.get('exclusive')
            if excl is not None:
                if not isinstance(excl, list):
                    errors.append(f'{at} ({key}): "exclusive" muss eine Liste sein')
                elif isinstance(opts, list):
                    for e in excl:
                        if e not in opts:
                            errors.append(f'{at} ({key}): exklusive Option "{e}" '
                                          'steht nicht in "options"')
                if typ == 'single' and excl:
                    errors.append(f'{at} ({key}): "exclusive" wirkt nur bei type "multi"')

    # Bedingungen erst prüfen, wenn alle Keys bekannt sind (Vorwärts-Referenzen).
    for i, s in enumerate(steps):
        if isinstance(s, dict) and 'show_if' in s:
            _check_condition(s['show_if'], f'steps[{i}].show_if', keys, errors)
    return errors


# ── Laden ──────────────────────────────────────────────────────────────────────

def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def ensure_user_copy() -> bool:
    """Richtet `/config/trippilot/` beim Start ein und gibt True zurück, wenn es
    danach eine Nutzer-Datei gibt.

    `questions.json` wird nur angelegt, wenn sie fehlt — ein Add-on-Update darf
    eigene Fragen nicht überschreiben. `questions.default.json` und `README.md`
    gehören dagegen dem Add-on und werden bei jedem Start auf den aktuellen
    Stand gebracht, damit sich neue Auslieferungsfragen nachvollziehen lassen."""
    created = False
    try:
        os.makedirs(QUESTIONS_DIR, exist_ok=True)
        if not os.path.exists(QUESTIONS_PATH):
            shutil.copyfile(BUNDLED_PATH, QUESTIONS_PATH)
            created = True
            log.info('TripPilot-Fragen nach %s kopiert — dort editierbar', QUESTIONS_PATH)
    except OSError as e:
        log.warning('TripPilot-Fragen konnten nicht nach %s kopiert werden: %s',
                    QUESTIONS_PATH, type(e).__name__)
        return False
    # Referenz + Doku immer erneuern (nicht nutzereigen, Diff-Grundlage nach Update)
    try:
        shutil.copyfile(BUNDLED_PATH, DEFAULT_COPY_PATH)
        with open(README_PATH, 'w', encoding='utf-8') as f:
            f.write(_README_TEXT)
    except OSError as e:
        log.warning('TripPilot-Referenzdateien nicht schreibbar: %s', type(e).__name__)
    return created or os.path.exists(QUESTIONS_PATH)


def load(force: bool = False) -> dict:
    """Aktueller Fragebogen. Ergebnis:
    `{'steps': [...], 'daytrip_value': str, 'source': 'user'|'bundled', 'errors': [...]}`.

    Reihenfolge: Nutzer-Datei, sonst Image-Version. Eine kaputte Nutzer-Datei
    ersetzt den Fragebogen nicht, sondern liefert nur `errors` mit — so bleibt
    der Wizard nach einem Tippfehler benutzbar. Ergebnis wird bis zur nächsten
    Änderung (mtime/Pfad) gecacht, damit jeder Aufruf nicht neu parst."""
    path, errors = QUESTIONS_PATH, []
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        path, mtime = BUNDLED_PATH, None
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0
    if not force and _cache['data'] is not None \
            and _cache['path'] == path and _cache['mtime'] == mtime:
        return _cache['data']

    data = None
    if path == QUESTIONS_PATH:
        try:
            candidate = _read(path)
            errors = validate(candidate)
            if errors:
                log.warning('%s ist fehlerhaft (%d Problem(e)) — mitgelieferte Fragen aktiv. '
                            'Erstes Problem: %s', path, len(errors), errors[0])
            else:
                data = candidate
        except (OSError, ValueError) as e:
            errors = [f'Datei nicht lesbar/kein gültiges JSON ({type(e).__name__})']
            log.warning('%s nicht lesbar (%s) — mitgelieferte Fragen aktiv', path, type(e).__name__)

    source = 'user'
    if data is None:
        source = 'bundled'
        try:
            data = _read(BUNDLED_PATH)
        except (OSError, ValueError) as e:  # darf nie passieren (Image-Datei)
            log.error('Mitgelieferte TripPilot-Fragen unlesbar: %s', type(e).__name__)
            data = {'steps': [], 'daytrip_value': ''}

    result = {'steps': data.get('steps') or [],
              'daytrip_value': data.get('daytrip_value') or '',
              'source': source, 'errors': errors}
    _cache.update({'mtime': mtime, 'path': path, 'data': result,
                   'errors': errors, 'source': source})
    return result


def steps() -> list:
    return load()['steps']


def daytrip_value() -> str:
    return load()['daytrip_value']


def fields() -> tuple:
    """Profil-Keys in Fragebogen-Reihenfolge — bestimmt auch die Reihenfolge der
    Zeilen im KI-Prompt."""
    return tuple(s['key'] for s in steps() if s.get('key'))


def list_fields() -> set:
    return {s['key'] for s in steps() if s.get('type') == 'multi' and s.get('key')}


def text_fields() -> set:
    return {s['key'] for s in steps() if s.get('type') == 'text' and s.get('key')}


def labels() -> dict:
    return {s['key']: (s.get('label') or s['key']) for s in steps() if s.get('key')}


_README_TEXT = """# TripPilot-Fragen

`questions.json` in diesem Ordner steuert den TripPilot-Fragebogen von TUIWatch
— Fragen, Reihenfolge, Antwortmöglichkeiten und welche Frage wann erscheint.
Änderungen greifen beim nächsten Öffnen des Fragebogens, ohne Add-on-Neustart.

Ist die Datei fehlerhaft, benutzt TUIWatch weiter die mitgelieferten Fragen und
zeigt den Fehler im Fragebogen sowie im Add-on-Log an. Die Datei löschen und das
Add-on neu starten stellt die Auslieferungsversion wieder her.

## Diese Dateien

| Datei | Gehört | Bei einem Add-on-Update |
|---|---|---|
| `questions.json` | dir | bleibt unangetastet |
| `questions.default.json` | dem Add-on | wird auf den neuen Auslieferungsstand gesetzt |
| `README.md` | dem Add-on | wird neu geschrieben |

Nach einem Update lohnt ein Vergleich der beiden JSON-Dateien: Was in
`questions.default.json` neu ist und dir gefällt, kannst du in `questions.json`
übernehmen. Eigene Änderungen gehen dabei nie verloren.

## Aufbau

```json
{
  "version": 1,
  "daytrip_value": "Tagesausflug in der Nähe",
  "steps": [ ... ]
}
```

`daytrip_value` ist der Antwortwert, der den Tagesausflug-Modus auslöst (anderer
KI-Prompt, keine Reise-DNA). Er muss als Option bei der Frage `region` vorkommen.

Jeder Eintrag in `steps`:

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `key` | ja | eindeutiger Feldname, geht so an die KI |
| `title` | ja | Frage, wie sie im Fragebogen steht |
| `label` | ja | Bezeichnung dieser Angabe im KI-Prompt |
| `type` | ja | `multi` (Mehrfachauswahl), `single` (eine Antwort), `text` (Freitext) |
| `options` | bei multi/single | Liste der Antwortmöglichkeiten |
| `exclusive` | nein | Optionen (nur `multi`), die alle anderen abwählen |
| `placeholder` | nein | grauer Hinweistext im Freitextfeld |
| `required` | nein | `true` = ohne Antwort geht es nicht weiter |
| `show_if` | nein | Bedingung, sonst wird die Frage immer gestellt |

## Bedingungen (`show_if`)

Einzelbedingung — `key` ist der `key` einer **anderen** Frage:

| Form | Trifft zu, wenn |
|---|---|
| `{"key": "interests", "contains": "🌴 Strand"}` | Antwort enthält den Wert |
| `{"key": "region", "contains_any": ["Weltweit", "Egal"]}` | Antwort enthält einen davon |
| `{"key": "accommodation", "equals": "Hotel"}` | Antwort ist genau dieser Wert |
| `{"key": "arrival_mode", "in": ["Auto", "Bus", "Bahn"]}` | Antwort ist einer davon |
| `{"key": "water_type", "answered": true}` | Frage wurde beantwortet |

Verknüpfen mit `all` (und), `any` (oder), `not` (nicht):

```json
"show_if": {"all": [
  {"not": {"key": "region", "contains": "Tagesausflug in der Nähe"}},
  {"key": "accommodation", "equals": "Hotel"}
]}
```

## Hinweise

* Die Datei muss **UTF-8** sein, sonst gehen Umlaute und Emojis kaputt.
* Antwortwerte gehen wörtlich an die KI — sprechende Werte („Direktflug“) wirken
  besser als Kürzel („df“).
* Der Fragebogen wertet einzelne Antwortwerte zusätzlich für die Reise-DNA aus
  (z. B. `🌴 Strand` bei `interests`, `Spa` bei `hotel_wishes`). Werden solche
  Werte umbenannt, bleiben die Fragen funktionsfähig, nur die DNA-Auswertung
  greift für diesen Wert nicht mehr.
* Vor größeren Umbauten eine Kopie der Datei anlegen.
"""
