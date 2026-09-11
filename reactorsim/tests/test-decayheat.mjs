// Nachzerfallswärme gegen die ANS-5.1-Größenordnung.
//
// Die Stützwerte (10 s, 100 s, 1 h, 1 d nach Abschaltung aus langem Volllast-
// betrieb) sind die üblichen Referenzpunkte. Wer f_j oder λ_j ändert, muss
// hier bewusst vorbeikommen.

import test from 'node:test';
import assert from 'node:assert/strict';

import { equilibriumDecay, stepDecay, decaySum } from '../static/js/sim/decayheat.js';
import { DECAY_SUM, PROMPT_FRACTION } from '../static/js/sim/constants.js';

function after(seconds, dt = 1) {
  const D = equilibriumDecay(1);
  const steps = Math.round(seconds / dt);
  for (let i = 0; i < steps; i++) stepDecay(D, 0, dt);
  return decaySum(D);
}

test('im Gleichgewicht sind es 7 Prozent', () => {
  const D = equilibriumDecay(1);
  assert.ok(Math.abs(decaySum(D) - 0.07) < 1e-12);
  // Und die Gesamtleistung ist damit genau 100 %, nicht 107 %.
  assert.ok(Math.abs(PROMPT_FRACTION * 1 + DECAY_SUM - 1) < 1e-12);
});

test('Verlauf nach Abschaltung', () => {
  const cases = [
    [10, 0.042, 0.005],
    [100, 0.027, 0.004],
    [3600, 0.0089, 0.003],
    [86400, 0.0050, 0.003],
  ];
  for (const [t, expect, tol] of cases) {
    const got = after(t, t > 3600 ? 10 : 0.5);
    assert.ok(Math.abs(got - expect) < tol,
      `t = ${t} s: ${(got * 100).toFixed(3)} %, erwartet ${(expect * 100).toFixed(2)} %`);
  }
});

test('Zeitschritt ändert das Ergebnis nicht', () => {
  const a = after(3600, 0.05);
  const b = after(3600, 5);
  assert.ok(Math.abs(a / b - 1) < 1e-6, `${a} vs ${b}`);
});

test('folgt der Leistung mit Verzögerung', () => {
  const D = equilibriumDecay(0);
  // Aus dem Stillstand auf Volllast: die schnelle Gruppe ist nach Sekunden da,
  // die langsame braucht Tage.
  for (let i = 0; i < 60; i++) stepDecay(D, 1, 1);
  const short = decaySum(D);
  assert.ok(short > 0.03 && short < 0.055, `nach 60 s: ${short}`);
  for (let i = 0; i < 10 * 86400; i++) stepDecay(D, 1, 1);
  assert.ok(Math.abs(decaySum(D) - 0.07) < 0.002, `nach 10 d: ${decaySum(D)}`);
});
