#!/usr/bin/env python3
"""Wertung -- serverseitig.

Dieselbe Formel wie in static/js/game/scoring.js. Das ist Absicht und kein
Versehen: der Server darf dem Browser den Punktestand nicht glauben, also muss
er ihn aus den gemeldeten Kennzahlen selbst ausrechnen. Wer die eine Seite
aendert, aendert die andere mit -- tests/fixtures/scoring.json haelt beide
zusammen, und zwar von beiden Seiten aus geprueft.

Die Kennzahlen selbst bleiben faelschbar, solange die Simulation im Browser
laeuft. Das verschiebt die Angriffsflaeche aber von "eine beliebige Zahl" auf
"ein Satz physikalisch begrenzter Groessen", und die lassen sich auf
Plausibilitaet pruefen (siehe validate_summary).
"""

from __future__ import annotations

import math

WEIGHTS = {
    'energy': 1000.0,
    'deviation': 2.0,
    'alarm_second': 0.05,
    'violation': {1: 0.2, 2: 1.0, 3: 4.0},
    'scram': 500.0,
    'fuel_damage': 5000.0,
    'difficulty_bonus': 250.0,
}


def _num(value, default=0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def score(summary: dict) -> dict:
    """@return {'score': int, 'parts': {...}}"""
    demanded = max(_num(summary.get('energy_mwh_demanded')), 1e-9)
    ratio = min(_num(summary.get('energy_mwh_delivered')) / demanded, 1.0)

    parts = {
        'energy': WEIGHTS['energy'] * ratio,
        'deviation': -WEIGHTS['deviation'] * _num(summary.get('deviation_mwh')),
        'alarms': -WEIGHTS['alarm_second'] * _num(summary.get('alarm_seconds_unacked')),
        'violations': 0.0,
        'scram': -WEIGHTS['scram'] * _num(summary.get('scram_count')),
        'fuel': -WEIGHTS['fuel_damage'] if summary.get('fuel_damage') else 0.0,
        'bonus': (WEIGHTS['difficulty_bonus'] * _num(summary.get('difficulty'), 1.0)
                  if summary.get('completed') else 0.0),
    }
    vs = summary.get('violation_seconds')
    if not isinstance(vs, dict):
        # Unsinn statt eines Objekts zaehlt als "keine Ueberschreitungen".
        # Abstuerzen darf die Wertung nicht -- sie laeuft auf einer Anfrage,
        # deren Inhalt der Server nicht bestimmt.
        vs = {}
    for sev in (1, 2, 3):
        seconds = _num(vs.get(sev, vs.get(str(sev))))
        parts['violations'] -= WEIGHTS['violation'][sev] * seconds

    return {'score': round(sum(parts.values())), 'parts': parts}


def validate_summary(summary, scenario: dict, reactor_p0_e: float) -> str | None:
    """Plausibilitaetspruefung. @return Fehlergrund oder None.

    Geprueft wird nicht, ob jemand gut gespielt hat, sondern ob die gemeldeten
    Zahlen ueberhaupt aus einem Lauf stammen koennen: mehr Energie als die
    Anlage in der Zeit liefern kann, eine laengere Schicht als das Szenario
    dauert, negative Abweichungen, Ueberschreitungszeiten laenger als der Lauf.
    """
    if not isinstance(summary, dict):
        return 'summary_not_object'

    duration = _num(summary.get('duration_s'), -1.0)
    if duration <= 0:
        return 'duration_invalid'
    max_duration = _num(scenario.get('duration_s'), 0.0) * 1.05 + 120
    if duration > max_duration:
        return 'duration_too_long'

    delivered = _num(summary.get('energy_mwh_delivered'), -1.0)
    demanded = _num(summary.get('energy_mwh_demanded'), -1.0)
    if delivered < 0 or demanded < 0:
        return 'energy_negative'
    # Auch mit voll aufgedrehter Anlage nicht mehr als Nennleistung mal Zeit.
    ceiling = reactor_p0_e * duration / 3600.0 * 1.05 + 1.0
    if delivered > ceiling or demanded > ceiling:
        return 'energy_impossible'

    if _num(summary.get('deviation_mwh'), -1.0) < 0:
        return 'deviation_negative'

    scrams = _num(summary.get('scram_count'), -1.0)
    if scrams < 0 or scrams > 100:
        return 'scram_count_invalid'

    vs = summary.get('violation_seconds') or {}
    if not isinstance(vs, dict):
        return 'violations_not_object'
    for sev in (1, 2, 3):
        seconds = _num(vs.get(sev, vs.get(str(sev))), -1.0)
        if seconds < 0 or seconds > duration + 1:
            return 'violation_seconds_invalid'

    alarms = _num(summary.get('alarm_seconds_unacked'), -1.0)
    # Mehrere Meldungen koennen gleichzeitig anstehen, also darf die Summe
    # laenger sein als der Lauf -- aber nicht beliebig viel laenger.
    if alarms < 0 or alarms > duration * 40 + 60:
        return 'alarm_seconds_invalid'

    return None
