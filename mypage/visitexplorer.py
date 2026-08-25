"""Besucher-Explorer — CSV-Archiv lesen und zu Sitzungen verdichten.

Reine Logik ohne Flask: Parsen der Monatsdateien aus `visits/`, Bauen der
Sitzungen und die vier Auswertungen. Die Routen liegen in app.py, damit dieses
Modul keine Abhängigkeit zurück auf die App braucht.

Der Gedanke hinter dem Aufbau: das Archiv kennt keine Sitzungs-Kennung — es
schreibt eine Zeile je Seitenaufruf. Eine „Sitzung" entsteht hier erst durch
Zusammenfassen: gleiche IP, gleiche Browserkennung, höchstens `SESSION_GAP_MIN`
Minuten Abstand. Das ist eine Schätzung, keine Wahrheit (hinter einem
Mobilfunk-Anschluss teilen sich viele Leute eine Adresse), aber es ist die
einzige, die sich aus den vorhandenen Spalten überhaupt bilden lässt.

Zeilen werden als Tupel gehalten, nicht als dict: eine Monatsdatei kann
sechsstellig viele Zeilen haben, und 200 000 dicts wären ein paar hundert MB.
"""
import csv
import functools
import hashlib
import ipaddress
import threading
from collections import Counter, deque
from datetime import datetime

# ── Konstanten ───────────────────────────────────────────────────────────────

# Ab welcher Pause zwischen zwei Aufrufen eine neue Sitzung beginnt.
# Bewusst fest verdrahtet: ein Wert, den niemand dreht, wäre als Add-on-Option
# vier Dateien Pflege wert (config.yaml, beide translations, DOCS.md).
SESSION_GAP_MIN = 30

# Obergrenze je Monatsdatei. Gelesen wird in eine deque(maxlen=…), es überleben
# also die *neuesten* Zeilen — bei einer angeschnittenen Datei ist der aktuelle
# Rand interessanter als der Monatsanfang.
ROWS_MAX = 200_000

# Zwei aufeinanderfolgende gleiche Pfade dichter als das hier gelten als
# Doppelauslösung (Reload-Ticks, Vorschau-Prefetch) und werden zusammengefasst.
REPEAT_WINDOW_S = 2

# Spalten der CSV (siehe VISIT_CSV_COLUMNS in app.py):
# datum;ip;land;browser;system;pfad;referrer;sprache;bot;neuer_besucher;user_agent
_C_DATUM, _C_IP, _C_LAND, _C_BROWSER, _C_SYSTEM = 0, 1, 2, 3, 4
_C_PFAD, _C_REF, _C_LANG, _C_BOT, _C_NEW, _C_UA = 5, 6, 7, 8, 9, 10
_CSV_COLS = 11

# Aufbau einer geparsten Zeile (Tupel-Indizes)
TS, IP, UA, PATH, REF, LANG, COUNTRY, BOT, NEW, BROWSER, SYSTEM = range(11)


# ── Rechenzentrums-Adressen ──────────────────────────────────────────────────

