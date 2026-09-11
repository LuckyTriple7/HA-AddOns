// Xenon, Jod, Samarium.
//
// Die Jod-Grube wird gegen die analytische Lösung geprüft, nicht gegen eine
// erinnerte Zahl: nach einer Abschaltung aus dem Gleichgewicht gilt
//   X*(t) = A·e^(−λ_Xe·t) − B·e^(−λ_I·t)
// mit A = 1 + k/(λ_I−λ_Xe), B = k/(λ_I−λ_Xe) und k = (λ_Xe+σφ₁₀₀)·γ_I/(γ_I+γ_Xe).
// Trifft der Integrator das, stimmt auch alles Weitere.

import test from 'node:test';
import assert from 'node:assert/strict';

import { stepPoisons, equilibriumPoisons, forecastXenon } from '../static/js/sim/poisons.js';
import {
  LAMBDA_I135, LAMBDA_XE, GAMMA_I, GAMMA_XE, SIGMA_XE_PHI100,
} from '../static/js/sim/constants.js';

const H = 3600;

function analyticPit(t) {
  const k = (LAMBDA_XE + SIGMA_XE_PHI100) * GAMMA_I / (GAMMA_I + GAMMA_XE);
  const B = k / (LAMBDA_I135 - LAMBDA_XE);
  const A = 1 + B;
  return A * Math.exp(-LAMBDA_XE * t) - B * Math.exp(-LAMBDA_I135 * t);
}

function run(p, n, seconds, dt = 1) {
  const steps = Math.round(seconds / dt);
  for (let i = 0; i < steps; i++) stepPoisons(p, n, dt);
  return p;
}

test('Volllast-Gleichgewicht ist auf 1 normiert', () => {
  const p = equilibriumPoisons(1);
  assert.ok(Math.abs(p.I - 1) < 1e-12);
  assert.ok(Math.abs(p.X - 1) < 1e-12);
  run(p, 1, 48 * H, 10);
  assert.ok(Math.abs(p.X - 1) < 0.02, `X = ${p.X}`);
  assert.ok(Math.abs(p.I - 1) < 0.02, `I = ${p.I}`);
});

test('aus dem sauberen Kern baut sich Xenon auf 1 auf', () => {
  const p = { I: 0, X: 0, Pm: 0, Sm: 0 };
  run(p, 1, 48 * H, 10);
  assert.ok(Math.abs(p.X - 1) < 0.02, `X nach 48 h = ${p.X}`);
});

test('Jod-Grube: Höhe und Zeitpunkt treffen die analytische Lösung', () => {
  const p = equilibriumPoisons(1);
  let peak = 0;
  let tPeak = 0;
  const dt = 10;
  for (let t = dt; t <= 30 * H; t += dt) {
    stepPoisons(p, 0, dt);
    if (p.X > peak) { peak = p.X; tPeak = t; }
    const exact = analyticPit(t);
    assert.ok(Math.abs(p.X - exact) < 0.005 * Math.max(exact, 1),
      `t = ${(t / H).toFixed(1)} h: X = ${p.X.toFixed(4)}, exakt ${exact.toFixed(4)}`);
  }
  // Die Höhe folgt aus σφ₁₀₀/λ_Xe ≈ 3,8. Ändert jemand diesen Wert, muss er
  // hier bewusst vorbeikommen.
  assert.ok(peak > 1.85 && peak < 2.0, `Spitze ${peak.toFixed(3)}`);
  assert.ok(tPeak / H > 8.0 && tPeak / H < 9.0, `Spitze bei ${(tPeak / H).toFixed(2)} h`);
});

test('nach der Grube fällt Xenon wieder ab', () => {
  const p = equilibriumPoisons(1);
  run(p, 0, 40 * H, 10);
  assert.ok(p.X < 0.6, `X nach 40 h = ${p.X}`);
});

test('Lastfolge: Xenon steigt beim Absenken, fällt beim Hochfahren', () => {
  const p = equilibriumPoisons(1);
  run(p, 0.5, 4 * H, 5);
  const afterDown = p.X;
  assert.ok(afterDown > 1.0, `X nach Absenken = ${afterDown}`);
  run(p, 1.0, 4 * H, 5);
  assert.ok(p.X < afterDown, `X nach Hochfahren = ${p.X}, vorher ${afterDown}`);
});

test('Samarium wächst nach Abschaltung und bleibt liegen', () => {
  const p = equilibriumPoisons(1);
  const start = p.Sm;
  run(p, 0, 200 * H, 60);
  assert.ok(p.Sm > start, `Sm = ${p.Sm}, vorher ${start}`);
  const held = p.Sm;
  run(p, 0, 200 * H, 60);
  // Ohne Neutronenfluss verschwindet Samarium praktisch nicht mehr.
  assert.ok(Math.abs(p.Sm - held) < 0.05 * held, `Sm driftet: ${p.Sm} vs ${held}`);
});

test('Vorausschau trifft die schrittweise Rechnung', () => {
  const p = equilibriumPoisons(1);
  const fc = forecastXenon(p, 0, 12 * H, 600);
  const walk = equilibriumPoisons(1);
  run(walk, 0, 12 * H, 10);
  const last = fc[fc.length - 1];
  assert.equal(last.t, 12 * H);
  assert.ok(Math.abs(last.X - walk.X) < 0.01, `Vorausschau ${last.X}, Rechnung ${walk.X}`);
});
