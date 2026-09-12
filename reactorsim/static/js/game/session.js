// Ablauf eines Laufs: Auswahl → Einweisung → Betrieb → Auswertung.
//
// Die Sitzung kennt die Oberfläche nicht. Sie meldet Zustandswechsel über
// Rückrufe, damit main.js entscheidet, was angezeigt wird.

import { Scenario, RunState } from './scenario.js';
import { getEvent, eventKey, eventSeverity, stepEvents } from './events.js';
import { score } from './scoring.js';
import { Rng } from '../rng.js';

// Freies Spiel ohne Bedarfskurve hiesse: "folge der Netzanforderung" waere
// nichts als "lass die Anforderung, wie sie ist" -- kein Unterschied zum
// Nichtstun. Ein Szenario hat feste Kennpunkte in der JSON-Datei; das freie
// Spiel bekommt stattdessen einen Zufallsspaziergang, neu gesät bei jedem
// Start (kein fester Seed wie im Szenario -- hier zaehlt keine Wertung, die
// Wiedergabe reproduzieren muesste).
const FREE_DEMAND_MIN_FRAC = 0.5;   // Untergrenze der Anforderung, Anteil P0_e
const FREE_DEMAND_MAX_FRAC = 1.0;   // Obergrenze
const FREE_DEMAND_INTERVAL_S = [300, 900];   // Abstand zwischen neuen Zielwerten
const FREE_DEMAND_RAMP_FRAC_PER_S = 0.002;   // maximale Aenderung je Sekunde, Anteil P0_e

export const PHASE = {
  BRIEFING: 'briefing',
  RUNNING: 'running',
  DEBRIEF: 'debrief',
};

export class Session {
  /**
   * @param {object} engine
   * @param {object} scenarioDef  geladene JSON-Definition, oder null für freies Spiel
   */
  constructor(engine, scenarioDef) {
    this.engine = engine;
    this.free = !scenarioDef;
    this.scenario = scenarioDef ? new Scenario(scenarioDef) : null;
    this.run = this.scenario ? new RunState(this.scenario, engine.spec) : null;
    this.phase = this.scenario ? PHASE.BRIEFING : PHASE.RUNNING;
    this.onEnd = null;
    this.onAlert = null;
    this.result = null;
    this.demandRng = this.free ? new Rng(Date.now() >>> 0) : null;
    this.demandTarget = null;
    this.demandNextChangeT = 0;
  }

  start() {
    this.phase = PHASE.RUNNING;
    if (this.scenario) {
      const st = this.scenario.def.start_overrides || {};
      for (const [k, v] of Object.entries(st)) this.engine.state[k] = v;
      this.engine.state.P_demand = this.scenario.demandAt(0);
    } else {
      // Erstes Ziel erst ein Stueck nach dem Start waehlen -- sonst zerrt die
      // Anforderung schon in der ersten Minute an einer Anlage, die gerade
      // erst in den Beharrungszustand gefahren ist.
      this.demandTarget = this.engine.state.P_demand;
      this.demandNextChangeT = this.demandRng.range(...FREE_DEMAND_INTERVAL_S);
    }
  }

  /** Freies Spiel: die Anforderung wandert langsam zu einem neuen Zufallsziel,
   *  nie sprunghaft -- ein realer Netzbetreiber ruft auch keine Stufenfunktion
   *  ab. */
  _stepFreeDemand(s, dt) {
    const p0 = this.engine.spec.P0_e;
    if (s.t_sim >= this.demandNextChangeT) {
      this.demandTarget = this.demandRng.range(FREE_DEMAND_MIN_FRAC, FREE_DEMAND_MAX_FRAC) * p0;
      this.demandNextChangeT = s.t_sim + this.demandRng.range(...FREE_DEMAND_INTERVAL_S);
    }
    const maxStep = FREE_DEMAND_RAMP_FRAC_PER_S * p0 * dt;
    const diff = this.demandTarget - s.P_demand;
    s.P_demand += Math.max(-maxStep, Math.min(maxStep, diff));
  }

  /** Ein Rechenschritt. Wird aus der Schleife gerufen, nach engine.step(). */
  step(dt, worstSeverity, unackedSeconds) {
    if (this.phase !== PHASE.RUNNING) return;
    const s = this.engine.state;
    stepEvents(this.engine, dt);

    if (!this.scenario) {
      this._stepFreeDemand(s, dt);
      if (s.destroyed) this._finish(false, 'fail_fuel_damage');
      return;
    }

    // Bedarfskurve führt die Lastanforderung.
    s.P_demand = this.scenario.demandAt(s.t_sim);

    // Akustische Vorwarnung, 2-5 Minuten vor dem eigentlichen Ereignis --
    // main.js entscheidet, welcher Klang das ist.
    if (this.scenario.dueAlerts(s.t_sim).length && this.onAlert) this.onAlert();

    for (const ev of this.scenario.due(s.t_sim)) {
      const def = getEvent(ev.id);
      if (def) {
        def.apply(this.engine, ev.args || {});
        this.engine.ctx.log.push({
          t: s.t_sim, key: eventKey(ev.id), severity: eventSeverity(ev.id), kind: 'on',
        });
      }
    }

    const d = this.engine.derive();
    this.run.accumulate(s, d, worstSeverity, dt);
    this.unacked = unackedSeconds;

    const failed = this.run.checkFail(s, d);
    if (failed) { this._finish(false, failed); return; }
    if (s.t_sim >= this.scenario.duration) { this._finish(true, null); }
  }

  _finish(completed, failed) {
    if (this.phase === PHASE.DEBRIEF) return;
    this.phase = PHASE.DEBRIEF;
    if (this.run) {
      this.run.completed = completed;
      this.run.failed = failed;
      const sum = this.run.summary(this.engine.state);
      sum.alarm_seconds_unacked = Math.round(this.unacked || 0);
      this.result = { summary: sum, ...score(sum) };
    }
    if (this.onEnd) this.onEnd(this.result, failed);
  }

  /** Vorzeitiger Abbruch durch den Spieler -- ohne Wertung. */
  abort() {
    this.phase = PHASE.DEBRIEF;
    this.result = null;
    if (this.onEnd) this.onEnd(null, 'aborted');
  }
}