# Netze der großen Cloud-Anbieter. Ein Aufruf von hier kommt nicht von einem
# Menschen mit Browser, egal was in der Browserkennung steht: Scanner setzen
# reihenweise „Safari/iOS" oder „Edge/Windows" ein, damit die übliche
# Textsuche in der Kennung (_BOT_UA in app.py) sie durchlässt.
#
# Die Liste ist bewusst grob (große Blöcke statt exakter Anbieter-Präfixe) und
# nicht vollständig — sie soll die Masse der Scan-Netze treffen, nicht ein
# Register führen. Folge einer zu groben Angabe ist harmlos: der Aufruf wird im
# Explorer als Bot einsortiert und ist über den Bot-Schalter weiter sichtbar.
# Eigene Ergänzungen kommen über die Option `visit_bot_nets` dazu.
_DATACENTER_CIDRS = (
    # Amazon AWS
    '3.0.0.0/8', '13.32.0.0/12', '15.177.0.0/16', '18.32.0.0/11',
    '18.128.0.0/9', '34.192.0.0/10', '35.152.0.0/13', '44.192.0.0/10',
    '52.0.0.0/11', '52.32.0.0/11', '52.64.0.0/12', '52.84.0.0/14',
    '52.88.0.0/13', '52.192.0.0/10', '54.64.0.0/10', '54.144.0.0/12',
    '54.160.0.0/11', '54.192.0.0/10',
    # Microsoft Azure
    '13.64.0.0/11', '20.0.0.0/8', '40.64.0.0/10', '52.224.0.0/11',
    '104.40.0.0/13',
    # Google Cloud
    '34.64.0.0/10', '35.184.0.0/13', '35.192.0.0/12', '35.208.0.0/12',
    '35.224.0.0/12', '35.240.0.0/13',
    # Tencent Cloud — Herkunft der meisten „Safari · iOS"-Einzelaufrufe
    '43.128.0.0/10', '119.28.0.0/16', '129.226.0.0/16', '150.109.0.0/16',
    '170.106.0.0/16',
    # Alibaba Cloud
    '8.208.0.0/12', '47.74.0.0/15', '47.76.0.0/14', '47.235.0.0/16',
    '47.236.0.0/14', '47.240.0.0/14', '198.11.128.0/18',
    # Oracle Cloud
    '129.146.0.0/15', '132.145.0.0/16', '140.238.0.0/16', '141.147.0.0/16',
    '143.47.0.0/16', '150.230.0.0/16', '152.67.0.0/16', '158.101.0.0/16',
    '168.138.0.0/16', '193.122.0.0/16',
    # DigitalOcean
    '104.131.0.0/16', '138.68.0.0/16', '143.110.0.0/16', '157.245.0.0/16',
    '159.65.0.0/16', '164.90.0.0/16', '165.22.0.0/16', '167.71.0.0/16',
    '167.99.0.0/16', '174.138.0.0/16', '178.62.0.0/16', '188.166.0.0/16',
    # Hetzner
    '5.9.0.0/16', '78.46.0.0/15', '88.99.0.0/16', '94.130.0.0/16',
    '116.202.0.0/16', '128.140.0.0/17', '135.181.0.0/16', '138.201.0.0/16',
    '142.132.0.0/16', '144.76.0.0/16', '148.251.0.0/16', '157.90.0.0/16',
    '159.69.0.0/16', '162.55.0.0/16', '167.235.0.0/16', '168.119.0.0/16',
    '176.9.0.0/16', '178.63.0.0/16', '188.40.0.0/16', '195.201.0.0/16',
    '213.239.192.0/18',
    # OVH
    '51.68.0.0/14', '51.75.0.0/16', '51.83.0.0/16', '51.89.0.0/16',
    '51.91.0.0/16', '137.74.0.0/16', '141.94.0.0/16', '145.239.0.0/16',
    '146.59.0.0/16', '147.135.0.0/16', '149.202.0.0/16', '151.80.0.0/16',
    '158.69.0.0/16', '164.132.0.0/16', '167.114.0.0/16', '176.31.0.0/16',
    '178.32.0.0/15', '188.165.0.0/16', '192.99.0.0/16', '213.32.0.0/16',
    '217.182.0.0/16',
    # Linode / Akamai
    '45.33.0.0/16', '45.56.0.0/16', '45.79.0.0/16', '50.116.0.0/16',
    '139.162.0.0/16', '172.104.0.0/15', '176.58.96.0/19', '178.79.128.0/17',
    '198.58.96.0/19', '212.71.232.0/21',
    # Vultr
    '45.32.0.0/16', '45.63.0.0/16', '45.76.0.0/16', '45.77.0.0/16',
    '95.179.128.0/17', '104.156.224.0/19', '108.61.0.0/16', '136.244.64.0/18',
    '149.28.0.0/16', '155.138.128.0/17', '207.148.0.0/17', '216.128.128.0/17',
    # Scaleway / Online.net
    '51.15.0.0/16', '51.158.0.0/15', '62.210.0.0/16', '163.172.0.0/16',
    '195.154.0.0/16', '212.83.128.0/19',
)

_dc_nets = [ipaddress.ip_network(c) for c in _DATACENTER_CIDRS]


def set_extra_bot_nets(cidrs) -> None:
    """Zusätzliche Netze aus der Option `visit_bot_nets` übernehmen.

    Unbrauchbare Einträge werden still übergangen: eine vertippte Zeile in den
    Add-on-Optionen darf den Besucherzähler nicht anhalten.
    """
    global _dc_nets
    nets = [ipaddress.ip_network(c) for c in _DATACENTER_CIDRS]
    for raw in (cidrs or ()):
        try:
            nets.append(ipaddress.ip_network(str(raw).strip(), strict=False))
        except ValueError:
            continue
    _dc_nets = nets
    is_datacenter_ip.cache_clear()


@functools.lru_cache(maxsize=4096)
def is_datacenter_ip(value: str) -> bool:
    """Ob die Adresse in einem der bekannten Rechenzentrums-Netze liegt."""
    try:
        addr = ipaddress.ip_address((value or '').strip())
    except ValueError:
        return False
    return any(addr in net for net in _dc_nets)


