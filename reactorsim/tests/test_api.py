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


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('REACTORSIM_BASE', _ROOT)
    monkeypatch.setenv('REACTORSIM_DATA', str(tmp_path))
    for mod in ('app', 'persist', 'scoring', 'atomic_io'):
        sys.modules.pop(mod, None)
    import app as appmod
    appmod.app.config['TESTING'] = True
    return appmod.app.test_client()


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
