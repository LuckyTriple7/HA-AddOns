"""Der freiwillige Zusatz-Datensatz für die Technik-Erkennung.

NetToolbox bringt eigene Fingerabdrücke mit (techrules.py, MIT wie das Add-on
selbst). Weit umfangreicher ist der Gemeinschafts-Datensatz, der nach dem
Rückzug von Wappalyzer 2023 weitergepflegt wird -- der steht jedoch unter der
**GPL-3.0**. Ins Abbild kopiert wäre das Add-on damit ein kombiniertes Werk
und müsste selbst unter die GPL.

Deshalb wird er hier nicht mitgeliefert, sondern auf ausdrücklichen Wunsch
**zur Laufzeit** in den Datenordner der eigenen Instanz geladen -- dieselbe
Trennung wie bei Virensignaturen oder Filterlisten: verteilt wird nur das
Programm, die Daten holt sich der Betreiber selbst und bleibt ihr Empfänger.
Die Lizenz steht in der Oberfläche neben dem Schalter, und ohne Schalter wird
nichts geladen.

Heruntergeladen werden 27 JSON-Dateien (~3 MB). Gespeichert wird davon nur,
was sich ohne Browser überhaupt prüfen lässt -- Header, Cookies, Meta-Angaben,
eingebundene Dateien, Quelltext, Adresse. Die `js`- und `dom`-Muster des
Datensatzes brauchen eine echte Seitenausführung und werden verworfen; das
sind rund 30 % der Einträge und der Grund, warum aus 7600 Techniken etwa 5300
werden.

Zu jedem Muster wird beim Import sein längstes wörtliches Teilstück abgelegt.
Beim Prüfen wird erst danach gesucht (ein Textvergleich, kein Regex) und das
Muster nur bei einem Treffer wirklich ausgeführt. Das ist nicht nur schnell,
es ist auch die Absicherung: fremde Muster laufen so gut wie nie über fremde
Eingaben, und wenn, dann unter einem Zeitbudget.
"""

import json
import logging
import os
import re
import threading
import time

from netcore import Context, ProbeError, http_get

log = logging.getLogger(__name__)

SOURCE_REPO = 'https://github.com/enthec/webappanalyzer'
BASE_URL = 'https://raw.githubusercontent.com/enthec/webappanalyzer/main/src/'
LICENSE = 'GPL-3.0'
FILES = ('_',) + tuple('abcdefghijklmnopqrstuvwxyz')
MAX_FILE_BYTES = 2 * 1024 * 1024
STALE_AFTER = 7 * 24 * 3600     # eine Woche, danach gilt der Stand als alt

# Felder des fremden Schemas, die ohne Browser auswertbar sind, und wohin sie
# in unserer eigenen Regelform landen.
FIELD_MAP = (
    ('headers', 'header'),
    ('cookies', 'cookie'),
    ('meta', 'meta'),
    ('scriptSrc', 'script'),
    ('html', 'html'),
    ('text', 'html'),
    ('url', 'url'),
)

# Ihre Kategorienamen auf unsere Schubladen. Nach Stichwort statt nach der
# Nummer, weil Nummern im fremden Datensatz kommen und gehen.
CATEGORY_WORDS = (
    ('tag manager', 'tagmanager'),
    ('cookie compliance', 'consent'),
    ('cdn', 'cdn'),
    ('ecommerce', 'shop'), ('shop', 'shop'), ('cart', 'shop'),
    ('cms', 'cms'), ('blog', 'cms'), ('wiki', 'cms'), ('documentation', 'cms'),
    ('static site generator', 'framework'),
    ('javascript framework', 'framework'), ('web framework', 'framework'),
    ('javascript librar', 'js'), ('javascript graphic', 'js'),
    ('ui framework', 'css'), ('css', 'css'),
    ('font script', 'font'),
    ('web server', 'server'), ('reverse prox', 'server'),
    ('load balancer', 'server'), ('caching', 'server'),
    ('programming language', 'language'), ('database', 'language'),
    ('web server extension', 'server'),
    ('security', 'waf'), ('firewall', 'waf'),
    ('paas', 'hosting'), ('iaas', 'hosting'), ('hosting', 'hosting'),
    ('captcha', 'captcha'),
    ('analytics', 'analytics'),
    ('advertis', 'marketing'), ('retargeting', 'marketing'),
    ('affiliate', 'marketing'), ('marketing automation', 'marketing'),
    ('payment', 'payment'),
    ('live chat', 'support'), ('crm', 'support'), ('help desk', 'support'),
    ('customer', 'support'), ('support', 'support'),
    ('video player', 'media'), ('maps', 'media'), ('photo galler', 'media'),
    ('media', 'media'),
    ('search engine', 'search'), ('site search', 'search'),
    ('webmail', 'mail'), ('email', 'mail'),
    ('dns', 'dns'),
)