# ── Datei lesen ──────────────────────────────────────────────────────────────

def _parse_ts(s: str) -> float:
    """`2026-08-15 21:23:19` → Unix-Zeit (lokale Zeitzone).

    Von Hand zerlegt statt per `strptime`: das Format ist von uns selbst
    geschrieben und damit fest, und der Handbetrieb ist etwa viermal schneller —
    bei 200 000 Zeilen ist das der Unterschied zwischen Sekunden und Minuten.
    """
    return datetime(int(s[0:4]), int(s[5:7]), int(s[8:10]),
                    int(s[11:13]), int(s[14:16]), int(s[17:19])).timestamp()


def parse_month(path) -> tuple:
    """Eine Monatsdatei einlesen → `(rows, meta)`.

    `rows` sind Tupel in Dateireihenfolge (also aufsteigend nach Zeit), `meta`
    hält `rows`, `skipped` und `truncated`. Kaputte Zeilen werden gezählt und
    übersprungen — eine halb geschriebene letzte Zeile darf die ganze Auswertung
    nicht kippen.
    """
    rows = deque(maxlen=ROWS_MAX)
    skipped = 0
    total = 0
    # Wiederkehrende Zeichenketten teilen sich ein Objekt: es gibt eine Handvoll
    # Browser und Systeme, aber Zehntausende Zeilen.
    pool = {}

    def _pooled(v):
        return pool.setdefault(v, v)

    with open(path, encoding='utf-8-sig', newline='') as f:
        for i, raw in enumerate(csv.reader(f, delimiter=';')):
            # Kopfzeile nur überspringen, wenn dort wirklich eine steht — von
            # Hand zusammengesetzte Dateien haben womöglich keine.
            if i == 0 and raw and raw[0] == 'datum':
                continue
            total += 1
            try:
                if len(raw) < _CSV_COLS:
                    raise ValueError('Spaltenzahl')
                rows.append((
                    _parse_ts(raw[_C_DATUM]),
                    raw[_C_IP],
                    raw[_C_UA],
                    raw[_C_PFAD],
                    raw[_C_REF],
                    _pooled(raw[_C_LANG]),
                    _pooled(raw[_C_LAND]),
                    raw[_C_BOT] == '1',
                    raw[_C_NEW] == '1',
                    _pooled(raw[_C_BROWSER]),
                    _pooled(raw[_C_SYSTEM]),
                ))
            except (ValueError, IndexError, OverflowError, OSError):
                skipped += 1
    return list(rows), {'rows': len(rows), 'skipped': skipped,
                        'truncated': total - skipped > len(rows)}


# ── Zwischenspeicher ─────────────────────────────────────────────────────────
#
# Übersicht und Sitzungsliste desselben Monats sind zwei Abrufe kurz
# hintereinander — ohne Zwischenspeicher würde dieselbe Datei zweimal geparst.
# Schlüssel ist (mtime, Größe): angehängte Zeilen ändern beides, und die Größe
# ist der billigere der beiden Hinweise.

_CACHE_MONTHS = 2
_cache = {}
_cache_lock = threading.Lock()
_cache_tick = 0


def cache_get(path, month: str) -> tuple:
    """Geparste Zeilen eines Monats, gepuffert über Änderungszeit und Größe."""
    global _cache_tick
    st = path.stat()
    key = (st.st_mtime_ns, st.st_size)
    with _cache_lock:
        hit = _cache.get(month)
        if hit and hit[0] == key:
            _cache_tick += 1
            _cache[month] = (key, hit[1], hit[2], _cache_tick)
            return hit[1], hit[2]
    rows, meta = parse_month(path)
    with _cache_lock:
        _cache_tick += 1
        _cache[month] = (key, rows, meta, _cache_tick)
        while len(_cache) > _CACHE_MONTHS:
            # Am längsten nicht mehr abgerufenen Monat verwerfen. Der eben
            # geschriebene hat den höchsten Zähler und kann nicht getroffen werden.
            del _cache[min(_cache, key=lambda m: _cache[m][3])]
    return rows, meta


def cache_clear() -> None:
    """Zwischenspeicher leeren (Tests, und wenn eine Datei gelöscht wurde)."""
    with _cache_lock:
        _cache.clear()


# ── Sitzungen ────────────────────────────────────────────────────────────────

