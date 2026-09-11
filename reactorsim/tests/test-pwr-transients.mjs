// Störfälle und Lastwechsel am Druckwasserreaktor.

import test from 'node:test';
import assert from 'node:assert/strict';

import { createEngine } from '../static/js/sim/engine.js';
import * as pwr from '../static/js/plants/pwr.js';
import { Rng } from '../static/js/rng.js';

const DT = 0.05;

function boot() {
  const e = createEngine(pwr, { n: 1.0 });
  for (let i = 0, n = Math.round(600 / DT); i < n; i++) e.step(DT);
  return e;
}
function run(e, seconds) {
  for (let i = 0, n = Math.round(seconds / DT); i < n; i++) e.step(DT);
}

test('Schnellabschaltung: Leistung faellt, Nachzerfallswaerme bleibt', () => {
  const e = boot();
  const s = e.state;
  e.scram('test');

  run(e, 3);
  assert.ok(s.n < 0.06, `nach 3 s noch ${(s.n * 100).toFixed(2)} %`);
  assert.ok(s.rod[0] > 0.99 && s.rod[1] > 0.99, 'Staebe nicht eingefahren');

  run(e, 7);   // t = 10 s
  const p10 = 100 * s.P_th / e.spec.P0_th;
  assert.ok(p10 > 5 && p10 < 10, `bei 10 s: ${p10.toFixed(2)} % (Nachzerfall plus Restspaltung)`);

  run(e, 3590); // t = 1 h
  const p1h = 100 * s.P_th / e.spec.P0_th;
  assert.ok(p1h > 0.7 && p1h < 1.3, `bei 1 h: ${p1h.toFixed(2)} %`);
  assert.ok(!s.destroyed, 'Brennstoffschaden nach sauberer Abschaltung');
  assert.ok(s.T_cl < 700, `Huellrohr ${(s.T_cl - 273.15).toFixed(0)} C`);
});

test('Jod-Grube: nach der Abschaltung reicht die Stabwirksamkeit nicht', () => {
  const e = boot();
  const s = e.state;
  e.scram('test');
  run(e, 9 * 3600);
  // Xenon steht auf dem Gipfel. Die dafuer noetige Reaktivitaet uebersteigt,
  // was die Staebe hergeben -- der Reaktor ist wirklich nicht anfahrbar, das
  // steht nicht bloss als Text auf dem Schirm.
  assert.ok(s.X > 1.7, `X = ${s.X.toFixed(2)}`);
  const xenonPcm = e.derive().breakdown.xenon * 1e5;
  const rodWorth = e.spec.rodBanks.reduce((a, b) => a + b.worth, 0);
  assert.ok(-xenonPcm > 4700, `Xenon ${xenonPcm.toFixed(0)} pcm`);
  // Alle Staebe gezogen ergaebe noch immer keine Kritikalitaet.
  s.rod[0] = 0; s.rod[1] = 0;
  assert.ok(e.reactivity.compute(s, e.spec) < 0,
    `mit gezogenen Staeben waere der Kern kritisch (Stabwirksamkeit ${rodWorth} pcm)`);
});

test('Turbinenschnellschluss: Druecke bleiben unter den Sicherheitsventilen', () => {
  const e = boot();
  const s = e.state;
  s.turbineTripped = true;
  s.breaker = false;
  let pMax = 0, pSgMax = 0;
  for (let i = 0, n = Math.round(300 / DT); i < n; i++) {
    e.step(DT);
    pMax = Math.max(pMax, s.pzr_p);
    pSgMax = Math.max(pSgMax, s.p_sg);
  }
  assert.ok(pMax < e.spec.pressurizer.safety, `Primaer ${pMax.toFixed(1)} bar`);
  assert.ok(pSgMax < 88, `Sekundaer ${pSgMax.toFixed(1)} bar`);
  assert.ok(!s.destroyed, 'Brennstoffschaden beim Lastabwurf');
});

test('Ausfall aller Hauptkuehlmittelpumpen meldet -- und wer scrammt, uebersteht es', () => {
  // Die Schnellabschaltung loest nichts mehr von selbst aus (das ist Sache
  // des Bedieners) -- geprueft wird deshalb erst, dass die Meldung wirklich
  // kommt, und danach, dass eine Schnellabschaltung von Hand den Kern
  // tatsaechlich rettet.
  const e = boot();
  const s = e.state;
  for (const p of e.ctx.pumps) p.trip();
  run(e, 60);
  assert.ok(e.trips.states.get('rcp_lost').latched, 'keine Meldung nach Pumpenausfall');
  assert.ok(!s.scram.active, 'SCRAM loeste von selbst aus');

  e.scram('manual');
  run(e, 60);
  assert.ok(s.W_core < 0.2 * e.spec.coolant.W0, `Durchsatz ${s.W_core.toFixed(0)} kg/s`);
  // Der Auslauf haelt den Kern in den ersten Sekunden kuehl.
  assert.ok(!s.destroyed, 'Brennstoffschaden trotz Abschaltung von Hand');
});