# Wappalyzer haengt Zusatzangaben mit \; an das Muster: confidence, version.
TAG_SPLIT = r'\;'
_LITERAL_RE = re.compile(r'[A-Za-z0-9_./-]{4,}')
_VERSION_GROUP_RE = re.compile(r'^\\(\d)$')
# Muster mit einem Quantifizierer direkt hinter einer quantifizierten Gruppe --
# das klassische (a+)+ -- werden gar nicht erst uebernommen.
_NESTED_QUANT_RE = re.compile(r'\([^()]*[+*][^()]*\)\s*[+*]')
MAX_PATTERN_LEN = 400

_lock = threading.Lock()
_path = ''
_cache = None
_cache_mtime = -1.0
_busy = False


def init(data_dir: str) -> None:
    global _path, _cache, _cache_mtime
    _path = os.path.join(data_dir, 'techrules_extra.json')
    _cache, _cache_mtime = None, -1.0


# ── Import ───────────────────────────────────────────────────────────────────

def _literal_of(pattern: str) -> str:
    """Das laengste woertliche Teilstueck, nach dem sich vorab suchen laesst.

    Ein Stueck, dessen letztes Zeichen von einem ? oder * gefolgt wird, ist
    optional -- es taugt nicht als Vorbedingung und wird deshalb gekuerzt.
    """
    best = ''
    for found in _LITERAL_RE.finditer(pattern):
        part = found.group(0)
        tail = pattern[found.end():found.end() + 1]
        if tail in ('?', '*', '{'):
            part = part[:-1]
        if len(part) > len(best):
            best = part
    return best.lower() if len(best) >= 4 else ''


def _parse_pattern(raw) -> dict:
    """Ein Eintrag des fremden Schemas -> unsere Form, oder {} wenn unbrauchbar."""
    parts = str(raw).split(TAG_SPLIT)
    pattern = parts[0]
    if not pattern or len(pattern) > MAX_PATTERN_LEN:
        return {}
    if _NESTED_QUANT_RE.search(pattern):
        return {}
    confidence, version = 100, ''
    for extra in parts[1:]:
        key, _sep, value = extra.partition(':')
        key = key.strip().lower()
        if key == 'confidence':
            try:
                confidence = max(0, min(100, int(value.strip())))
            except ValueError:
                pass
        elif key == 'version':
            hit = _VERSION_GROUP_RE.match(value.strip())
            version = hit.group(1) if hit else ''
    try:
        re.compile(pattern, re.I)
    except (re.error, RecursionError):
        return {}
    return {'p': pattern, 'l': _literal_of(pattern), 'v': version,
            'c': confidence}


def _category(cats, catalogue: dict) -> str:
    for cat in cats or []:
        name = str(catalogue.get(str(cat), '')).lower()
        for word, ours in CATEGORY_WORDS:
            if word in name:
                return ours
    return 'misc'


def _convert(techs: dict, catalogue: dict) -> list:
    """Fremdes Schema -> unsere Regeln. Alles Unbrauchbare faellt weg."""
    rules = []
    for name, entry in techs.items():
        if not isinstance(entry, dict):
            continue
        tests = []
        for source_key, kind in FIELD_MAP:
            value = entry.get(source_key)
            if value is None:
                continue
            if isinstance(value, dict):
                for field, raw in value.items():
                    for one in (raw if isinstance(raw, list) else [raw]):
                        parsed = _parse_pattern(one)
                        if parsed:
                            parsed['f'] = str(field).lower()[:80]
                            parsed['k'] = kind
                            tests.append(parsed)
            else:
                for one in (value if isinstance(value, list) else [value]):
                    parsed = _parse_pattern(one)
                    if parsed:
                        parsed['k'] = kind
                        tests.append(parsed)
        if not tests:
            continue
        rules.append({
            'name': str(name)[:80],
            'cat': _category(entry.get('cats'), catalogue),
            'site': str(entry.get('website') or '')[:120],
            'implies': _names(entry.get('implies')),
            'requires': _names(entry.get('requires')),
            'tests': tests,
        })
    return rules


