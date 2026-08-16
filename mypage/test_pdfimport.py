#!/usr/bin/env python3
"""Tests fuer pdfimport.py.

Aufruf: python test_pdfimport.py
Keine externe Test-Lib noetig (laeuft im Add-on-Image).

Die HTML-Tests laufen immer. Liegt zusaetzlich ein echtes Generator-PDF unter
C:\\temp\\datenschutzerklaerung.pdf (nicht im Repo, enthaelt Adressdaten), wird
auch der PDF-Weg geprueft.
"""
import sys
from pathlib import Path

import pdfimport as pi

FAILS = []
REAL_PDF = Path(r'C:\temp\datenschutzerklaerung.pdf')


def check(cond, msg):
    if cond:
        print(f'  ok   {msg}')
    else:
        print(f'  FAIL {msg}')
        FAILS.append(msg)


def md(html):
    return pi.html_to_markdown(html)


# ── HTML nach Markdown ───────────────────────────────────────────────────────
print('\nhtml_to_markdown')

check(md('<h1>Titel</h1>') == '# Titel', 'h1 wird #')
check(md('<h2>A</h2><h3>B</h3><h4>C</h4>') == '## A\n\n### B\n\n#### C',
      'h2/h3/h4 werden ##/###/####')
check(md('<p>Ein Satz.</p><p>Noch einer.</p>') == 'Ein Satz.\n\nNoch einer.',
      'Absaetze durch Leerzeile getrennt')
check(md('<p>fett: <strong>ja</strong> hier</p>') == 'fett: **ja** hier', 'strong wird **')
check(md('<p><b>b</b> und <em>e</em> und <i>i</i></p>') == '**b** und *e* und *i*',
      'b/em/i werden uebersetzt')

check(md('<ul><li>eins</li><li>zwei</li></ul>') == '- eins\n\n- zwei', 'ul wird Strichliste')
check(md('<ol><li>eins</li><li>zwei</li></ol>') == '1. eins\n\n2. zwei', 'ol wird nummeriert')

check(md('<p>siehe <a href="https://x.de/">Seite</a>.</p>') == 'siehe [Seite](https://x.de/).',
      'Link mit Beschriftung')
check(md('<p>hier <a href="https://x.de/">https://x.de/</a></p>') == 'hier <https://x.de/>',
      'nackte Adresse wird nicht gedoppelt')
check('javascript' not in md('<p><a href="javascript:alert(1)">klick</a></p>'),
      'javascript: wird als Link verworfen')
check(md('<p><a href="javascript:alert(1)">klick</a></p>') == 'klick',
      'Text eines verworfenen Links bleibt erhalten')
check(md('<p><a href="mailto:a@b.de">a@b.de</a></p>') == '[a@b.de](mailto:a@b.de)',
      'mailto bleibt Link, ohne das Schema in der Beschriftung')

check(md('<p>a<br>b</p>') == 'a  \nb', 'br wird harter Umbruch')
check(md('<p>&uuml;ber &amp; &szlig;</p>') == 'über & ß', 'Entities werden aufgeloest')
check(md('<h1>Daten&shy;schutz</h1>') == '# Datenschutz', 'weicher Trenner faellt raus')
check(md('<p>a&nbsp;b</p>') == 'a b', 'geschuetztes Leerzeichen wird normal')
check(md('<script>böse()</script><p>gut</p>') == 'gut', 'script-Inhalt landet nicht im Text')
check(md('<p>Zeile\n  umgebrochen</p>') == 'Zeile umgebrochen',
      'Layout-Umbruch im Absatz wird zu Leerzeichen')
check(md('') == '' and md(None) == '', 'leere Eingabe ergibt leeren Text')
check(md('<p>a</p><hr><p>b</p>') == 'a\n\n---\n\nb', 'hr wird Trennlinie')
check('<' not in md('<div><span>x</span></div>').replace('', ''),
      'unbekannte Tags landen nicht im Ergebnis')

# ── Feldnamen ────────────────────────────────────────────────────────────────
print('\n_kind_from_field')

for name, erwartet in [('privacy_html_de', ('privacy', 'de')),
                       ('imprint_html_en', ('impressum', 'en')),
                       ('datenschutz-html', ('privacy', '')),
                       ('impressum_html_de', ('impressum', 'de')),
                       ('irgendwas', ('', ''))]:
    got = pi._kind_from_field(name)
    check(got == erwartet, f'{name} -> {erwartet}')

# ── PDF-Strings ──────────────────────────────────────────────────────────────
print('\n_pdf_text')

check(pi._pdf_text('<h1>x</h1>') == '<h1>x</h1>', 'str bleibt str')
check(pi._pdf_text('<h1>ä</h1>'.encode('utf-16')).endswith('<h1>ä</h1>'), 'UTF-16 mit BOM')
check(pi._pdf_text('äöü'.encode('utf-8')) == 'äöü', 'UTF-8 ohne BOM')
check(pi._pdf_text(None) == '', 'None ergibt leeren Text')

# ── Echtes PDF ───────────────────────────────────────────────────────────────
print('\nextract (echtes PDF)')

if not REAL_PDF.exists():
    print(f'  uebersprungen — {REAL_PDF} nicht vorhanden')
else:
    r = pi.extract(REAL_PDF.read_bytes())
    m = r['markdown']
    check(r['source'] == 'html', 'Formularfeld wird dem Seitenlayout vorgezogen')
    check(r['kind'] == 'privacy' and r['lang'] == 'de', 'Art und Sprache aus dem Feldnamen')
    check(r['pages'] > 1 and r['chars'] > 5000, 'Seitenzahl und Umfang gemeldet')
    check(not r['warnings'], 'keine Warnungen')
    check(m.startswith('# '), 'beginnt mit einer Ueberschrift')
    check('\n## ' in m and '\n### ' in m, 'mehrere Ueberschriftenebenen')
    check('- ' in m, 'Aufzaehlung erkannt')
    check('**' in m, 'Fettschrift erkannt')
    for bad in ('<p>', '<h2', '&uuml;', '&nbsp;', '\u00ad'):
        check(bad not in m, f'kein Rest von {bad!r} im Ergebnis')
    check('http' in m, 'Adressen sind erhalten')

    import io
    import pdfplumber
    with pdfplumber.open(io.BytesIO(REAL_PDF.read_bytes())) as pdf:
        lay = pi.layout_to_markdown(pdf)
    check(len(lay) > 5000, 'Seitenlayout-Weg liefert ebenfalls Text')
    check('##' in lay, 'Seitenlayout-Weg erkennt Ueberschriften')
    check('....' not in lay, 'Inhaltsverzeichnis mit Punktfuehrung faellt raus')
    check('14 / 14' not in lay and '1 / 14' not in lay, 'Seitenzahlen fallen raus')
    # Absaetze duerfen nicht zeilenweise zerfallen
    laufend = [b for b in lay.split('\n\n') if len(b) > 200]
    check(len(laufend) > 20, 'Zeilen werden zu Absaetzen zusammengefasst')

# ── Fehlerfaelle ─────────────────────────────────────────────────────────────
print('\nFehlerfaelle')

for data, name in [(b'', 'leere Datei'), (b'kein PDF', 'kein PDF'),
                   (b'%PDF-1.4\nkaputt', 'abgeschnittenes PDF')]:
    try:
        pi.extract(data)
        check(False, f'{name} muss einen Fehler werfen')
    except Exception as e:
        check(True, f'{name} -> {type(e).__name__}')

print()
if FAILS:
    print(f'{len(FAILS)} Test(s) fehlgeschlagen')
    sys.exit(1)
print('alle Tests bestanden')
