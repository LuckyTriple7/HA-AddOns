// Druckwasserreaktor im Beharrungszustand.
//
// Der wichtigste Test des ganzen Projekts: läuft die Anlage nicht von selbst
// ruhig, ist jede Aussage über eine Störung wertlos. Er hat in der Entwicklung
// drei echte Fehler gefunden -- das Wärmegefälle im Dampferzeuger, das
// Temperaturprogramm der Stabregelung und die 2,6 % Spaltenergie, die nicht im
// Brennstoff landen und vorher aus der Bilanz verschwanden.

import test from 'node:test';
import assert from 'node:assert/strict';

import { createEngine } from '../static/js/sim/engine.js';
import * as pwr from '../static/js/plants/pwr.js';

const DT = 0.05;

function boot(opts = {}) {
  const e = createEngine(pwr, { n: 1.0, ...opts });
  return e;
}
function run(e, seconds, dt = DT) {
  const steps = Math.round(seconds / dt);
  for (let i = 0; i < steps; i++) e.step(dt);
}

test('Startzustand ist kritisch und passt zur Wärmebilanz', () => {
  const e = boot();
  const s = e.state;
  const d = e.derive();
  assert.ok(Math.abs(d.rho_pcm) < 1, `rho = ${d.rho_pcm} pcm`);
  // Kritische Borkonzentration ist ein Ergebnis, kein Sollwert -- sie muss im
  // betrieblich üblichen Bereich landen.
  assert.ok(s.C_B > 900 && s.C_B < 1500, `C_B = ${s.C_B} ppm`);
  assert.ok(Math.abs(s.T_co - e.spec.coolant.T_out) < 1.5, `T_heiss = ${s.T_co}`);
  assert.ok(Math.abs(s.T_ci - e.spec.coolant.T_in) < 1.5, `T_kalt = ${s.T_ci}`);
});

test('eine Stunde ohne Eingriff: Drift unter 0,5 Prozent', () => {
  const e = boot();
  const s = e.state;
  run(e, 600);
  const ref = {
    n: s.n, P_e: s.P_e, p_sg: s.p_sg, pzr_p: s.pzr_p,
    T_avg: 0.5 * (s.T_ci + s.T_co), L_sg: s.L_sg,
  };
  run(e, 3000);
  assert.ok(Math.abs(s.n / ref.n - 1) < 0.005, `n driftet: ${s.n} vs ${ref.n}`);
  assert.ok(Math.abs(s.P_e / ref.P_e - 1) < 0.005, `P_e driftet: ${s.P_e} vs ${ref.P_e}`);
  assert.ok(Math.abs(s.p_sg - ref.p_sg) < 0.5, `p_sg driftet: ${s.p_sg} vs ${ref.p_sg}`);
  assert.ok(Math.abs(s.pzr_p - ref.pzr_p) < 0.5, `Druckhalter driftet: ${s.pzr_p}`);
  assert.ok(Math.abs(s.L_sg - ref.L_sg) < 0.03, `Fuellstand driftet: ${s.L_sg}`);
  assert.ok(Math.abs(e.derive().rho_pcm) < 20, `rho = ${e.derive().rho_pcm} pcm`);
  assert.ok(!s.scram.active, `ungewollte Abschaltung: ${s.scram.cause}`);
  assert.equal(s.fault, null);
});

test('Energiebilanz schliesst sich auf ein Prozent', () => {
  const e = boot();
  const s = e.state;
  const sp = e.spec;
  run(e, 1200);

  // Kern: was der Durchsatz abfuehrt, muss die thermische Leistung sein.
  const removed = (s.W_core * sp.coolant.cp * (s.T_co - s.T_ci)) / 1000;
  assert.ok(Math.abs(removed / s.P_th - 1) < 0.01,
    `Kern: ${removed.toFixed(1)} MW abgefuehrt, ${s.P_th.toFixed(1)} MW erzeugt`);

  // Nennleistung: 3850 MWth, 1400 MWe.
  assert.ok(Math.abs(s.P_th / sp.P0_th - 1) < 0.01, `P_th = ${s.P_th}`);
  assert.ok(Math.abs(s.P_e / sp.P0_e - 1) < 0.01, `P_e = ${s.P_e}`);

  // Wirkungsgrad muss zum Kreisprozess passen, nicht bloss zufaellig stimmen.
  const eta = s.P_e / s.P_th;
  assert.ok(eta > 0.35 && eta < 0.375, `Wirkungsgrad ${(eta * 100).toFixed(2)} %`);
});

test('Unterkuehlungsspanne und DNBR liegen im Auslegungsbereich', () => {
  const e = boot();
  run(e, 600);
  const d = e.derive();
  assert.ok(d.subcooling > 15 && d.subcooling < 25, `Unterkuehlung ${d.subcooling.toFixed(1)} K`);
  assert.ok(d.dnbr > 2.0 && d.dnbr < 2.6, `DNBR ${d.dnbr.toFixed(2)}`);
});

test('Reaktivitaetsaufschluesselung summiert sich und ist plausibel', () => {
  const e = boot();
  run(e, 600);
  const d = e.derive();
  const sum = Object.values(d.breakdown).reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(sum - d.rho) < 1e-12);
  const pcm = (k) => d.breakdown[k] * 1e5;
  assert.ok(pcm('xenon') < -2500, `Xenon ${pcm('xenon').toFixed(0)} pcm`);
  assert.ok(pcm('boron') < -8000, `Bor ${pcm('boron').toFixed(0)} pcm`);
  assert.ok(pcm('excess') > 12000, `Ueberschuss ${pcm('excess').toFixed(0)} pcm`);
});

test('Teillast stellt sich stabil ein', () => {
  const e = boot();
  const s = e.state;
  run(e, 300);
  const target = 0.6 * e.spec.P0_e;
  const start = s.P_demand;
  for (let i = 0, n = Math.round(1800 / DT); i < n; i++) {
    s.P_demand = start + (target - start) * (i / n);
    e.step(DT);
  }
  run(e, 1800);
  assert.ok(Math.abs(s.P_e / target - 1) < 0.02, `P_e = ${s.P_e}, Soll ${target}`);
  assert.ok(!s.scram.active, `Abschaltung bei Lastfolge: ${s.scram.cause}`);
  // Die Mitteltemperatur folgt dem Programm: bei kleiner Last kaelter.
  const T_avg = 0.5 * (s.T_ci + s.T_co) - 273.15;
  assert.ok(T_avg > 298 && T_avg < 306, `T_mittel ${T_avg.toFixed(1)} C`);
});
