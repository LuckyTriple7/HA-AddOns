#!/usr/bin/env python3
"""Die Wertung muss auf beiden Seiten dasselbe ergeben.

Die Fixture-Datei tests/fixtures/scoring.json wird von der JavaScript-Seite
(tests/test-game.mjs) gegen dieselben Erwartungswerte geprueft. Weicht eine
Seite ab, faellt es hier oder dort auf -- und nicht erst dann, wenn ein
Spieler sich ueber einen anderen Punktestand wundert.
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import scoring  # noqa: E402


def _fixtures():
    with open(os.path.join(_HERE, 'fixtures', 'scoring.json'), encoding='utf-8') as f:
        return json.load(f)


def test_fixtures_match():
    for f in _fixtures():
        got = scoring.score(f['summary'])['score']
        assert got == f['score'], f"{f['name']}: {got} statt {f['score']}"


def test_more_energy_than_demanded_gives_no_extra():
    base = _fixtures()[0]['summary']
    over = dict(base, energy_mwh_delivered=base['energy_mwh_demanded'] * 3)
    assert scoring.score(over)['score'] == scoring.score(base)['score']


def test_every_penalty_lowers_the_score():
    base = _fixtures()[0]['summary']
    ref = scoring.score(base)['score']
    for over in ({'deviation_mwh': 50}, {'alarm_seconds_unacked': 600},
                 {'scram_count': 1}, {'fuel_damage': True},
                 {'violation_seconds': {'1': 0, '2': 0, '3': 60}}):
        assert scoring.score(dict(base, **over))['score'] < ref, over


def test_nan_and_nonsense_do_not_crash():
    assert isinstance(scoring.score({})['score'], int)
    weird = {'energy_mwh_delivered': 'viel', 'energy_mwh_demanded': None,
             'deviation_mwh': float('nan'), 'violation_seconds': 'keine'}
    assert isinstance(scoring.score(weird)['score'], int)