test('Rueckkopplungen fangen eine Reaktivitaetszugabe von selbst ab', () => {
  const e = boot();
  const s = e.state;
  e.ctx.rodCtl.auto = false;   // Staebe festhalten, nur die Physik wirken lassen

  const before = e.derive();
  const fb0 = (before.breakdown.doppler + before.breakdown.moderator) * 1e5;
  const T0 = 0.5 * (s.T_ci + s.T_co);
  const nStart = s.n;

  // 150 pcm ueber eine Minute. Bewusst eine Rampe und kein Sprung: ein Sprung
  // dieser Groesse liefe ueber die Leistungsausloesung, und geprueft wuerde
  // dann die Abschaltung statt der Rueckkopplung.
  let peak = 0;
  for (let i = 0, n = Math.round(60 / DT); i < n; i++) {
    s.rho_ext = 150e-5 * (i / n);
    e.step(DT);
    peak = Math.max(peak, s.n);
  }
  for (let i = 0, n = Math.round(600 / DT); i < n; i++) { e.step(DT); peak = Math.max(peak, s.n); }

  assert.ok(!s.scram.active, `Abschaltung statt Selbstbegrenzung: ${s.scram.cause}`);
  assert.ok(Number.isFinite(s.n), 'Leistung nicht endlich');
  assert.ok(peak > nStart * 1.005, `keine Leistungserhoehung (Spitze ${(peak * 100).toFixed(2)} %)`);
  assert.ok(peak < 1.5 * nStart, `Ueberschwinger auf ${(peak * 100).toFixed(0)} %`);

  const after = e.derive();
  const fb1 = (after.breakdown.doppler + after.breakdown.moderator) * 1e5;
  // Die Bilanz steht wieder bei null, und die 150 pcm stecken jetzt in den
  // Temperaturrueckkopplungen.
  assert.ok(Math.abs(after.rho_pcm) < 30, `rho = ${after.rho_pcm.toFixed(1)} pcm`);
  assert.ok(Math.abs((fb1 - fb0) + 150) < 45,
    `Rueckkopplung aenderte sich um ${(fb1 - fb0).toFixed(0)} pcm statt um -150`);

  // Die Anlage findet ihren neuen Punkt ueber die Temperatur, nicht ueber die
  // Leistung: die Turbine nimmt weiter, was sie vorher nahm, also steigt die
  // Mitteltemperatur, bis der Moderatorkoeffizient die Zugabe aufgefressen hat.
  const T1 = 0.5 * (s.T_ci + s.T_co);
  assert.ok(T1 - T0 > 2 && T1 - T0 < 12, `T_mittel stieg um ${(T1 - T0).toFixed(2)} K`);
});

test('Bor wirkt langsam: eine Dosierung braucht Minuten', () => {
  const e = boot();
  const s = e.state;
  const start = s.C_B;
  s.boronFlow = 1;                 // aufborieren
  run(e, 60);
  const after1min = s.C_B;
  run(e, 540);
  assert.ok(after1min - start < 4, `nach 1 min schon ${(after1min - start).toFixed(1)} ppm`);
  assert.ok(s.C_B - start > 10, `nach 10 min erst ${(s.C_B - start).toFixed(1)} ppm`);
  // Die Regelung faengt das mit den Staeben ab, ohne dass die Leistung wegbricht.
  assert.ok(Math.abs(s.P_e / e.spec.P0_e - 1) < 0.03, `P_e = ${s.P_e.toFixed(0)}`);
});

test('Zufaellige Eingriffe erzeugen kein NaN', () => {
  const e = boot();
  const s = e.state;
  const rng = new Rng(20260911);
  for (let k = 0; k < 4000; k++) {
    const pick = rng.int(0, 5);
    if (pick === 0) s.rodDmd[0] = rng.next();
    else if (pick === 1) s.P_demand = rng.range(0, e.spec.P0_e * 1.1);
    else if (pick === 2) s.boronFlow = rng.int(-1, 1);
    else if (pick === 3) e.ctx.pumps[rng.int(0, 3)][rng.next() > 0.5 ? 'trip' : 'start']();
    else if (pick === 4) e.ctx.govCtl.auto = rng.next() > 0.3;
    else s.bypass = rng.next();
    for (let i = 0; i < 10; i++) e.step(DT);
    assert.equal(s.fault, null, `Simulationsfehler bei Schritt ${k}: ${s.fault}`);
    assert.ok(Number.isFinite(s.n) && s.n >= 0, `n = ${s.n}`);
    assert.ok(Number.isFinite(s.p_sg) && s.p_sg > 0, `p_sg = ${s.p_sg}`);
    assert.ok(Number.isFinite(s.pzr_p) && s.pzr_p > 0, `pzr_p = ${s.pzr_p}`);
    assert.ok(Number.isFinite(s.T_f), `T_f = ${s.T_f}`);
  }
});

test('gleicher Startwert, gleiche Eingaben: bitgleiches Ergebnis', async () => {
  const { hash } = await import('../static/js/sim/state.js');
  const play = () => {
    const e = createEngine(pwr, { n: 1.0 });
    const rng = new Rng(4711);
    for (let k = 0; k < 200; k++) {
      e.state.P_demand = rng.range(700, 1400);
      for (let i = 0; i < 20; i++) e.step(DT);
    }
    return hash(e.state);
  };
  assert.equal(play(), play());
});
