// Reaktivitäts-Registry: Stabkurve, Vorzeichen der Rückkopplungen, Aufschlüsselung.

import test from 'node:test';
import assert from 'node:assert/strict';

import { makeReactivity, rodWorthCurve } from '../static/js/sim/reactivity.js';

/** Minimaler Typ zum Prüfen der Registry -- kein echter Reaktor. */
const spec = {
  id: 'probe',
  feedbacks: ['rods', 'doppler', 'mtc', 'void', 'xenon', 'samarium', 'boron', 'graphite'],
  rodBanks: [{ worth: 1200 }, { worth: 3800 }],
  feedback: {
    doppler_pcm_per_K: -2.8, doppler_T_ref: 900,
    mtc_pcm_per_K: -60, mtc_pcm_per_K_per_ppm: 0.03, mtc_T_ref: 578,
    void_pcm_per_pct: -100, void_ref: 0,
    xenon_worth_pcm: 2800,
    samarium_worth_pcm: 600,
    boron_pcm_per_ppm: 8, boron_ref_ppm: 1000,
    graphite_pcm_per_K: 0.5, graphite_T_ref: 800,
  },
};

const base = () => ({
  rod: [0, 0], T_f: 900, T_mod: 578, alphaBar: 0,
  X: 0, Sm: 0, C_B: 1000, T_gr: 800, rho_ext: 0,
});

test('Stabkurve ist monoton und in der Mitte am steilsten', () => {
  assert.equal(rodWorthCurve(0), 0);
  assert.ok(Math.abs(rodWorthCurve(1) - 1) < 1e-12);
  let prev = -1;
  for (let h = 0; h <= 1.0001; h += 0.01) {
    const v = rodWorthCurve(h);
    assert.ok(v >= prev - 1e-12, `nicht monoton bei h = ${h}`);
    prev = v;
  }
  const d = (h) => rodWorthCurve(h + 1e-4) - rodWorthCurve(h - 1e-4);
  assert.ok(d(0.5) > d(0.1) && d(0.5) > d(0.9), 'differentielle Wirksamkeit nicht mittig');
});

test('im Bezugszustand ist die Summe null', () => {
  const r = makeReactivity(spec);
  assert.ok(Math.abs(r.compute(base(), spec)) < 1e-12);
});

test('jede Rückkopplung hat das richtige Vorzeichen', () => {
  const r = makeReactivity(spec);

  const hotter = { ...base(), T_f: 1100 };
  assert.ok(r.compute(hotter, spec) < 0, 'Doppler nicht negativ');

  const warmMod = { ...base(), T_mod: 590 };
  assert.ok(r.compute(warmMod, spec) < 0, 'Moderatorkoeffizient nicht negativ');

  const voided = { ...base(), alphaBar: 0.4 };
  assert.ok(r.compute(voided, spec) < 0, 'Dampfblasen nicht negativ');

  const poisoned = { ...base(), X: 1 };
  const rho = r.compute(poisoned, spec);
  assert.ok(Math.abs(rho + 0.028) < 1e-9, `Xenon-Wert ${rho}`);

  const borated = { ...base(), C_B: 1100 };
  assert.ok(r.compute(borated, spec) < 0, 'Bor nicht negativ');

  const rodsIn = { ...base(), rod: [1, 1] };
  assert.ok(Math.abs(r.compute(rodsIn, spec) + 0.05) < 1e-9, 'Stabwirksamkeit falsch');
});

test('hohe Borkonzentration frisst den Moderatorkoeffizienten auf', () => {
  const r = makeReactivity(spec);
  const at = (ppm) => {
    const s = { ...base(), C_B: ppm, T_mod: 588 };
    r.compute(s, spec);
    return r.breakdown.moderator;
  };
  // −60 + 0,03·ppm: bei 2000 ppm ist der Koeffizient null.
  assert.ok(at(1000) < 0);
  assert.ok(Math.abs(at(2000)) < 1e-9, `bei 2000 ppm: ${at(2000)}`);
});

test('Aufschlüsselung summiert sich auf die Gesamtreaktivität', () => {
  const r = makeReactivity(spec);
  const s = { ...base(), rod: [0.3, 0.1], T_f: 1050, T_mod: 585, X: 0.8, C_B: 900, rho_ext: 1e-4 };
  const total = r.compute(s, spec);
  const sum = Object.values(r.breakdown).reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(sum - total) < 1e-15, `${sum} vs ${total}`);
  assert.ok(Math.abs(r.breakdown.external - 1e-4) < 1e-15);
});

test('Hooks hängen eigene Beiträge an', () => {
  const hooks = { reactivity: () => [{ id: 'tip', fn: () => 5e-4 }] };
  const r = makeReactivity(spec, hooks);
  assert.ok(Math.abs(r.compute(base(), spec) - 5e-4) < 1e-15);
  assert.ok('tip' in r.breakdown);
});
