#!/usr/bin/env python3
"""Tests fuer visitexplorer.py.

Aufruf: python test_visitexplorer.py
Keine externe Test-Lib noetig (laeuft im Add-on-Image).
"""
import csv
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import visitexplorer as vx

FAILS = []


def check(cond, msg):
    if cond:
        print(f'  ok   {msg}')
    else:
        print(f'  FAIL {msg}')
        FAILS.append(msg)


def ts(day, hh, mm, ss=0):
    return datetime(2026, 8, day, hh, mm, ss).strftime('%Y-%m-%d %H:%M:%S')


UA_A = 'Mozilla/5.0 (Windows NT 10.0) Chrome/141.0'
UA_B = 'Mozilla/5.0 (X11; Linux) Firefox/144.0'
UA_BOT = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'

COLS = ('datum', 'ip', 'land', 'browser', 'system', 'pfad', 'referrer',
        'sprache', 'bot', 'neuer_besucher', 'user_agent')


def row(datum, ip, pfad, ua=UA_A, land='DE', browser='Chrome', system='Windows',
        ref='', lang='de-DE', bot='0', neu='0'):
    return dict(zip(COLS, (datum, ip, land, browser, system, pfad, ref, lang,
                           bot, neu, ua)))


def write_csv(path, rows, header=True, extra_lines=()):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter=';')
        if header:
            w.writeheader()
        for r in rows:
            w.writerow(r)
        for line in extra_lines:
            f.write(line + '\n')