def _names(value) -> list:
    r"""implies/requires koennen selbst Zusatzangaben tragen (Name\;confidence)."""
    out = []
    for item in (value if isinstance(value, list) else [value] if value else []):
        name = str(item).split(TAG_SPLIT)[0].strip()
        if name:
            out.append(name[:80])
    return out


def update(ctx: Context) -> dict:
    """Datensatz holen, umwandeln, schreiben. Gibt den neuen Stand zurueck."""
    global _busy
    with _lock:
        if _busy:
            raise ProbeError('update_running')
        _busy = True
    try:
        techs, catalogue = {}, {}
        raw_bytes = 0
        answer = http_get(ctx, BASE_URL + 'categories.json',
                          max_bytes=MAX_FILE_BYTES, accept='application/json')
        raw_bytes += answer['bytes']
        for key, value in (json.loads(answer['body']) or {}).items():
            if isinstance(value, dict):
                catalogue[str(key)] = str(value.get('name') or '')
        for letter in FILES:
            answer = http_get(ctx, BASE_URL + 'technologies/%s.json' % letter,
                              max_bytes=MAX_FILE_BYTES, accept='application/json')
            raw_bytes += answer['bytes']
            try:
                part = json.loads(answer['body'])
            except ValueError:
                raise ProbeError('bad_dataset', letter)
            if isinstance(part, dict):
                techs.update(part)
        if not techs:
            raise ProbeError('bad_dataset', 'empty')
        rules = _convert(techs, catalogue)
        payload = {
            'meta': {
                'source': SOURCE_REPO, 'license': LICENSE,
                'fetched': int(time.time()),
                'technologies_upstream': len(techs),
                'technologies': len(rules),
                'patterns': sum(len(r['tests']) for r in rules),
                'downloaded_bytes': raw_bytes,
            },
            'rules': rules,
        }
        _write(payload)
        return status()
    finally:
        with _lock:
            _busy = False


def _write(payload: dict) -> None:
    global _cache, _cache_mtime
    if not _path:
        raise ProbeError('not_initialised')
    folder = os.path.dirname(_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = _path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, _path)
    _cache, _cache_mtime = None, -1.0


def remove() -> bool:
    """Datensatz loeschen -- wer den Schalter wieder ausmacht, soll die
    fremden Daten auch loswerden koennen."""
    global _cache, _cache_mtime
    _cache, _cache_mtime = None, -1.0
    try:
        os.unlink(_path)
        return True
    except OSError:
        return False


# ── Lesen ────────────────────────────────────────────────────────────────────

def _load() -> dict:
    global _cache, _cache_mtime
    if not _path:
        return {}
    try:
        mtime = os.path.getmtime(_path)
    except OSError:
        _cache, _cache_mtime = {}, -1.0
        return {}
    if _cache is not None and mtime == _cache_mtime:
        return _cache
    try:
        with open(_path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        log.warning("Zusatz-Datensatz unlesbar: %s", type(e).__name__)
        data = {}
    if not isinstance(data, dict) or not isinstance(data.get('rules'), list):
        data = {}
    _cache, _cache_mtime = data, mtime
    return data


def rules() -> list:
    return _load().get('rules') or []


def status() -> dict:
    data = _load()
    meta = data.get('meta') or {}
    fetched = int(meta.get('fetched') or 0)
    age = int(time.time()) - fetched if fetched else 0
    try:
        size = os.path.getsize(_path)
    except OSError:
        size = 0
    return {
        'available': bool(data.get('rules')),
        'source': meta.get('source', SOURCE_REPO),
        'license': meta.get('license', LICENSE),
        'fetched': fetched,
        'age_days': age // 86400 if fetched else None,
        'stale': bool(fetched and age > STALE_AFTER),
        'technologies': int(meta.get('technologies') or 0),
        'technologies_upstream': int(meta.get('technologies_upstream') or 0),
        'patterns': int(meta.get('patterns') or 0),
        'downloaded_bytes': int(meta.get('downloaded_bytes') or 0),
        'stored_bytes': size,
        'updating': _busy,
    }


def needs_update() -> bool:
    info = status()
    return not info['available'] or info['stale']
