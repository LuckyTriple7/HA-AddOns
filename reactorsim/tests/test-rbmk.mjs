// RBMK-1000.
//
// Der wichtigste Test dieser Datei ist der letzte: AZ-5 muss in BEIDEN
// Richtungen funktionieren. Löst die Schnellabschaltung bei leerem Kern eine
// Exkursion aus, bei vollem aber sauber ab, dann ist es ein Modell. Geht nur
// der erste Fall, ist es ein Zwischenfilm mit Physik-Anstrich.

import test from 'node:test';
import assert from 'node:assert/strict';

import { createEngine } from '../static/js/sim/engine.js';
import * as rbmk from '../static/js/plants/rbmk.js';

const DT = 0.05;
const run = (e, sec) => { for (let i = 0, n = Math.round(sec / DT); i < n; i++) e.step(DT); };
const boot = () => { const e = createEngine(rbmk, { n: 1.0 }); run(e, 600); return e; };

/** Fährt die Vorgeschichte: Volllast, Absenkung auf 7 %, warten. */
function lowPowerWithXenon(targetOrm) {
  const e = createEngine(rbmk, { n: 1.0 });
  const s = e.state;
  run(e, 600);
  const n0 = s.n;
  for (let i = 0, N = Math.round(2400 / DT); i < N; i++) {
    e.ctx.powerCtl.setpoint = n0 + (0.07 - n0) * (i / N);
    e.step(DT);
  }
  e.ctx.powerCtl.setpoint = 0.07;
  // Xenon baut auf, die Leistungsregelung zieht die Stäbe -- die
  // Abschaltreserve schmilzt von selbst. Nichts davon ist gescriptet.
  let guard = 0;
  while (e.derive().orm > targetOrm && guard < 7200 / DT && !s.scram.active) { e.step(DT); guard++; }
  return e;
}

test('Nennbetrieb ist kritisch und passt zusammen', () => {
  const e = createEngine(rbmk, { n: 1.0 });
  const s = e.state;
  const d = e.derive();
  assert.ok(Math.abs(d.rho_pcm) < 1, `rho = ${d.rho_pcm}`);
  assert.ok(d.orm > 40 && d.orm < 75, `Abschaltreserve ${d.orm.toFixed(1)} Stäbe`);
  assert.ok(Math.abs(s.P_th / e.spec.P0_th - 1) < 0.02, `P_th = ${s.P_th.toFixed(0)}`);
  assert.ok(Math.abs(s.P_e / e.spec.P0_e - 1) < 0.03, `P_e = ${s.P_e.toFixed(0)}`);
  assert.ok(s.alphaBar > 0.28 && s.alphaBar < 0.40, `Blasenanteil ${s.alphaBar.toFixed(3)}`);
  assert.ok(s.T_gr > 500 + 273 && s.T_gr < 700 + 273, `Graphit ${(s.T_gr - 273.15).toFixed(0)} C`);
});

test('der Dampfblasenkoeffizient ist positiv und haengt an der Abschaltreserve', () => {
  const e = boot();
  const s = e.state;
  const a0 = e.derive().voidCoeff;
  assert.ok(a0 > 0, `Koeffizient ${a0} -- er MUSS positiv sein`);

  // Stäbe ziehen heißt Abschaltreserve verlieren heißt schlimmerer Koeffizient.
  s.rod[0] = 0.02; s.rod[1] = 0.02;
  const d = e.derive();
  assert.ok(d.orm < 10, `Abschaltreserve ${d.orm.toFixed(1)}`);
  assert.ok(d.voidCoeff > a0 * 2, `Koeffizient stieg nur von ${a0} auf ${d.voidCoeff}`);
  assert.ok(d.voidCoeff > 50, `bei leerem Kern nur ${d.voidCoeff.toFixed(0)} pcm/%`);
});

test('eine Stunde Nennbetrieb bleibt ruhig', () => {
  const e = boot();
  const s = e.state;
  const n0 = s.n;
  run(e, 3600);
  assert.ok(Math.abs(s.n / n0 - 1) < 0.01, `n driftet: ${(s.n * 100).toFixed(2)} %`);
  assert.ok(!s.scram.active, `ungewollte Abschaltung: ${s.scram.cause}`);
  assert.equal(s.fault, null);
});

test('axiale Xenon-Schwingung bleibt beschraenkt und kehrt um', () => {
  const e = boot();
  const s = e.state;
  let max = -1, min = 1;
  let turned = false;
  let prev = s.ao, rising = true;
  for (let h = 0; h < 30; h++) {
    run(e, 3600);
    max = Math.max(max, s.ao); min = Math.min(min, s.ao);
    const nowRising = s.ao > prev;
    if (rising && !nowRising) turned = true;
    rising = nowRising; prev = s.ao;
    if (s.scram.active) break;
  }
  assert.ok(!s.scram.active, `Abschaltung durch die Schwingung: ${s.scram.cause}`);
  assert.ok(max < 0.35, `Schieflage lief bis ${max.toFixed(3)}`);
  assert.ok(turned, 'die Schieflage kehrt nicht um -- das waere Weglaufen, keine Schwingung');
});

