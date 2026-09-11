// Punktkinetik: Inhour, Prompt Jump, prompt kritisch, dt-Konvergenz.
//
// Die Inhour-Prüfung ist die kanonische Validierung eines Kinetiklösers: die
// Gleichung wird im Test selbst numerisch gelöst, nicht als Zahl hinterlegt.
// Stimmt die gemessene asymptotische Periode damit überein, rechnet der Löser
// richtig -- alles Weitere baut darauf auf.

import test from 'node:test';
import assert from 'node:assert/strict';

import { makeKinetics, equilibriumPrecursors, stepKinetics, inhourPeriod }
  from '../static/js/sim/kinetics.js';

const PWR = () => makeKinetics(0.0065, 2e-5, 0);   // ohne Quelle: reine Kinetik
const BWR = () => makeKinetics(0.0056, 4e-5, 0);
const RBMK = () => makeKinetics(0.0048, 1e-3, 0);

function fresh(kin, n = 1) {
  return { n, c: equilibriumPrecursors(kin, n) };
}

function run(kin, s, rho, seconds, dt) {
  const steps = Math.round(seconds / dt);
  for (let i = 0; i < steps; i++) stepKinetics(s, kin, rho, dt);
  return s;
}

test('Vorläufer starten im Gleichgewicht und bleiben dort', () => {
  const kin = PWR();
  const s = fresh(kin);
  for (let i = 0; i < 6; i++) {
    assert.ok(Math.abs(s.c[i] - kin.beta_i[i] / (kin.lambda[i] * kin.Lambda)) < 1e-9);
  }
  run(kin, s, 0, 1000, 0.05);
  // Ohne Quelle und ohne Reaktivität darf sich über 1000 s nichts bewegen.
  assert.ok(Math.abs(s.n - 1) < 1e-6, `n = ${s.n}`);
});

test('unterkritisch stellt sich die Quellmultiplikation ein', () => {
  // Mit Quelle: n strebt gegen −S·Λ/ρ. Das ist die Anzeige im Quellbereich.
  const kin = makeKinetics(0.0065, 2e-5, 1e-6);
  const rho = -0.01;
  const expect = -kin.source * kin.Lambda / rho;
  const s = { n: expect, c: equilibriumPrecursors(kin, expect) };
  run(kin, s, rho, 5000, 0.05);
  assert.ok(Math.abs(s.n / expect - 1) < 0.02, `n = ${s.n}, erwartet ${expect}`);
});

test('Inhour: gemessene Periode trifft die Gleichung', () => {
  for (const [name, make] of [['DWR', PWR], ['SWR', BWR], ['RBMK', RBMK]]) {
    const kin = make();
    for (const pcm of [100, 300, 500]) {
      const rho = pcm * 1e-5;
      const T = inhourPeriod(kin, rho);
      assert.ok(T > 0 && Number.isFinite(T), `${name} ${pcm} pcm: T = ${T}`);

      const s = fresh(kin);
      const dt = 0.01;
      // Einschwingen lassen, dann über eine Periode messen.
      run(kin, s, rho, Math.min(25 * T, 400), dt);
      const n0 = s.n;
      const window = Math.min(2 * T, 60);
      run(kin, s, rho, window, dt);
      const measured = window / Math.log(s.n / n0);

      const err = Math.abs(measured / T - 1);
      assert.ok(err < 0.05,
        `${name} ${pcm} pcm: gemessen ${measured.toFixed(3)} s, Inhour ${T.toFixed(3)} s (${(err * 100).toFixed(1)} %)`);
    }
  }
});

test('Prompt Jump: n springt um beta/(beta-rho)', () => {
  const kin = PWR();
  const s = fresh(kin);
  const rho = 50e-5;
  const expect = kin.beta / (kin.beta - rho);   // 1,0833
  stepKinetics(s, kin, rho, 0.05);
  assert.ok(Math.abs(s.n / expect - 1) < 0.02,
    `nach einem Schritt n = ${s.n.toFixed(4)}, erwartet ${expect.toFixed(4)}`);
});

test('prompt kritisch bleibt endlich und konvergiert in dt', () => {
  for (const [name, make] of [['DWR', PWR], ['SWR', BWR], ['RBMK', RBMK]]) {
    const kin = make();
    const rho = 1.05 * kin.beta;
    const peaks = [];
    for (const dt of [0.05, 0.0125]) {
      const s = fresh(kin);
      let flagged = false;
      const steps = Math.round(1.0 / dt);
      for (let i = 0; i < steps; i++) {
        const r = stepKinetics(s, kin, rho, dt);
        if (r.promptCritical) flagged = true;
      }
      assert.ok(Number.isFinite(s.n), `${name}: n = ${s.n}`);
      assert.ok(s.n > 1, `${name}: keine Exkursion, n = ${s.n}`);
      assert.ok(flagged, `${name}: prompt kritisch nicht gemeldet`);
      peaks.push(s.n);
    }
    const dev = Math.abs(peaks[0] / peaks[1] - 1);
    assert.ok(dev < 0.05,
      `${name}: dt-Abhängigkeit ${(dev * 100).toFixed(1)} % (${peaks[0].toExponential(3)} vs ${peaks[1].toExponential(3)})`);
  }
});

test('negative Reaktivität schaltet ab, ohne negativ zu werden', () => {
  const kin = PWR();
  const s = fresh(kin);
  run(kin, s, -0.05, 300, 0.05);
  assert.ok(s.n > 0 && s.n < 0.05, `n = ${s.n}`);
  for (let i = 0; i < 6; i++) assert.ok(s.c[i] >= 0);
});

test('Untertakte greifen nur oberhalb prompt kritisch', () => {
  const kin = PWR();
  const s = fresh(kin);
  assert.equal(stepKinetics(s, kin, 0.003, 0.05).substeps, 1);
  assert.ok(stepKinetics(s, kin, 1.2 * kin.beta, 0.05).substeps > 1);
});
