// Gegenprobe zu passive.mjs: schafft ein VERNUENFTIGER Bediener die Szenarien?
//
//     node tests/tools/competent.mjs
//
// passive.mjs allein genuegt nicht. Ein Szenario so scharf zu stellen, dass
// Nichtstun scheitert, ist leicht -- man kann dabei versehentlich auch jeden
// richtigen Lauf unmoeglich machen und haette die Fehlerrichtung nur gedreht.
// Diese Sonde faehrt eine schlichte, aber korrekte Betriebsweise:
//
//   * steht eine Ausloesemeldung an, wird abgeschaltet (die Meldetafel tut es
//     nicht von selbst, siehe sim/trips.js)
//   * nach dem Abschalten mit abgesperrtem Frischdampf: Notkondensator auf
//   * steigt der Sicherheitsbehaelterdruck, wird gevented
//   * ohne Wechselstrom: Loeschwasser einspeisen
//   * Regler bleiben in Automatik
//
// Das ist keine Meisterleistung, sondern das Minimum dessen, was die Hilfe-
// texte beschreiben. Wer das tut, muss durchkommen.
import { readFile, readdir } from 'node:fs/promises';
import { createEngine } from '../../static/js/sim/engine.js';
import { getPlant } from '../../static/js/plants/index.js';
import { Session } from '../../static/js/game/session.js';

const DT = 0.05;
const DIR = new URL('../../static/data/scenarios/', import.meta.url);
const names = (await readdir(DIR)).filter((n) => n.endsWith('.json'));

/** Der Bediener. Laeuft einmal je Rechenschritt, vor engine.step(). */
function operate(e, s, worst) {
  // Ausloesemeldung steht -> abschalten. Ohne Verzug: das ist die Handlung,
  // auf die jeder Hilfetext mit "Sofort SCRAM/RESA/AZ-5" verweist.
  if (worst >= 3 && !s.scram.active) e.scram('operator');

  // Siedewasserreaktor: abgeschaltet und isoliert -> Notkondensator ist die
  // einzige verbliebene Waermesenke.
  if (s.icDemand !== undefined && s.scram.active && s.msiv < 0.5) s.icDemand = 1;
  // Sicherheitsbehaelter venten, bevor der Auslegungsdruck erreicht ist.
  if (s.contVentOpen !== undefined && s.pCont > 3.0) s.contVentOpen = true;
  // Ohne Wechselstrom bringt nur noch das Loeschwasser Wasser in den Kern.
  if (s.fireInjOn !== undefined && s.acPower === false) s.fireInjOn = true;

  // Druckwasserreaktor: das Abblaseventil steht offen, obwohl der Druck
  // laengst darunter liegt -- dann klemmt es, und das Blockventil davor ist
  // die Antwort. Genau der Handgriff, der in Three Mile Island erst nach
  // zweieinhalb Stunden kam.
  const d = e.derive();
  if (s.porvBlock !== undefined && d.porvStuck) s.porvBlock = 0;

  // ── Last fuehren ────────────────────────────────────────────────────────
  // Ohne das prueft die Sonde die Szenarien nicht, deren ganze Aufgabe das
  // Fuehren der Bedarfskurve IST -- sie scheitern dann an der Netzbedingung,
  // und zwar an der Sonde, nicht am Spiel.
  if (s.scram.active) return;
  const err = s.P_demand - s.P_e;          // MW, positiv = zu wenig Leistung

  // Siedewasserreaktor und RBMK stellen die Leistung ueber den Umwaelzstrom.
  if (s.recircDmd !== undefined) {
    s.recircDmd = Math.max(0.45, Math.min(1.10, s.recircDmd + err * 2e-6));
  }
  // Druckwasserreaktor: die Turbine folgt von selbst, solange der Kern die
  // Reaktivitaet hat. Klemmt eine Stabgruppe, bleibt nur Bor -- verduennen
  // hebt die Leistung, aufborieren senkt sie, beides mit drei Minuten Verzug.
  if (s.boronFlow !== undefined) {
    s.boronFlow = err > 40 ? -1 : (err < -40 ? 1 : 0);
  }
  // RBMK: die Leistung macht der Kern, gefuehrt vom Leistungsregler. Schaltet
  // ein Szenario den ab (power_regulator_off), bleiben nur die Staebe von
  // Hand -- ohne das scheitert die Nachtschicht an der Bedarfskurve, und zwar
  // an der Sonde. Ziehen erhoeht die Leistung, einfahren senkt sie; die
  // Abschaltreserve setzt dabei die Grenze, nicht der Bedarf.
  if (e.ctx.powerCtl && !e.ctx.powerCtl.auto && Math.abs(err) > 20) {
    const dir = err > 0 ? -1 : 1;                  // -1 = ziehen
    const orm = d.orm !== undefined ? d.orm : 99;
    if (!(dir < 0 && orm < 30)) {                  // nie unter die Vorschrift ziehen
      for (let i = 0; i < s.rodDmd.length; i++) {
        s.rodDmd[i] = Math.max(0, Math.min(1, s.rodDmd[i] + dir * 2e-5));
      }
    }
  }
}

console.log('Szenario             Ausgang              Punkte  T_cl_max  cont  zerstoert  Grund');
console.log('-'.repeat(92));
let won = 0;
for (const n of names) {
  const def = JSON.parse(await readFile(new URL(n, DIR), 'utf8'));
  const e = createEngine(getPlant(def.reactor), { n: 1.0, seed: def.seed, cold: !!def.cold });
  const ses = new Session(e, def);
  ses.start();
  const s = e.state;
  let out = null, score = null;
  ses.onEnd = (r, f) => { out = f || 'GESCHAFFT'; score = r ? r.score : null; };
  let cladmax = 0, cmax = 0;
  for (let i = 0; i < Math.round((def.duration_s + 5) / DT) && !out; i++) {
    let worst = 0;
    for (const t of e.trips.tiles()) {
      if ((t.tile === 'new' || t.tile === 'ack') && t.severity > worst) worst = t.severity;
    }
    operate(e, s, worst);
    e.step(DT);
    ses.step(DT, worst, e.trips.unacknowledgedSeconds());
    cladmax = Math.max(cladmax, s.T_cl); cmax = Math.max(cmax, s.pCont || 0);
  }
  if (out === 'GESCHAFFT') won++;
  console.log([def.id.padEnd(20), String(out).padEnd(20), String(score).padStart(6),
    (cladmax - 273).toFixed(0).padStart(9), (cmax).toFixed(1).padStart(5),
    String(s.destroyed).padStart(10), String(s.destroyedKey || '-')].join(' '));
}
console.log('-'.repeat(92));
console.log(`Mit vernuenftiger Bedienung bestanden: ${won} von ${names.length}`);
