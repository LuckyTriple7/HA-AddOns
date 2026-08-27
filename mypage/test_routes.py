#!/usr/bin/env python3
"""Rauchtest über alle Routen von MyPage.

Aufruf: python test_routes.py — keine externe Test-Bibliothek noetig.
Laeuft ausserdem bei jeder Aenderung am Code in der CI
(`.github/workflows/test-mypage.yml`); ins Add-on-Image wandert er nicht.

Warum es das gibt: `app.py` ist auf ueber 300 Routen gewachsen, geprueft wurde
davon bisher keine einzige. Ein vertippter Vorlagenwert oder ein umbenanntes
Feld faellt damit erst dem Betreiber der Website auf. Dieser Test ruft jede
Route mit GET auf und verlangt nur eines: **kein 500er**. Das ist wenig, faengt
aber genau die Klasse Fehler, die eine Seite unbenutzbar macht.

Was er ausdruecklich NICHT prueft: ob der Inhalt stimmt. Dafuer braucht es
Tests je Funktion; dieser hier ist das Netz darunter.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent.resolve()
TMP = Path(tempfile.mkdtemp(prefix='mypage-routes-'))

# Muss VOR dem Import von app gesetzt sein: das Modul legt beim Laden seine
# Verzeichnisse an und liest die Optionen.
os.environ['MYPAGE_BASE'] = str(HERE)
os.environ['MYPAGE_DATA'] = str(TMP)
os.environ['MYPAGE_OPTIONS'] = str(TMP)
(TMP / 'options.json').write_text(json.dumps({
    'username': 'pruefer', 'password': 'pruefwort', 'session_hours': 1,
}), encoding='utf-8')

sys.path.insert(0, str(HERE))
import app  # noqa: E402  (Reihenfolge ist Absicht, siehe oben)

FAILS: list[str] = []


def check(cond, msg):
    if cond:
        print(f'  ok   {msg}')
    else:
        print(f'  FEHL {msg}')
        FAILS.append(msg)


# ── Testdaten ────────────────────────────────────────────────────────────────
# Ohne Inhalte antworten die Detailrouten mit 404 und pruefen damit nichts.
# Die Kennungen sind fest, damit sie unten in die Platzhalter passen.

POST_ID = 'aaaaaaaaaaaa'
PROJECT_ID = 'bbbbbbbbbbbb'
FORM_ID = 'cccccccccccc'
LIB_ID = 'dddddddddddd'
PAGE_ID = 'eeeeeeeeeeee'
ALBUM_ID = 'ffffffffffff'
TRIP_ID = '111111111111'
DAY_ID = '222222222222'


def seed():
    site = json.loads(json.dumps(app.DEFAULT_SITE))
    site['profile']['name'] = 'Pruefstand'
    site['design']['public_url'] = 'https://beispiel.invalid'
    site['design']['travel_enabled'] = True
    site['design']['comments_enabled'] = True
    site['posts'] = [{
        'id': POST_ID, 'date': '2026-01-02', 'title_de': 'Testbeitrag',
        'title_en': 'Test post', 'text_de': 'Text mit **Fett**.', 'text_en': 'Text.',
        'tags': ['test'], 'published': True, 'members_only': False,
        'image': '', 'video': '', 'gallery': [], 'meta_de': '', 'meta_en': '',
    }]
    site['pages'] = [{
        'id': PAGE_ID, 'slug': 'testseite', 'visible': True, 'nav': True,
        'title_de': 'Testseite', 'title_en': 'Test page',
        'body_de': 'Inhalt', 'body_en': 'Content', 'meta_de': '', 'meta_en': '',
        'members_only': False,
    }]
    site['projects'] = [{
        'id': PROJECT_ID, 'title': 'Testprojekt', 'desc_de': 'Kurz', 'desc_en': 'Short',
        'long_de': 'Lang genug fuer eine Detailseite.', 'long_en': 'Long enough.',
        'published': True, 'tags': [], 'url': '', 'repo': '',
    }]
    site['forms'] = [{
        'id': FORM_ID, 'slug': 'testformular', 'title_de': 'Testformular',
        'title_en': 'Test form', 'visible': True, 'nav': False, 'notify': False,
        'fields': [{'id': 'f1', 'type': 'text', 'label_de': 'Name', 'label_en': 'Name',
                    'required': True}],
    }]
    site['albums'] = [{
        'id': ALBUM_ID, 'title_de': 'Testalbum', 'title_en': 'Test album',
        'images': [], 'visible': True,
    }]
    site['library']['entries'] = [{
        'id': LIB_ID, 'slug': 'testeintrag', 'visible': True,
        'title_de': 'Testeintrag', 'title_en': 'Test entry',
        'summary_de': 'Kurz', 'summary_en': 'Short',
        'body_de': 'Inhalt', 'body_en': 'Content', 'tags': ['test'],
        'updated': '2026-01-02', 'pdf_mode': '',
    }]
    app.save_site(site)

    travel = {'trips': [{
        'id': TRIP_ID, 'slug': 'testreise', 'name': 'Testreise',
        'destination': 'Nirgendwo', 'travel_start': '2026-01-01',
        'travel_end': '2026-01-03', 'days': [{
            'id': DAY_ID, 'slug': 'tag-1', 'day_number': 1, 'date': '2026-01-01',
            'published': True, 'location': 'Nirgendwo', 'photos': [],
            'article': {'de': {'title': 'Tag 1', 'teaser': 'Kurz', 'body': 'Text'},
                        'en': {'title': 'Day 1', 'teaser': 'Short', 'body': 'Text'}},
        }],
    }]}
    (TMP / 'travel.json').write_text(json.dumps(travel), encoding='utf-8')


# Platzhalter der Routen mit Werten fuellen, die es tatsaechlich gibt.
VALUES = {
    'pid': POST_ID, 'eid': LIB_ID, 'fid': FORM_ID, 'tid': TRIP_ID, 'did': DAY_ID,
    'cid': 'zzzzzzzzzzzz', 'uid': 'zzzzzzzzzzzz', 'mid': 'zzzzzzzzzzzz',
    'sid': 'zzzzzzzzzzzz', 'aid': ALBUM_ID, 'gid': 'zzzzzzzzzzzz',
    'slug': 'testseite', 'tslug': 'testreise', 'dslug': 'tag-1',
    'cat': 'test', 'tag': 'test', 'lang': 'de', 'name': 'nichts.webp',
    'filename': 'nichts.webp', 'token': 'x' * 32, 'key': 'test',
    'game': 'kniffel', 'kind': 'post', 'ident': POST_ID, 'code': 'de',
    'path': 'nichts.txt', 'q': 'test', 'ts': '1',
}

# Routen, die nach draussen telefonieren oder absichtlich lange laufen. Sie
# gehoeren nicht in einen Rauchtest: er soll in Sekunden durchlaufen und auch
# ohne Netz dasselbe Ergebnis liefern.
SKIP_SUBSTRINGS = (
    '/api/github',          # GitHub-API
    '/api/geoip',           # Datensatz herunterladen
    '/api/ai/',             # Gemini
    '/api/translate',       # Uebersetzungsdienst
    '/api/indexnow',        # Suchmaschinen anpingen
    '/api/backup',          # ZIP ueber den ganzen Datenbestand
    '/api/export',          # statischer Export
    '/api/travel/ha/',      # Home-Assistant-Supervisor
    '/api/library/entries/<eid>/pdf',
)
# `/health` steht hier bewusst NICHT: Als Teilzeichenkette haette es zugleich
# `/api/health` mit ausgeschlossen — und ausgerechnet die Zustandsanzeige waere
# dann ungeprueft geblieben, ohne dass es jemandem auffaellt.


def build_url(rule) -> str | None:
    """Konkrete Adresse aus einer Regel — None, wenn ein Platzhalter fehlt."""
    url = rule.rule
    for arg in rule.arguments:
        val = VALUES.get(arg)
        if val is None:
            return None
        url = url.replace(f'<{arg}>', val)
        for conv in ('string', 'int', 'path', 'float'):
            url = url.replace(f'<{conv}:{arg}>', val)
    return None if '<' in url else url


def routes_of(flask_app):
    """(geprueft, uebersprungen, ohne GET) — die zweite Zahl ist die ehrliche."""
    out, skipped, no_get = [], [], 0
    for rule in flask_app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        if 'GET' not in (rule.methods or set()):
            no_get += 1
            continue
        if any(s in rule.rule for s in SKIP_SUBSTRINGS):
            skipped.append(rule.rule + '  (spricht nach draussen)')
            continue
        url = build_url(rule)
        if url:
            out.append((rule.rule, url))
        else:
            missing = [a for a in rule.arguments if a not in VALUES]
            skipped.append(rule.rule + f'  (kein Wert fuer {", ".join(missing)})')
    return sorted(set(out)), sorted(set(skipped)), no_get


def run(label, client, urls):
    """Jede Adresse aufrufen. Durchgefallen ist nur, was 5xx liefert oder wirft."""
    print(f'\n{label}: {len(urls)} Routen')
    bad = []
    for rule, url in urls:
        try:
            resp = client.get(url)
            code = resp.status_code
        except Exception as e:      # noqa: BLE001 — genau das ist der Fund
            bad.append(f'{rule} -> Ausnahme: {type(e).__name__}: {e}')
            continue
        if code >= 500:
            bad.append(f'{rule} -> HTTP {code}')
    for b in bad:
        print(f'  FEHL {b}')
        FAILS.append(f'{label}: {b}')
    check(not bad, f'{label}: kein Serverfehler auf {len(urls)} Routen')
    return len(urls)


def main():
    seed()
    pub = app.public_app.test_client()
    adm = app.admin_app.test_client()

    # Anmeldung ueber den echten Weg — damit deckt der Test zugleich ab, dass
    # der Login ueberhaupt funktioniert.
    r = adm.post('/login', data={'username': 'pruefer', 'password': 'pruefwort'})
    check(r.status_code in (200, 302), 'Anmeldung am Admin moeglich')

    pub_urls, pub_skip, pub_nog = routes_of(app.public_app)
    adm_urls, adm_skip, adm_nog = routes_of(app.admin_app)
    n_pub = run('oeffentlich', pub, pub_urls)
    n_adm = run('Admin', adm, adm_urls)

    # Ein paar Adressen, die es nicht gibt: muessen 404 sein, nicht 500.
    for url in ('/gibtsnicht', '/blog/xxxxxxxxxxxx', '/seite/gibtsnicht',
                '/bibliothek/gibtsnicht', '/reiseblog/x/y'):
        check(pub.get(url).status_code == 404, f'unbekannte Adresse {url} -> 404')

    # Ohne Anmeldung darf keine Admin-API Daten herausgeben.
    anon = app.admin_app.test_client()
    for url in ('/api/site', '/api/health', '/api/stats/notfound', '/api/uploads/list'):
        code = anon.get(url).status_code
        check(code in (401, 302), f'ohne Anmeldung {url} -> {code}')

    # Die Abdeckung offen ausweisen. Ein Rauchtest, der verschweigt, was er
    # nicht anfasst, wiegt in falscher Sicherheit.
    skipped = pub_skip + adm_skip
    print(f'\nAbdeckung: {n_pub + n_adm} Routen mit GET geprueft, '
          f'{len(skipped)} uebersprungen, {pub_nog + adm_nog} ohne GET '
          f'(POST/PUT/DELETE — hier nicht getestet)')
    for line in skipped:
        print(f'  uebersprungen: {line}')
    print(f'\n{len(FAILS)} Fehler')
    return 1 if FAILS else 0


if __name__ == '__main__':
    try:
        rc = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print('\nalle Tests bestanden' if rc == 0 else f'\n{len(FAILS)} FEHLER')
    sys.exit(rc)
