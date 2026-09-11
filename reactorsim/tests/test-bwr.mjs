// Siedewasserreaktor.
//
// Diese Datei prüft nicht nur den Typ, sondern die Abstraktion: der
// Siedewasserreaktor war der erste Typ nach dem Druckwasserreaktor, und jede
// Änderung, die er an der Engine nötig gemacht hätte, wäre ein Hinweis auf
// eine falsch geschnittene Schnittstelle gewesen. Nötig war genau eine:
// ein Haken für den siedenden Kern, weil dort die Austrittstemperatur
// festliegt und die Wärme in den Dampfgehalt geht statt in die Temperatur.

import test from 'node:test';
import assert from 'node:assert/strict';

import { createEngine } from '../static/js/sim/engine.js';
import * as bwr from '../static/js/plants/bwr.js';
import * as pwr from '../static/js/plants/pwr.js';

const DT = 0.05;
const boot = (opts = {}) => {
  const e = createEngine(bwr, { n: 1.0, ...opts });
  for (let i = 0, n = Math.round(400 / DT); i < n; i++) e.step(DT);
  return e;
};
const run = (e, sec) => { for (let i = 0, n = Math.round(sec / DT); i < n; i++) e.step(DT); };

test('Startzustand ist kritisch und siedet richtig', () => {
  const e = createEngine(bwr, { n: 1.0 });
  const s = e.state;
  assert.ok(Math.abs(e.derive().rho_pcm) < 1, `rho = ${e.derive().rho_pcm}`);
  // Kritisch wird hier ueber die Stabstellung, nicht ueber Bor.
  assert.ok(s.rod[0] > 0.2 && s.rod[0] < 0.8, `Stabstellung ${s.rod[0].toFixed(3)}`);
  assert.ok(s.alphaBar > 0.33 && s.alphaBar < 0.45, `Blasenanteil ${s.alphaBar.toFixed(3)}`);
  assert.ok(s.x_e > 0.12 && s.x_e < 0.19, `Dampfgehalt ${s.x_e.toFixed(3)}`);
  assert.ok(s.dTsub > 8 && s.dTsub < 16, `Unterkuehlung ${s.dTsub.toFixed(1)} K`);
  // Bor ist bei diesem Typ kein Regelmittel -- es steht nicht in der
  // Reaktivitaetsbilanz, und der Spieler bekommt dafuer auch keine Bedienung.
  assert.ok(!e.spec.feedbacks.includes('boron'), 'Bor sollte nicht in der Bilanz stehen');
  assert.ok(!e.spec.feedbacks.includes('mtc'), 'Moderatorkoeffizient laeuft hier ueber die Blasen');
});

test('eine Stunde ohne Eingriff bleibt ruhig', () => {
  const e = boot();
  const s = e.state;
  const ref = { n: s.n, p: s.p_dome, L: s.L_rpv, a: s.alphaBar };
  run(e, 3200);
  assert.ok(Math.abs(s.n / ref.n - 1) < 0.02, `n driftet: ${s.n} vs ${ref.n}`);
  assert.ok(Math.abs(s.p_dome - ref.p) < 0.5, `Domdruck driftet: ${s.p_dome}`);
  assert.ok(Math.abs(s.L_rpv - ref.L) < 0.05, `Fuellstand driftet: ${s.L_rpv}`);
  assert.ok(Math.abs(s.alphaBar - ref.a) < 0.02, `Blasenanteil driftet: ${s.alphaBar}`);
  assert.ok(!s.scram.active, `ungewollte Abschaltung: ${s.scram.cause}`);
  assert.equal(s.fault, null);
});

test('Energiebilanz und Nennwerte', () => {
  const e = boot();
  const s = e.state;
  assert.ok(Math.abs(s.P_th / e.spec.P0_th - 1) < 0.02, `P_th = ${s.P_th.toFixed(0)}`);
  assert.ok(Math.abs(s.P_e / e.spec.P0_e - 1) < 0.03, `P_e = ${s.P_e.toFixed(0)}`);
  const eta = s.P_e / s.P_th;
  assert.ok(eta > 0.33 && eta < 0.37, `Wirkungsgrad ${(eta * 100).toFixed(2)} %`);
});

test('Umwaelzstrom ist das Leistungsstellglied', () => {
  const e = boot();
  const s = e.state;
  const n0 = s.n;
  const rod0 = s.rod[0];

  s.recircDmd = 0.80;
  run(e, 600);
  const drop = 1 - s.n / n0;
  assert.ok(drop > 0.07 && drop < 0.25,
    `Durchsatz 100 → 80 % aenderte die Leistung um ${(drop * 100).toFixed(1)} %`);
  assert.ok(s.alphaBar > 0.39, `Blasenanteil stieg nur auf ${s.alphaBar.toFixed(3)}`);
  assert.ok(Math.abs(s.rod[0] - rod0) < 1e-9, 'Staebe haben sich bewegt');

  s.recircDmd = 1.0;
  run(e, 900);
  assert.ok(Math.abs(s.n / n0 - 1) < 0.03, `nicht umkehrbar: ${(s.n * 100).toFixed(1)} %`);
});

