#!/usr/bin/env python3
"""Schnittstelle: Pfadprüfung, Größengrenzen, Ratenbegrenzung, Wertung.

Ausgeführt mit: python3 -m pytest reactorsim/tests/test_api.py
"""

import json
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)


TEST_USER = 'tester'
TEST_PASSWORD = 'test-passwort-123'


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Angemeldeter Client.

    Seit 0.0.13 liegt alles ausser /health und /login hinter der Anmeldung.
    Diese Tests pruefen die Schnittstelle selbst, nicht den Zugang -- der hat
    seine eigene Datei (test_auth.py). Also hier einmal anmelden und fertig.
    """
    import re
    monkeypatch.setenv('REACTORSIM_BASE', _ROOT)
    monkeypatch.setenv('REACTORSIM_DATA', str(tmp_path))
    monkeypatch.setenv('REACTORSIM_USER', TEST_USER)
    monkeypatch.setenv('REACTORSIM_PASSWORD', TEST_PASSWORD)
    for mod in ('app', 'auth', 'persist', 'scoring', 'atomic_io'):
        sys.modules.pop(mod, None)
    import app as appmod
    appmod.app.config['TESTING'] = True
    c = appmod.app.test_client()
    html = c.get('/login').get_data(as_text=True)
    csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
    r = c.post('/login', data={'user': TEST_USER, 'password': TEST_PASSWORD,
                               'csrf': csrf, 'next': '/'})
    assert r.status_code == 302, 'Anmeldung im Test fehlgeschlagen'
    return c


def _summary(**over):
    base = {
        'reactor': 'pwr',
        'scenario': 'pwr_load_follow',
        'difficulty': 1,
        'energy_mwh_delivered': 5400.0,
        'energy_mwh_demanded': 5600.0,
        'deviation_mwh': 12.5,
        'alarm_seconds_unacked': 60,
        'violation_seconds': {'1': 30, '2': 0, '3': 0},
        'scram_count': 0,
        'fuel_damage': False,
        'duration_s': 14400.0,
        'completed': True,
    }
    base.update(over)
    return base


def test_health_and_meta(client):
    assert client.get('/health').get_json()['status'] == 'ok'
    meta = client.get('/api/meta').get_json()
    assert len(meta['scenarios']) >= 4
    assert all(s['reactor'] in ('pwr', 'bwr', 'rbmk') for s in meta['scenarios'])


@pytest.mark.parametrize('slot', ['UPPER', 'mit punkt.', 'a' * 33, 'mit leer zeichen'])
def test_bad_slot_names_rejected(client, slot):
    r = client.put(f'/api/saves/{slot}', json={'v': 1})
    assert r.status_code == 400, slot


def test_path_traversal_cannot_escape(client, tmp_path):
    # Flask loest den Pfad selbst auf; wichtig ist, dass nichts ausserhalb
    # von /data entsteht.
    for slot in ['../../etc/passwd', '..%2F..%2Fx', 'a/b']:
        client.put(f'/api/saves/{slot}', json={'v': 1})
    for root, _dirs, files in os.walk(tmp_path):
        for name in files:
            assert str(tmp_path) in os.path.abspath(os.path.join(root, name))
    assert not os.path.exists('/tmp/reactorsim-escaped')


def test_save_roundtrip_and_size_limit(client):
    assert client.put('/api/saves/slot1', json={'v': 1, 'reactor': 'pwr', 't_sim': 5.0}).status_code == 200
    got = client.get('/api/saves/slot1').get_json()
    assert got['t_sim'] == 5.0
    listed = client.get('/api/saves').get_json()['saves']
    assert listed[0]['slot'] == 'slot1'

    big = {'v': 1, 'reactor': 'pwr', 'pad': 'x' * 200_000}
    r = client.put('/api/saves/big', json=big)
    assert r.status_code in (413, 400)

    assert client.delete('/api/saves/slot1').get_json()['ok'] is True
    assert client.get('/api/saves/slot1').status_code == 404


def test_score_is_recomputed_not_trusted(client):
    r = client.post('/api/highscores',
                    json={'name': 'Operator', 'score': 999999, 'summary': _summary()})
    data = r.get_json()
    assert r.status_code == 200
    assert data['score'] != 999999
    # Genau der Wert, den auch der Browser rechnet.
    sys.path.insert(0, _ROOT)
    import scoring
    assert data['score'] == scoring.score(_summary())['score']


def test_difficulty_comes_from_the_scenario_not_the_request(client):
    """Der Schwierigkeitsgrad ist ein Faktor im Abschlussbonus, und zwar ohne
    Deckel. Kam er aus der Anfrage, liess sich der Punktestand beliebig hoch
    schrauben -- validate_summary prueft jede andere Kennzahl, diese nicht:
    difficulty=1e6 mit completed=true ergab 250 Mio Punkte und ging glatt
    durch. Jetzt gewinnt die Szenariodatei."""
    import scoring
    r = client.post('/api/highscores',
                    json={'name': 'Schummler',
                          'summary': _summary(difficulty=1_000_000)})
    assert r.status_code == 200
    # pwr_load_follow steht in der Datei auf difficulty 1 -- genau der Wert,
    # den die ehrliche Rechnung benutzt.
    assert r.get_json()['score'] == scoring.score(_summary(difficulty=1))['score']


def test_difficulty_is_filled_in_when_missing(client):
    """Ueberschreiben statt pruefen heisst auch: ein Lauf ohne das Feld
    bekommt trotzdem den richtigen Bonus, statt still auf 1 zurueckzufallen."""
    import scoring
    # pwr_turbine_trip steht in der Datei auf difficulty 2 und dauert eine
    # Stunde -- die Kennzahlen muessen dazu passen, sonst greift vorher die
    # Plausibilitaetspruefung.
    summary = _summary(scenario='pwr_turbine_trip', duration_s=3600.0,
                       energy_mwh_delivered=1350.0, energy_mwh_demanded=1400.0,
                       violation_seconds={'1': 30, '2': 0, '3': 0})
    summary.pop('difficulty')
    r = client.post('/api/highscores', json={'name': 'X', 'summary': summary})
    assert r.status_code == 200
    assert r.get_json()['score'] == scoring.score({**summary, 'difficulty': 2})['score']


def test_security_headers_are_set(client):
    """Der Dienst haengt auf einem offenen LAN-Port. Ohne frame-ancestors
    laesst sich das Anmeldeformular in einen fremden Rahmen setzen."""
    for path in ('/', '/login'):
        h = client.get(path).headers
        csp = h['Content-Security-Policy']
        assert "frame-ancestors 'none'" in csp, path
        assert "default-src 'self'" in csp, path
        assert "unsafe-inline" not in csp, path
        assert h['X-Content-Type-Options'] == 'nosniff', path
        assert h['X-Frame-Options'] == 'DENY', path


def test_inline_blocks_carry_a_fresh_nonce(client):
    """Die Uebersetzungstabelle (index.html) und das Anmelde-CSS (login.html)
    stehen inline. Ohne passende Nonce im Kopf wuerde die eigene Seite an der
    eigenen Richtlinie scheitern -- und eine ueber Antworten hinweg gleiche
    Nonce waere dasselbe wie keine."""
    import re
    seen = set()
    for path in ('/', '/login'):
        r = client.get(path)
        html = r.get_data(as_text=True)
        nonce = re.search(r'nonce="([^"]+)"', html).group(1)
        assert f"'nonce-{nonce}'" in r.headers['Content-Security-Policy'], path
        seen.add(nonce)
    assert len(seen) == 2, 'Nonce war zweimal dieselbe'


@pytest.mark.parametrize('over,why', [
    ({'energy_mwh_delivered': 999999}, 'energy_impossible'),
    ({'duration_s': 999999}, 'duration_too_long'),
    ({'deviation_mwh': -5}, 'deviation_negative'),
    ({'violation_seconds': {'1': 99999, '2': 0, '3': 0}}, 'violation_seconds_invalid'),
    ({'scram_count': -1}, 'scram_count_invalid'),
])
def test_implausible_summaries_rejected(client, over, why):
    r = client.post('/api/highscores', json={'name': 'X', 'summary': _summary(**over)})
    assert r.status_code == 400
    assert r.get_json()['detail'] == why


def test_unknown_ids_rejected(client):
    r = client.post('/api/highscores',
                    json={'name': 'X', 'summary': _summary(scenario='gibts_nicht')})
    assert r.get_json()['error'] == 'bad_scenario'
    r = client.post('/api/highscores', json={'name': 'X', 'summary': _summary(reactor='fusion')})
    assert r.get_json()['error'] == 'bad_reactor'
    # Szenario existiert, passt aber nicht zum Reaktortyp.
    r = client.post('/api/highscores',
                    json={'name': 'X', 'summary': _summary(scenario='bwr_msiv')})
    assert r.get_json()['error'] == 'reactor_mismatch'


def test_name_is_cleaned_and_required(client):
    r = client.post('/api/highscores', json={'name': '   ', 'summary': _summary()})
    assert r.get_json()['error'] == 'bad_name'

    import persist
    assert persist.Store.clean_name('Ope​rator\x07') == 'Operator'
    assert len(persist.Store.clean_name('x' * 100)) == 24


def test_rate_limit_on_highscores(client):
    first = client.post('/api/highscores', json={'name': 'A', 'summary': _summary()})
    assert first.status_code == 200
    second = client.post('/api/highscores', json={'name': 'B', 'summary': _summary()})
    assert second.status_code == 429


def test_scores_are_sorted_and_capped(client, tmp_path):
    import persist
    store = persist.Store(str(tmp_path))
    for i in range(60):
        store.add_score('pwr', 'pwr_load_follow', f'P{i}', i * 10, {'completed': True})
    scores = store.list_scores('pwr', 'pwr_load_follow', limit=50)
    assert len(scores) <= persist.MAX_SCORES_PER_LIST
    assert scores == sorted(scores, key=lambda e: e['score'], reverse=True)
    assert scores[0]['score'] == 590


def test_rate_limit_forgets_expired_keys(monkeypatch):
    """Aufgeraeumt wurden vorher nur Schluessel mit LEERER Liste. Ein
    Spieler-Token, das einmal getroffen und nie wieder gesehen wurde, behielt
    seinen Eintrag fuer immer -- bei einem Cookie je Geraet wuchs die Tabelle
    ueber die Laufzeit des Containers monoton mit."""
    import persist
    limits = persist.RateLimit()
    monkeypatch.setattr(limits, '_SWEEP_AT', 4)

    now = [1000.0]
    monkeypatch.setattr(persist.time, 'monotonic', lambda: now[0])

    for i in range(4):
        assert limits.hit(f'alt:{i}', 5, 60)
    assert len(limits._hits) == 4

    # Eine Stunde spaeter ist keiner der alten Schluessel mehr im Fenster.
    now[0] += 3600
    limits.hit('neu', 5, 60)
    assert set(limits._hits) == {'neu'}


def test_rate_limit_keeps_live_keys_across_a_sweep(monkeypatch):
    """Aufraeumen darf nur wegwerfen, was abgelaufen ist -- sonst hebt der
    Speicherschutz die Grenze auf, die er schuetzen soll."""
    import persist
    limits = persist.RateLimit()
    monkeypatch.setattr(limits, '_SWEEP_AT', 2)
    assert limits.hit('dauer', 2, 86400)
    for i in range(5):
        limits.hit(f'kurz:{i}', 5, 60)
    assert 'dauer' in limits._hits
    assert limits.hit('dauer', 2, 86400)      # zweiter von zwei
    assert not limits.hit('dauer', 2, 86400)  # Grenze steht noch


def test_save_slot_limit_without_parsing_every_slot(tmp_path, monkeypatch):
    """write_save() zaehlt nur noch, statt jeden Slot zu oeffnen und zu
    parsen. Verhalten an der Obergrenze muss dasselbe bleiben."""
    import persist
    store = persist.Store(str(tmp_path))
    pid = store.new_player_id()
    for i in range(persist.MAX_SLOTS):
        assert store.write_save(pid, f'slot{i}', {'v': 1}) is None
    assert store.count_saves(pid) == persist.MAX_SLOTS

    # Voll: ein NEUER Slot geht nicht mehr, ein vorhandener schon.
    assert store.write_save(pid, 'noch-einer', {'v': 1}) == 'too_many_slots'
    assert store.write_save(pid, 'slot0', {'v': 2}) is None

    # Die Einstellungen liegen im selben Ordner, zaehlen aber nicht als Slot.
    store.write_prefs(pid, {'a': 1})
    assert store.count_saves(pid) == persist.MAX_SLOTS
    assert len(store.list_saves(pid)) == persist.MAX_SLOTS


def test_atomic_write_survives_partial_failure(tmp_path):
    import atomic_io
    path = os.path.join(tmp_path, 'x.json')
    atomic_io.write_json(path, {'a': 1})
    with pytest.raises(TypeError):
        atomic_io.write_json(path, {'b': object()})
    # Die alte Datei steht noch vollstaendig da, und es liegt kein halber
    # Schreibvorgang daneben.
    with open(path, encoding='utf-8') as f:
        assert json.load(f) == {'a': 1}
    leftovers = [n for n in os.listdir(tmp_path) if n.startswith('.tmp-')]
    assert leftovers == []