def build_sessions(rows, gap_min: int = SESSION_GAP_MIN) -> list:
    """Zeilen zu Sitzungen zusammenfassen.

    Gruppiert wird über (IP, vollständige Browserkennung). Nur über die IP wäre
    hinter einem gemeinsamen Anschluss alles ein einziger Besucher; die
    Browserkennung ist die einzige weitere Unterscheidung, die die CSV hergibt.
    """
    gap = gap_min * 60
    open_sessions = {}   # (ip, ua) → Sitzung in Arbeit
    done = []
    first_ts = rows[0][TS] if rows else 0

    for r in rows:
        key = (r[IP], r[UA])
        cur = open_sessions.get(key)
        if cur is not None and r[TS] - cur['_last'] > gap:
            done.append(cur)
            cur = None
        if cur is None:
            cur = {
                'ip': r[IP], 'ua': r[UA], 'browser': r[BROWSER],
                'system': r[SYSTEM], 'country': r[COUNTRY], 'lang': r[LANG],
                'bot': r[BOT], 'new': r[NEW],
                'start': int(r[TS]), 'ref': r[REF],
                'steps': [], '_last': r[TS],
            }
            open_sessions[key] = cur
        # Doppelauslösungen desselben Pfades zusammenfassen
        if (cur['steps'] and cur['steps'][-1]['path'] == r[PATH]
                and r[TS] - cur['_last'] <= REPEAT_WINDOW_S):
            cur['steps'][-1]['repeat'] += 1
        else:
            cur['steps'].append({'ts': int(r[TS]), 'path': r[PATH],
                                 'dwell': None, 'repeat': 1})
        cur['new'] = cur['new'] or r[NEW]
        cur['_last'] = r[TS]

    done.extend(open_sessions.values())

    gap_start = first_ts + gap
    for s in done:
        _finish(s, gap, gap_start)
    done.sort(key=lambda s: s['start'], reverse=True)
    return done


def _finish(s: dict, gap: int, gap_start: float) -> None:
    """Verweildauern, Kennzahlen und Kennung einer fertigen Sitzung setzen."""
    steps = s['steps']
    for i in range(len(steps) - 1):
        delta = steps[i + 1]['ts'] - steps[i]['ts']
        # Klammern fängt Sommerzeitsprünge ab: an der Umstellung kann dieselbe
        # Wanduhrzeit doppelt vorkommen (negativ) oder eine Stunde fehlen.
        steps[i]['dwell'] = max(0, min(delta, gap))
    # Der letzte Schritt bleibt bei None — es gibt kein Signal dafür, wann der
    # Besucher die letzte Seite wieder verlassen hat.
    s['end'] = steps[-1]['ts']
    s['duration'] = s['end'] - s['start']
    s['views'] = sum(st['repeat'] for st in steps)
    s['bounce'] = len(steps) == 1
    s['entry'] = steps[0]['path']
    s['exit'] = steps[-1]['path']
    # Sitzungen ganz am Dateianfang haben ihren Beginn womöglich im Vormonat.
    s['partial'] = s['start'] < gap_start
    s['id'] = hashlib.sha1(
        f"{s['ip']}|{s['ua']}|{s['start']}".encode(), usedforsecurity=False
    ).hexdigest()[:8]
    del s['_last']


def is_scanner_session(s) -> bool:
    """Ob eine Sitzung jedes Merkmal eines echten Browsers vermissen lässt.

    Drei Dinge zusammen: **ein** Aufruf, **kein** Referrer und **keine**
    Sprachangabe. Jeder Browser schickt `Accept-Language` mit — es steht in den
    Einstellungen und lässt sich nicht abschalten. Wer ohne Sprache genau eine
    Seite abholt und nie wiederkommt, hat keine Seite angesehen, sondern eine
    Adresse abgeklopft.

    Die Herkunft spielt bewusst keine Rolle: Scanner mieten sich auch in
    Mobilfunknetzen ein, und dort hilft keine Liste von Rechenzentrums-Netzen
    weiter (siehe `is_datacenter_ip`).
    """
    return (s['views'] == 1
            and not (s['ref'] or '').strip()
            and not (s['lang'] or '').strip())


def drop_scanners(sessions) -> tuple:
    """Sitzungen ohne Browser-Merkmale aussortieren → `(sessions, entfernt)`."""
    kept = [s for s in sessions if not is_scanner_session(s)]
    return kept, len(sessions) - len(kept)


def strip_steps(sessions) -> list:
    """Sitzungen ohne Schrittliste — für die Übersichtstabelle."""
    return [{k: v for k, v in s.items() if k != 'steps'} for s in sessions]


# ── Auswertungen ─────────────────────────────────────────────────────────────