test('Frischdampf-Absperrung gibt POSITIVE Reaktivitaet', () => {
  const e = boot();
  const s = e.state;
  const a0 = s.alphaBar;
  s.msiv = 0;

  let rhoMax = -1, nMax = 0, pMax = 0;
  for (let i = 0, n = Math.round(4 / DT); i < n; i++) {
    e.step(DT);
    const d = e.derive();
    rhoMax = Math.max(rhoMax, d.rho_pcm);
    nMax = Math.max(nMax, s.n);
    pMax = Math.max(pMax, s.p_dome);
  }
  // Das ist die klassische Druckstoerung dieses Typs: Druck steigt, Blasen
  // fallen zusammen, mehr Moderator, mehr Leistung. Geht die Leistung hier
  // zurueck, ist das Vorzeichen der Blasenrueckkopplung falsch herum.
  assert.ok(rhoMax > 20, `Reaktivitaet blieb bei ${rhoMax.toFixed(0)} pcm`);
  assert.ok(nMax > 1.03, `Leistungsspitze nur ${(nMax * 100).toFixed(1)} %`);
  assert.ok(s.alphaBar < a0, `Blasen fielen nicht zusammen: ${s.alphaBar.toFixed(3)} vs ${a0.toFixed(3)}`);

  run(e, 300);
  assert.ok(s.scram.active, 'keine Abschaltung nach Absperrung');
  assert.ok(!s.destroyed, 'Brennstoffschaden');
  assert.ok(s.p_dome < 95, `Domdruck ${s.p_dome.toFixed(1)} bar`);
});

test('Instabilitaetszone: Schwingung waechst, Ueberwachung loest aus', () => {
  const e = boot();
  const s = e.state;
  s.recircDmd = 0.45;
  run(e, 200);
  // Leistung mit den Staeben wieder hochziehen -- damit wandert der
  // Betriebspunkt in die gesperrte Ecke des Kennfelds.
  let steps = 0;
  while (s.n < 0.88 && steps < 600 && !s.scram.active && s.rodDmd[0] > 0.001) {
    s.rodDmd[0] = Math.max(0, s.rodDmd[0] - 0.002);
    run(e, 8);
    steps++;
  }
  const d = e.derive();
  assert.ok(d.decayRatio > 1.0, `Abklingverhaeltnis nur ${d.decayRatio.toFixed(2)}`);

  let amp = 0;
  for (let i = 0, n = Math.round(400 / DT); i < n; i++) { e.step(DT); amp = Math.max(amp, Math.abs(s.osc)); }
  assert.ok(amp > 0.15, `Schwingung wuchs nur auf ${amp.toFixed(3)}`);
  assert.ok(s.scram.active, 'Schwingungsueberwachung hat nicht ausgeloest');
  assert.equal(s.scram.cause, 'oprm', `Ausloesung durch ${s.scram.cause}`);
  assert.ok(!s.destroyed, 'Brennstoffschaden durch Schwingung');
});

test('Schnellabschaltung: Pumpen laufen mit ab, Naturumlauf bleibt', () => {
  const e = boot();
  const s = e.state;
  e.scram('test');
  run(e, 5);
  assert.ok(s.n < 0.08, `nach 5 s noch ${(s.n * 100).toFixed(2)} %`);
  run(e, 3595);
  const pct = 100 * s.P_th / e.spec.P0_th;
  assert.ok(pct > 0.7 && pct < 1.3, `nach 1 h: ${pct.toFixed(2)} %`);
  // Ohne Naturumlauf gaebe es keine Nachwaermeabfuhr.
  assert.ok(s.W_core > 0.08 * e.spec.recirc.W0, `Kerndurchsatz ${s.W_core.toFixed(0)} kg/s`);
  assert.ok(!s.destroyed);
});

test('die Engine verzweigt nicht nach Reaktortyp', async () => {
  // Der Rechenkern darf keinen Typnamen kennen. Faellt dieser Test, ist etwas
  // Typspezifisches in die gemeinsame Schicht gerutscht.
  const fs = await import('node:fs/promises');
  const dir = new URL('../static/js/sim/', import.meta.url);
  for (const name of await fs.readdir(dir)) {
    if (!name.endsWith('.js')) continue;
    const src = await fs.readFile(new URL(name, dir), 'utf8');
    const code = src.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
    for (const word of ["'pwr'", '"pwr"', "'bwr'", '"bwr"', "'rbmk'", '"rbmk"']) {
      assert.ok(!code.includes(word), `sim/${name} nennt ${word}`);
    }
    assert.ok(!/Math\.random/.test(code), `sim/${name} benutzt Math.random`);
  }
});

test('beide Typen laufen gleichzeitig, ohne sich zu stoeren', () => {
  // Die Typdateien halten gemeinsam genutzte Datenobjekte. Wer dort im Betrieb
  // hineinschreibt, veraendert den anderen Lauf mit.
  const a = createEngine(pwr, { n: 1.0 });
  const b = createEngine(bwr, { n: 1.0 });
  const c = createEngine(pwr, { n: 1.0 });
  const cb0 = c.state.C_B;
  for (let i = 0; i < 2000; i++) { a.step(DT); b.step(DT); c.step(DT); }
  assert.ok(Math.abs(a.state.C_B - c.state.C_B) < 1e-9, 'zwei DWR laufen auseinander');
  assert.ok(Math.abs(cb0 - c.state.C_B) < 5, 'Borkonzentration driftet ohne Dosierung');
  assert.equal(a.state.fault, null);
  assert.equal(b.state.fault, null);
});