test('Leistungsabsenkung frisst die Abschaltreserve auf', () => {
  const e = lowPowerWithXenon(15);
  const d = e.derive();
  assert.ok(!e.state.scram.active, `Abschaltung waehrend der Absenkung: ${e.state.scram.cause}`);
  assert.ok(d.orm <= 15, `Abschaltreserve blieb bei ${d.orm.toFixed(1)}`);
  assert.ok(e.state.X > 1.15, `Xenon nur bei ${e.state.X.toFixed(2)}`);
  // Und die Anlage meldet es auch.
  const tiles = e.trips.tiles().filter((x) => x.tile !== 'normal').map((x) => x.id);
  assert.ok(tiles.includes('orm_low'), `Meldungen: ${tiles.join(', ') || 'keine'}`);
});

test('AZ-5 bei leerem Kern: POSITIVE Einfuhr und Exkursion', () => {
  const e = lowPowerWithXenon(12);
  const s = e.state;
  assert.ok(!s.scram.active, 'schon vorher abgeschaltet');
  const nStart = s.n;

  e.scram('az5');
  let rhoMax = -1, nMax = 0, tipMax = 0;
  for (let i = 0, n = Math.round(6 / DT); i < n; i++) {
    e.step(DT);
    const d = e.derive();
    rhoMax = Math.max(rhoMax, d.rho_pcm);
    tipMax = Math.max(tipMax, d.tip_pcm);
    nMax = Math.max(nMax, s.n);
    if (s.destroyed) break;
  }
  assert.ok(tipMax > 400, `Spitzenbeitrag nur ${tipMax.toFixed(0)} pcm`);
  assert.ok(rhoMax > 100, `Reaktivitaet blieb bei ${rhoMax.toFixed(0)} pcm`);
  // Prompt kritisch: die Kette traegt sich ohne die verzoegerten Neutronen.
  assert.ok(rhoMax > e.ctx.betaEff * 1e5,
    `nicht prompt kritisch (${rhoMax.toFixed(0)} pcm gegen beta ${(e.ctx.betaEff * 1e5).toFixed(0)})`);
  assert.ok(nMax > 20 * nStart, `Leistung stieg nur auf das ${(nMax / nStart).toFixed(1)}-fache`);
  assert.ok(s.destroyed, 'der Kern haelt das aus -- dann stimmt die Kalibrierung nicht');
});

test('AZ-5 aus dem Nennbetrieb: sauber negativ, keine Exkursion', () => {
  const e = boot();
  const s = e.state;
  const d0 = e.derive();
  assert.ok(d0.orm > 40, `Abschaltreserve ${d0.orm.toFixed(1)}`);

  e.scram('az5');
  let rhoMax = -1e9, nMax = 0;
  for (let i = 0, n = Math.round(30 / DT); i < n; i++) {
    e.step(DT);
    rhoMax = Math.max(rhoMax, e.derive().rho_pcm);
    nMax = Math.max(nMax, s.n);
  }
  assert.ok(rhoMax <= 0, `Reaktivitaet wurde positiv: ${rhoMax.toFixed(0)} pcm`);
  assert.ok(nMax <= 1.001, `Leistungsspitze ${(nMax * 100).toFixed(1)} %`);
  assert.ok(s.n < 0.05, `nach 30 s noch ${(s.n * 100).toFixed(2)} %`);
  assert.ok(!s.destroyed, 'Brennstoffschaden bei sauberer Abschaltung');
  // Die Spitzen zaehlen hier gar nicht: die Staebe standen nicht weit genug
  // draussen, es hing also nie Graphit unter dem Kern.
  assert.equal(e.derive().tip_pcm, 0);
});

test('achtzehn Sekunden Einfahrzeit -- kein Schwerkraftfall', () => {
  const e = boot();
  const s = e.state;
  e.scram('test');
  run(e, 9);
  assert.ok(s.rod[0] > 0.4 && s.rod[0] < 0.95,
    `nach 9 s stehen die Staebe bei ${s.rod[0].toFixed(2)}`);
  run(e, 11);
  assert.ok(s.rod[0] > 0.999, `nach 20 s erst bei ${s.rod[0].toFixed(3)}`);
});

test('Zufaellige Eingriffe erzeugen kein NaN', async () => {
  const { Rng } = await import('../static/js/rng.js');
  const e = boot();
  const s = e.state;
  const rng = new Rng(26041986);
  for (let k = 0; k < 1500; k++) {
    const pick = rng.int(0, 4);
    if (pick === 0) s.rodDmd[0] = rng.next();
    else if (pick === 1) s.mcpDmd = rng.range(0.3, 1.1);
    else if (pick === 2) e.ctx.powerCtl.auto = rng.next() > 0.4;
    else if (pick === 3) e.ctx.mcp[rng.int(0, 7)][rng.next() > 0.5 ? 'trip' : 'start']();
    else s.P_demand = rng.range(0, e.spec.P0_e);
    for (let i = 0; i < 10; i++) e.step(DT);
    assert.equal(s.fault, null, `Simulationsfehler bei ${k}: ${s.fault}`);
    assert.ok(Number.isFinite(s.n) && s.n >= 0, `n = ${s.n}`);
    assert.ok(Number.isFinite(s.p_drum) && s.p_drum > 0, `p_drum = ${s.p_drum}`);
    assert.ok(Number.isFinite(s.T_gr), `T_gr = ${s.T_gr}`);
  }
});