def summary(sessions) -> dict:
    """Die Kennzahlen über der Tabelle."""
    if not sessions:
        return {'sessions': 0, 'visitors': 0, 'views': 0, 'bounce_rate': 0,
                'avg_views': 0, 'avg_duration': 0}
    views = sum(s['views'] for s in sessions)
    bounces = sum(1 for s in sessions if s['bounce'])
    return {
        'sessions':     len(sessions),
        'visitors':     len({(s['ip'], s['ua']) for s in sessions}),
        'views':        views,
        'bounce_rate':  round(bounces / len(sessions) * 100),
        'avg_views':    round(views / len(sessions), 1),
        'avg_duration': round(sum(s['duration'] for s in sessions) / len(sessions)),
    }


def _clean_path_seq(session) -> list:
    """Pfadfolge einer Sitzung ohne direkte Wiederholungen.

    Für die Wege-Auswertung zählt Navigation, nicht das Neuladen: `A→A→B` ist
    derselbe Weg wie `A→B`. In der Zeitleiste bleiben die Wiederholungen
    dagegen stehen — dort sind sie echtes Verhalten.
    """
    out = []
    for st in session['steps']:
        if not out or out[-1] != st['path']:
            out.append(st['path'])
    return out


def path_analytics(sessions, limit: int = 20, seq_max: int = 4) -> dict:
    """Einstiegs-, Ausstiegsseiten und die häufigsten Wege."""
    entry = Counter(s['entry'] for s in sessions)
    exit_ = Counter(s['exit'] for s in sessions)
    seqs = Counter()
    for s in sessions:
        p = _clean_path_seq(s)
        # Alle Teilstrecken der Länge 2..seq_max zählen, damit auch ein langer
        # Weg seine kurzen Abschnitte in die Wertung einbringt.
        for n in range(2, seq_max + 1):
            for i in range(len(p) - n + 1):
                seqs[tuple(p[i:i + n])] += 1
    return {
        'entry': [{'name': p, 'count': c} for p, c in entry.most_common(limit)],
        'exit':  [{'name': p, 'count': c} for p, c in exit_.most_common(limit)],
        'sequences': [{'steps': list(k), 'count': c}
                      for k, c in seqs.most_common(limit) if c > 1],
    }


def heatmap(rows) -> dict:
    """7×24-Raster (Montag = 0) mit Aufrufen je Wochentag und Stunde."""
    cells = [[0] * 24 for _ in range(7)]
    for r in rows:
        d = datetime.fromtimestamp(r[TS])
        cells[d.weekday()][d.hour] += 1
    return {'cells': cells, 'max': max((max(row) for row in cells), default=0)}


def daily(sessions) -> list:
    """Sitzungen und Aufrufe je Kalendertag — füllt die Tagesauswahl."""
    per = {}
    for s in sessions:
        day = datetime.fromtimestamp(s['start']).strftime('%Y-%m-%d')
        d = per.setdefault(day, {'date': day, 'sessions': 0, 'views': 0})
        d['sessions'] += 1
        d['views'] += s['views']
    return sorted(per.values(), key=lambda d: d['date'], reverse=True)


def returning(sessions, limit: int = 50) -> list:
    """Besucher, die an mindestens zwei verschiedenen Tagen da waren."""
    per = {}
    for s in sessions:
        key = (s['ip'], s['ua'])
        e = per.get(key)
        if e is None:
            e = per[key] = {
                'ip': s['ip'], 'browser': s['browser'], 'system': s['system'],
                'country': s['country'], 'sessions': 0, 'views': 0,
                'first': s['start'], 'last': s['end'], 'sid': s['id'],
                '_days': set(), '_paths': Counter(),
            }
        e['sessions'] += 1
        e['views'] += s['views']
        e['first'] = min(e['first'], s['start'])
        if s['end'] > e['last']:
            e['last'] = s['end']
            e['sid'] = s['id']      # „Weg ansehen" zeigt den jüngsten Besuch
        e['_days'].add(datetime.fromtimestamp(s['start']).strftime('%Y-%m-%d'))
        for st in s['steps']:
            e['_paths'][st['path']] += st['repeat']

    out = []
    for e in per.values():
        if len(e['_days']) < 2:
            continue
        top = e['_paths'].most_common(1)
        e['days'] = len(e['_days'])
        e['top_path'] = top[0][0] if top else ''
        del e['_days'], e['_paths']
        out.append(e)
    out.sort(key=lambda e: (e['days'], e['views']), reverse=True)
    return out[:limit]


def all_paths(sessions) -> set:
    """Alle in den Sitzungen vorkommenden Pfade — für die Titel-Auflösung."""
    return {st['path'] for s in sessions for st in s['steps']}
