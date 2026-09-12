// Was passiert in jedem Szenario, wenn der Spieler NICHTS tut?
//
//     node tests/tools/passive.mjs
//
// Die wichtigste Frage, die ein Leitstandsspiel an sich selbst stellen kann.
// Ein Szenario, das man im Schlaf besteht, lehrt nichts -- und der Spieler
// merkt nicht einmal, dass seine Eingriffe wirkungslos sind, weil der Ausgang
// ohne sie derselbe ist.
//
// Als dieses Werkzeug zum ersten Mal lief, bestand ein untaetiger Spieler
// SIEBEN von neun Szenarien, darunter den Kuehlmittelverlust (mit der hoechsten
// Punktzahl im ganzen Spiel) und die Frischdampf-Absperrung mit geborstenem
// Sicherheitsbehaelter.
import { readFile, readdir } from 'node:fs/promises';
import { createEngine } from '../../static/js/sim/engine.js';
import { getPlant } from '../../static/js/plants/index.js';
import { Session } from '../../static/js/game/session.js';

const DT = 0.05;
const DIR = new URL('../../static/data/scenarios/', import.meta.url);
const names = (await readdir(DIR)).filter((n) => n.endsWith('.json'));

const pad = (v, n, d = 0) => (typeof v === 'number' ? v.toFixed(d) : String(v)).padStart(n);

console.log('Szenario             Ausgang              Punkte  p_max  cont  T_cl_max  L_min  Behaelter    H2');
console.log('-'.repeat(100));
let passive = 0;
for (const n of names) {
  const def = JSON.parse(await readFile(new URL(n, DIR), 'utf8'));
  const e = createEngine(getPlant(def.reactor), { n: 1.0, seed: def.seed, cold: !!def.cold });
  const ses = new Session(e, def);
  ses.start();
  const s = e.state;
  let out = null, score = null;
  ses.onEnd = (r, f) => { out = f || 'GESCHAFFT'; score = r ? r.score : null; };
  let pmax = 0, cmax = 0, cladmax = 0, lmin = 1;
  for (let i = 0; i < Math.round((def.duration_s + 5) / DT) && !out; i++) {
    // Schweregrad genau so bilden wie main.js, sonst prueft die Sonde etwas
    // anderes als das Spiel -- die Bedingung "Meldung steht, niemand handelt"
    // haengt direkt daran.
    let worst = 0;
    for (const tile of e.trips.tiles()) {
      if ((tile.tile === 'new' || tile.tile === 'ack') && tile.severity > worst) worst = tile.severity;
    }
    e.step(DT); ses.step(DT, worst, e.trips.unacknowledgedSeconds());
    pmax = Math.max(pmax, s.p_prim); cmax = Math.max(cmax, s.pCont || 0);
    cladmax = Math.max(cladmax, s.T_cl);
    lmin = Math.min(lmin, s.L_rpv ?? s.L_drum ?? s.L_sg ?? 1);
  }
  if (out === 'GESCHAFFT') passive++;
  console.log([def.id.padEnd(20), String(out).padEnd(20), pad(score, 6),
    pad(pmax, 6), pad(cmax, 5, 1), pad(cladmax - 273, 9), pad(lmin * 100, 6),
    String(s.contFailed ?? '-').padStart(9), pad(s.h2Mass ?? 0, 5)].join(' '));
}
console.log('-'.repeat(100));
console.log(`Untaetig bestanden: ${passive} von ${names.length}`);
