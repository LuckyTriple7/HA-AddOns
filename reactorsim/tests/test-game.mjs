// Spielschicht: Bedarfskurve, Störungen, Wertung, Sitzungsablauf.

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';

import { createEngine } from '../static/js/sim/engine.js';
import { getPlant } from '../static/js/plants/index.js';
import { Scenario, RunState, demandAt } from '../static/js/game/scenario.js';
import { score } from '../static/js/game/scoring.js';
import { Session, PHASE } from '../static/js/game/session.js';

const DT = 0.05;
const SCN_DIR = new URL('../static/data/scenarios/', import.meta.url);

async function loadScenarios() {
  const names = (await readdir(SCN_DIR)).filter((n) => n.endsWith('.json'));
  const out = [];
  for (const n of names) {
    out.push(JSON.parse(await readFile(new URL(n, SCN_DIR), 'utf8')));
  }
  return out;
}

test('Bedarfskurve: Stufen halten, Rampen interpolieren', () => {
  const pts = [
    { t: 0, mw: 1000 },
    { t: 100, mw: 1000 },
    { t: 200, mw: 500, ramp: 'linear' },
    { t: 300, mw: 500 },
  ];
  assert.equal(demandAt(pts, -10), 1000);
  assert.equal(demandAt(pts, 50), 1000);
  assert.equal(demandAt(pts, 150), 750);      // mitten in der Rampe
  assert.equal(demandAt(pts, 250), 500);      // Stufe haelt den alten Wert
  assert.equal(demandAt(pts, 9999), 500);
});

test('Störungszeitpunkte sind gesät, nicht zufällig', () => {
  const def = {
    id: 'x', seed: 99, duration_s: 100,
    events: [{ t: 'rand(10,90)', id: 'demand_step' }],
  };
  const a = new Scenario(def).events[0].t;
  const b = new Scenario(def).events[0].t;
  assert.equal(a, b);
  assert.ok(a >= 10 && a <= 90, `Zeitpunkt ${a}`);
  const c = new Scenario({ ...def, seed: 100 }).events[0].t;
  assert.notEqual(a, c, 'anderer Startwert, gleicher Zeitpunkt');
});

test('Störungen kommen genau einmal', () => {
  const scn = new Scenario({
    id: 'x', seed: 1, duration_s: 100,
    events: [{ t: 10, id: 'demand_step' }, { t: 20, id: 'rod_stuck' }],
  });
  assert.equal(scn.due(5).length, 0);
  assert.equal(scn.due(15).length, 1);
  assert.equal(scn.due(15).length, 0);
  assert.equal(scn.due(50).length, 1);
});

test('Wertung: Bestandteile und Vorzeichen', () => {
  const perfect = {
    energy_mwh_delivered: 1000, energy_mwh_demanded: 1000,
    deviation_mwh: 0, alarm_seconds_unacked: 0,
    violation_seconds: { 1: 0, 2: 0, 3: 0 },
    scram_count: 0, fuel_damage: false, completed: true, difficulty: 2,
  };
  const a = score(perfect);
  assert.equal(a.score, 1500);   // 1000 Energie + 2 × 250 Bonus

  const bad = score({ ...perfect, scram_count: 1, fuel_damage: true, completed: false });
  assert.ok(bad.score < 0, `Punkte ${bad.score}`);
  assert.equal(bad.parts.bonus, 0);

  // Mehr als angefordert zu liefern bringt keine Zusatzpunkte.
  const over = score({ ...perfect, energy_mwh_delivered: 2000 });
  assert.equal(over.score, a.score);

  // Jede Kennzahl wirkt in die richtige Richtung.
  assert.ok(score({ ...perfect, deviation_mwh: 50 }).score < a.score);
  assert.ok(score({ ...perfect, alarm_seconds_unacked: 600 }).score < a.score);
  assert.ok(score({ ...perfect, violation_seconds: { 1: 0, 2: 0, 3: 60 } }).score < a.score);
});

test('alle Szenariodateien sind vollständig und stimmig', async () => {
  const defs = await loadScenarios();
  assert.ok(defs.length >= 4, `nur ${defs.length} Szenarien`);
  const ids = new Set();
  for (const d of defs) {
    assert.ok(d.id && !ids.has(d.id), `doppelte Kennung ${d.id}`);
    ids.add(d.id);
    assert.ok(getPlant(d.reactor), `unbekannter Reaktortyp ${d.reactor}`);
    assert.ok(d.duration_s > 0);
    assert.ok(Array.isArray(d.demand) && d.demand.length >= 2, `${d.id}: keine Bedarfskurve`);
    // Die Kurve muss aufsteigend in der Zeit sein, sonst greift die
    // Interpolation ins Leere.
    for (let i = 1; i < d.demand.length; i++) {
      assert.ok(d.demand[i].t > d.demand[i - 1].t, `${d.id}: Kurve nicht aufsteigend`);
    }
    const spec = getPlant(d.reactor).spec;
    for (const pt of d.demand) {
      assert.ok(pt.mw >= 0 && pt.mw <= spec.P0_e * 1.05,
        `${d.id}: ${pt.mw} MW passt nicht zu ${spec.P0_e} MWe`);
    }
    // Texte nur als Schluessel, nie als Klartext.
    assert.ok(/^scn_/.test(d.title_key), `${d.id}: Titel ist kein Schluessel`);
    assert.ok(/^scn_/.test(d.brief_key), `${d.id}: Einweisung ist kein Schluessel`);
  }
});

