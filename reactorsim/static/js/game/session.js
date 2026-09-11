// Ablauf eines Laufs: Auswahl → Einweisung → Betrieb → Auswertung.
//
// Die Sitzung kennt die Oberfläche nicht. Sie meldet Zustandswechsel über
// Rückrufe, damit main.js entscheidet, was angezeigt wird.

import { Scenario, RunState } from './scenario.js';
import { getEvent, eventKey, eventSeverity, stepEvents } from './events.js';
import { score } from './scoring.js';

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
    this.result = null;
  }

  start() {
    this.phase = PHASE.RUNNING;
    if (this.scenario) {
      const st = this.scenario.def.start_overrides || {};
      for (const [k, v] of Object.entries(st)) this.engine.state[k] = v;
      this.engine.state.P_demand = this.scenario.demandAt(0);
    }
  }

  /** Ein Rechenschritt. Wird aus der Schleife gerufen, nach engine.step(). */
  step(dt, worstSeverity, unackedSeconds) {
    if (this.phase !== PHASE.RUNNING) return;
    const s = this.engine.state;
    stepEvents(this.engine, dt);

    if (!this.scenario) {
      if (s.destroyed) this._finish(false, 'fail_fuel_damage');
      return;
    }

    // Bedarfskurve führt die Lastanforderung.
    s.P_demand = this.scenario.demandAt(s.t_sim);

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