def parse(rows, **kw):
    """Zeilen durch die echte Datei-Ebene schicken."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'visits-2026-08.csv'
        write_csv(p, rows, **kw)
        return vx.parse_month(p)


# ── Parsen ───────────────────────────────────────────────────────────────────
print('\nparse_month')

rows, meta = parse([row(ts(1, 10, 0), '203.0.113.9', '/')])
check(len(rows) == 1 and meta['rows'] == 1, 'eine Zeile gelesen')
check(rows[0][vx.PATH] == '/', 'Pfad an der richtigen Stelle')
check(rows[0][vx.IP] == '203.0.113.9', 'IP an der richtigen Stelle')
check(rows[0][vx.UA] == UA_A, 'User-Agent an der richtigen Stelle')
check(rows[0][vx.TS] == datetime(2026, 8, 1, 10, 0).timestamp(), 'Zeitstempel stimmt')
check(rows[0][vx.BOT] is False and rows[0][vx.NEW] is False, 'Flags sind bool')

rows, meta = parse([row(ts(1, 10, 0), '203.0.113.9', '/')], header=False)
check(len(rows) == 1, 'Datei ohne Kopfzeile wird als Daten gelesen')

rows, meta = parse([row(ts(1, 10, 0), '203.0.113.9', '/')],
                   extra_lines=['kaputt;zu;wenig;spalten',
                                '9999-99-99 99:99:99;1.2.3.4;DE;C;W;/;;de;0;0;UA'])
check(meta['skipped'] == 2 and len(rows) == 1, 'kaputte Zeilen werden gezaehlt, nicht geworfen')
check(meta['truncated'] is False, 'nicht abgeschnitten')

# ── Sitzungen ────────────────────────────────────────────────────────────────
print('\nbuild_sessions')

# 29 Minuten Pause -> eine Sitzung, 30:01 -> zwei
rows, _ = parse([row(ts(1, 10, 0), '1.2.3.4', '/'),
                 row(ts(1, 10, 29), '1.2.3.4', '/blog')])
check(len(vx.build_sessions(rows)) == 1, '29 Min Pause bleibt eine Sitzung')

rows, _ = parse([row(ts(1, 10, 0), '1.2.3.4', '/'),
                 row(ts(1, 10, 30), '1.2.3.4', '/blog')])
check(len(vx.build_sessions(rows)) == 1, 'exakt 30 Min bleibt eine Sitzung')

rows, _ = parse([row(ts(1, 10, 0), '1.2.3.4', '/'),
                 row(ts(1, 10, 30, 1), '1.2.3.4', '/blog')])
check(len(vx.build_sessions(rows)) == 2, '30:01 Min trennt die Sitzung')

# Gleiche IP, zwei Browser -> zwei Sitzungen (NAT)
rows, _ = parse([row(ts(1, 10, 0), '1.2.3.4', '/', ua=UA_A),
                 row(ts(1, 10, 1), '1.2.3.4', '/', ua=UA_B)])
check(len(vx.build_sessions(rows)) == 2, 'gleiche IP, andere Browserkennung = eigene Sitzung')

# Verweildauer
rows, _ = parse([row(ts(1, 10, 0), '1.2.3.4', '/'),
                 row(ts(1, 10, 0, 41), '1.2.3.4', '/blog'),
                 row(ts(1, 10, 5), '1.2.3.4', '/p/x')])
s = vx.build_sessions(rows)[0]
check([st['dwell'] for st in s['steps']] == [41, 259, None],
      'Verweildauern stimmen, letzter Schritt ist None')
check(s['duration'] == 300, 'Sitzungsdauer = letzter minus erster Aufruf')
check(s['entry'] == '/' and s['exit'] == '/p/x', 'Ein- und Ausstieg stimmen')
check(s['bounce'] is False and s['views'] == 3, 'kein Absprung bei drei Aufrufen')

# Absprung
rows, _ = parse([row(ts(1, 10, 0), '1.2.3.4', '/')])
s = vx.build_sessions(rows)[0]
check(s['bounce'] is True and s['duration'] == 0, 'ein Aufruf = Absprung, Dauer 0')
check(s['steps'][0]['dwell'] is None, 'einziger Schritt hat keine Verweildauer')

# Doppelauslösung
rows, _ = parse([row(ts(1, 10, 0), '1.2.3.4', '/'),
                 row(ts(1, 10, 0, 1), '1.2.3.4', '/'),
                 row(ts(1, 10, 0, 30), '1.2.3.4', '/')])
s = vx.build_sessions(rows)[0]
check(len(s['steps']) == 2, 'Doppelauslaesung unter 2 s wird zusammengefasst')
check(s['steps'][0]['repeat'] == 2, 'repeat zaehlt mit')
check(s['views'] == 3, 'views zaehlt trotzdem alle Aufrufe')

# Verweildauer-Klammerung
rows, _ = parse([row(ts(1, 10, 0), '1.2.3.4', '/'),
                 row(ts(1, 9, 59), '1.2.3.4', '/blog')])
s = vx.build_sessions(rows)[0]
check(s['steps'][0]['dwell'] == 0, 'negative Zeitdifferenz wird zu 0 geklammert')

# partial
rows, _ = parse([row(ts(1, 0, 5), '1.2.3.4', '/'),
                 row(ts(1, 12, 0), '5.6.7.8', '/')])
ss = {s['ip']: s for s in vx.build_sessions(rows)}
check(ss['1.2.3.4']['partial'] is True, 'Sitzung am Dateianfang ist als partial markiert')
check(ss['5.6.7.8']['partial'] is False, 'spaetere Sitzung ist nicht partial')

# Sortierung + Kennung
rows, _ = parse([row(ts(1, 10, 0), '1.1.1.1', '/'),
                 row(ts(2, 10, 0), '2.2.2.2', '/')])
ss = vx.build_sessions(rows)
check(ss[0]['ip'] == '2.2.2.2', 'neueste Sitzung zuerst')
check(len({s['id'] for s in ss}) == 2 and len(ss[0]['id']) == 8,
      'jede Sitzung hat eine eigene 8-stellige Kennung')

# ── Auswertungen ─────────────────────────────────────────────────────────────
print('\nAuswertungen')

rows, _ = parse([
    row(ts(1, 10, 0), '1.1.1.1', '/'),
    row(ts(1, 10, 1), '1.1.1.1', '/blog'),
    row(ts(1, 10, 2), '1.1.1.1', '/blog/a'),
    row(ts(2, 11, 0), '2.2.2.2', '/'),
    row(ts(2, 11, 1), '2.2.2.2', '/blog'),
    row(ts(2, 11, 2), '2.2.2.2', '/blog/a'),
    row(ts(3, 12, 0), '3.3.3.3', '/impressum'),
])
ss = vx.build_sessions(rows)
c = vx.summary(ss)
check(c['sessions'] == 3 and c['views'] == 7, 'Kennzahlen: Sitzungen und Aufrufe')
check(c['visitors'] == 3, 'Kennzahlen: eindeutige Besucher')
check(c['bounce_rate'] == 33, 'Kennzahlen: Absprungrate 1 von 3')
check(c['avg_views'] == 2.3, 'Kennzahlen: Aufrufe je Sitzung')

pa = vx.path_analytics(ss)
check(pa['entry'][0] == {'name': '/', 'count': 2}, 'haeufigste Einstiegsseite')
check(pa['exit'][0] == {'name': '/blog/a', 'count': 2}, 'haeufigste Ausstiegsseite')
seqs = {tuple(x['steps']): x['count'] for x in pa['sequences']}
check(seqs.get(('/', '/blog')) == 2, 'Zweierweg wird gezaehlt')
check(seqs.get(('/', '/blog', '/blog/a')) == 2, 'Dreierweg wird gezaehlt')

# Wiederholung faellt aus der Wege-Auswertung, nicht aus den Schritten
rows, _ = parse([row(ts(1, 10, 0), '1.1.1.1', '/'),
                 row(ts(1, 10, 1, 0), '1.1.1.1', '/'),
                 row(ts(1, 10, 2), '1.1.1.1', '/blog')])
s = vx.build_sessions(rows)[0]
check(len(s['steps']) == 3, 'Reload 60 s spaeter bleibt ein eigener Schritt')
check(vx._clean_path_seq(s) == ['/', '/blog'], 'Wege-Auswertung faltet die Wiederholung')

# Heatmap
rows, _ = parse([row(ts(3, 14, 0), '1.1.1.1', '/'),      # 3.8.2026 = Montag
                 row(ts(3, 14, 30), '1.1.1.1', '/blog'),
                 row(ts(9, 2, 0), '2.2.2.2', '/')])      # 9.8.2026 = Sonntag
h = vx.heatmap(rows)
check(h['cells'][0][14] == 2, 'Heatmap: Montag 14 Uhr')
check(h['cells'][6][2] == 1, 'Heatmap: Sonntag 2 Uhr')
check(h['max'] == 2, 'Heatmap: Hoechstwert')
check(len(h['cells']) == 7 and len(h['cells'][0]) == 24, 'Heatmap: 7x24')

# Tage
rows, _ = parse([row(ts(1, 10, 0), '1.1.1.1', '/'),
                 row(ts(2, 10, 0), '2.2.2.2', '/'),
                 row(ts(2, 11, 0), '3.3.3.3', '/')])
d = vx.daily(vx.build_sessions(rows))
check([x['date'] for x in d] == ['2026-08-02', '2026-08-01'], 'Tage absteigend')
check(d[0]['sessions'] == 2, 'Sitzungen je Tag')

# Wiederkehrer
rows, _ = parse([row(ts(1, 10, 0), '1.1.1.1', '/'),
                 row(ts(1, 10, 1), '1.1.1.1', '/blog'),
                 row(ts(3, 10, 0), '1.1.1.1', '/blog'),
                 row(ts(5, 10, 0), '1.1.1.1', '/blog'),
                 row(ts(1, 10, 0), '9.9.9.9', '/'),
                 row(ts(1, 11, 0), '9.9.9.9', '/')])
ss = vx.build_sessions(rows)
ret = vx.returning(ss)
check(len(ret) == 1 and ret[0]['ip'] == '1.1.1.1',
      'nur wer an mehreren Tagen da war, zaehlt als Wiederkehrer')
check(ret[0]['days'] == 3 and ret[0]['sessions'] == 3, 'Tage und Sitzungen gezaehlt')
check(ret[0]['top_path'] == '/blog', 'meistbesuchter Pfad')
newest = max((s for s in ss if s['ip'] == '1.1.1.1'), key=lambda s: s['end'])
check(ret[0]['sid'] == newest['id'], 'verlinkt die juengste Sitzung')

# Bots bleiben Zeilen wie andere auch — gefiltert wird in app.py
rows, _ = parse([row(ts(1, 10, 0), '66.249.66.1', '/', ua=UA_BOT, land='', bot='1')])
s = vx.build_sessions(rows)[0]
check(s['bot'] is True and s['country'] == '', 'Bot-Zeile: Flag gesetzt, Land leer')

# strip_steps / all_paths
rows, _ = parse([row(ts(1, 10, 0), '1.1.1.1', '/'),
                 row(ts(1, 10, 1), '1.1.1.1', '/blog')])
ss = vx.build_sessions(rows)
check('steps' not in vx.strip_steps(ss)[0], 'strip_steps entfernt die Schritte')
check('steps' in ss[0], 'strip_steps laesst das Original in Ruhe')
check(vx.all_paths(ss) == {'/', '/blog'}, 'all_paths sammelt alle Pfade')

# ── Zwischenspeicher ─────────────────────────────────────────────────────────
print('\ncache_get')

with tempfile.TemporaryDirectory() as d:
    vx.cache_clear()
    p = Path(d) / 'visits-2026-08.csv'
    write_csv(p, [row(ts(1, 10, 0), '1.1.1.1', '/')])
    r1, _ = vx.cache_get(p, '2026-08')
    r2, _ = vx.cache_get(p, '2026-08')
    check(r1 is r2, 'zweiter Abruf kommt aus dem Zwischenspeicher')

    write_csv(p, [row(ts(1, 10, 0), '1.1.1.1', '/'),
                  row(ts(1, 10, 1), '1.1.1.1', '/blog')])
    r3, _ = vx.cache_get(p, '2026-08')
    check(len(r3) == 2, 'geaenderte Datei wird neu gelesen')

    for m in ('2026-05', '2026-06', '2026-07'):
        q = Path(d) / f'visits-{m}.csv'
        write_csv(q, [row(ts(1, 10, 0), '1.1.1.1', '/')])
        vx.cache_get(q, m)
    check(len(vx._cache) <= vx._CACHE_MONTHS,
          f'Zwischenspeicher haelt hoechstens {vx._CACHE_MONTHS} Monate')
    vx.cache_clear()

# ── Abschneiden ──────────────────────────────────────────────────────────────
print('\nROWS_MAX')

_orig = vx.ROWS_MAX
vx.ROWS_MAX = 3
try:
    rows, meta = parse([row(ts(1, 10, i), '1.1.1.1', f'/{i}') for i in range(5)])
    check(len(rows) == 3 and meta['truncated'] is True, 'zu grosse Datei wird abgeschnitten')
    check(rows[-1][vx.PATH] == '/4', 'die neuesten Zeilen ueberleben')
finally:
    vx.ROWS_MAX = _orig

# ── Scanner-Erkennung ────────────────────────────────────────────────────────
print('\nis_scanner_session')


def ses(views=1, ref='', lang=''):
    return {'views': views, 'ref': ref, 'lang': lang}


check(vx.is_scanner_session(ses()), 'ein Aufruf ohne Referrer und Sprache ist Scanner')
check(not vx.is_scanner_session(ses(lang='de-DE,de;q=0.9')),
      'mit Sprachangabe bleibt die Sitzung stehen')
check(not vx.is_scanner_session(ses(ref='https://www.google.com/')),
      'mit Referrer bleibt die Sitzung stehen')
check(not vx.is_scanner_session(ses(views=2)),
      'zwei Aufrufe bleiben stehen')
check(vx.is_scanner_session(ses(ref='  ', lang='  ')),
      'nur Leerzeichen zaehlen als leer')
kept, dropped = vx.drop_scanners([ses(), ses(lang='de'), ses()])
check(len(kept) == 1 and dropped == 2, 'drop_scanners zaehlt die entfernten Sitzungen')


# ── Rechenzentrums-Netze ─────────────────────────────────────────────────────
print('\nis_datacenter_ip')

check(vx.is_datacenter_ip('43.156.41.180'), 'Tencent-Adresse gilt als Rechenzentrum')
check(vx.is_datacenter_ip('20.219.2.203'), 'Azure-Adresse gilt als Rechenzentrum')
check(not vx.is_datacenter_ip('188.70.38.79'), 'Mobilfunk-Adresse bleibt Besucher')
check(not vx.is_datacenter_ip(''), 'leere Adresse ist kein Rechenzentrum')
check(not vx.is_datacenter_ip('kein-ip'), 'Unfug ist kein Rechenzentrum')

vx.set_extra_bot_nets(['194.180.48.0/24', 'kaputt'])
try:
    check(vx.is_datacenter_ip('194.180.48.7'), 'Netz aus visit_bot_nets greift')
    check(vx.is_datacenter_ip('43.156.41.180'), 'eingebaute Netze bleiben erhalten')
    check(not vx.is_datacenter_ip('188.70.38.79'), 'kaputter Eintrag wird uebergangen')
finally:
    vx.set_extra_bot_nets([])
check(not vx.is_datacenter_ip('194.180.48.7'), 'Zusatznetze lassen sich zuruecknehmen')

print()
if FAILS:
    print(f'{len(FAILS)} Test(s) fehlgeschlagen')
    sys.exit(1)
print('alle Tests bestanden')