test('alle Szenarientexte sind in beiden Sprachen da', async () => {
  const defs = await loadScenarios();
  const de = JSON.parse(await readFile(new URL('../locales/de.json', import.meta.url), 'utf8'));
  const en = JSON.parse(await readFile(new URL('../locales/en.json', import.meta.url), 'utf8'));
  for (const d of defs) {
    for (const key of [d.title_key, d.brief_key]) {
      assert.ok(de[key], `fehlt in de.json: ${key}`);
      assert.ok(en[key], `fehlt in en.json: ${key}`);
    }
  }
});

test('jedes Szenario läuft ohne Ausnahme bis zum Ende', async () => {
  const defs = await loadScenarios();
  for (const def of defs) {
    const plant = getPlant(def.reactor);
    // cold MUSS mit -- main.js tut das auch (boot() reicht scenarioDef.cold
    // durch). Ohne das startete ein Kaltstart-Szenario hier mit einem Kern
    // auf Volllast, waehrend seine Bedarfskurve bei null beginnt: eine Lage,
    // die es im Spiel nicht gibt. Aufgefallen ist es erst, als die
    // Netzabweichung zu einer Fehlbedingung wurde und der Lauf deswegen nach
    // zehn Minuten endete, bevor ueberhaupt Leistung angefordert war.
    const e = createEngine(plant, { n: def.cold ? 1e-6 : 1.0, cold: !!def.cold, seed: def.seed });
    const session = new Session(e, def);
    let ended = null;
    session.onEnd = (result, failed) => { ended = { result, failed }; };
    session.start();

    const steps = Math.round((def.duration_s + 60) / DT);
    for (let i = 0; i < steps && session.phase === PHASE.RUNNING; i++) {
      e.step(DT);
      session.step(DT, 0, 0);
      assert.equal(e.state.fault, null, `${def.id}: Simulationsfehler ${e.state.fault}`);
    }

    assert.ok(ended, `${def.id}: Lauf endete nie`);
    // Ohne Bedienung darf ein Szenario scheitern -- aber es muss eine Wertung
    // geben, und die Kennzahlen muessen brauchbar sein.
    if (ended.result) {
      const sum = ended.result.summary;
      assert.ok(Number.isFinite(ended.result.score), `${def.id}: Punkte ${ended.result.score}`);
      assert.ok(sum.energy_mwh_demanded > 0, `${def.id}: keine Anforderung`);
      assert.ok(sum.duration_s > 0);
      for (const v of Object.values(sum.violation_seconds)) assert.ok(Number.isFinite(v));
    }
  }
});

test('Freies Spiel endet nur bei Brennstoffschaden', () => {
  const e = createEngine(getPlant('pwr'), { n: 1.0 });
  const session = new Session(e, null);
  assert.equal(session.phase, PHASE.RUNNING);
  session.start();
  for (let i = 0; i < 2000; i++) { e.step(DT); session.step(DT, 0, 0); }
  assert.equal(session.phase, PHASE.RUNNING);
  assert.equal(session.result, null);
});

test('Wertung des Clients und des Servers stimmen überein', async () => {
  // Der Server rechnet mit derselben Formel nach, weil er dem Browser den
  // Punktestand nicht glauben darf. Dieser Test haelt die Fixtures fest, die
  // tests/test_scoring.py auf der Python-Seite prueft.
  const fixtures = JSON.parse(
    await readFile(new URL('./fixtures/scoring.json', import.meta.url), 'utf8'));
  for (const f of fixtures) {
    assert.equal(score(f.summary).score, f.score,
      `Fixture ${f.name}: ${score(f.summary).score} statt ${f.score}`);
  }
});

test('Netzabweichung wird in Sekunden gezählt, nicht in Schritten', () => {
  // Die Bedingung zaehlt, WIE LANGE die Abweichung ansteht. Vorher stand die
  // Schrittweite als Zahl (0,05) fest im Code statt aus dem Aufruf zu kommen:
  // mit jedem anderen dt lief die Uhr um genau dieses Verhaeltnis falsch, und
  // zwar lautlos. Also zweimal dieselbe Sim-Zeit, einmal in feinen und einmal
  // in groben Schritten -- beide Laeufe muessen im selben Augenblick scheitern.
  const def = {
    id: 'test', reactor: 'pwr', duration_s: 600, difficulty: 1,
    demand: [{ t: 0, mw: 1400 }],
    grid: { tolerance_mw: 50 },
    fail: [{ type: 'grid_deviation', mw: 100, for_s: 30 }],
  };
  const spec = { P0_e: 1400 };

  const runUntilFail = (dt) => {
    const run = new RunState(new Scenario(def), spec);
    // Generator aus, Anforderung steht: die Abweichung ist von der ersten
    // Sekunde an groesser als die erlaubten 100 MW.
    const s = { t_sim: 0, P_e: 0, destroyed: false, scram: { active: false } };
    for (let i = 0; i < Math.round(120 / dt); i++) {
      s.t_sim += dt;
      if (run.checkFail(s, {}, dt)) return s.t_sim;
    }
    return null;
  };

  const fine = runUntilFail(0.05);
  const coarse = runUntilFail(0.5);
  assert.ok(fine !== null && coarse !== null, `kein Fehlschlag: ${fine} / ${coarse}`);
  assert.ok(Math.abs(fine - 30) < 1, `feine Schritte scheiterten bei ${fine} s statt 30 s`);
  assert.ok(Math.abs(coarse - fine) < 1,
    `grobe Schritte scheiterten bei ${coarse} s, feine bei ${fine} s`);
});
