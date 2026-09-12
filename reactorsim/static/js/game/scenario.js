// Szenarien: Bedarfskurve, geplante Störungen, Ziele, Fehlbedingungen.
//
// Ein Szenario ist eine Datendatei, kein Code. Was darin steht, ist entweder
// eine Zahl oder ein Übersetzungsschlüssel -- Klartext gibt es nicht, sonst
// wäre das Spiel einsprachig.

import { Rng } from '../rng.js';
import { clamp } from '../sim/constants.js';

/**
 * Wert einer stückweise linearen Kurve. Stützstellen sind {t, mw}; zwischen
 * zwei Punkten wird interpoliert, wenn der zweite `ramp: "linear"` trägt,
 * sonst wird der alte Wert bis dahin gehalten (Stufe).
 */
export function demandAt(points, t) {
  if (!points || !points.length) return 0;
  if (t <= points[0].t) return points[0].mw;
  for (let i = 1; i < points.length; i++) {
    if (t <= points[i].t) {
      const a = points[i - 1];
      const b = points[i];
      if (b.ramp !== 'linear') return a.mw;
      const f = (t - a.t) / Math.max(b.t - a.t, 1e-9);
      return a.mw + (b.mw - a.mw) * f;
    }
  }
  return points[points.length - 1].mw;
}

/** "rand(a,b)" wird über den Startwert des Szenarios aufgelöst, nie über
 *  Math.random -- sonst wäre derselbe Lauf nicht zweimal derselbe. */
function resolveTime(value, rng) {
  if (typeof value === 'number') return value;
  const m = /^rand\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)$/.exec(String(value));
  if (!m) return 0;
  return rng.range(Number(m[1]), Number(m[2]));
}

export class Scenario {
  /** @param {object} def geladene JSON-Definition */
  constructor(def) {
    this.def = def;
    this.rng = new Rng(def.seed || 1);
    this.events = (def.events || [])
      .map((e) => ({ ...e, t: resolveTime(e.t, this.rng), fired: false }))
      .sort((a, b) => a.t - b.t);
    // Akustische Vorwarnung: 2-5 Minuten vor jedem Ereignis, einmalig, aus
    // demselben Seed wie die Ereignisse selbst -- derselbe Lauf klingt bei
    // gleichem Seed immer gleich.
    for (const e of this.events) {
      e.alertAt = Math.max(0, e.t - this.rng.range(120, 300));
      e.alertFired = false;
    }
    this.duration = def.duration_s || 3600;
    this.demand = def.demand || [];
    this.tolerance = (def.grid && def.grid.tolerance_mw) || 50;
  }

  get id() { return this.def.id; }
  get reactor() { return this.def.reactor; }
  get titleKey() { return this.def.title_key; }
  get briefKey() { return this.def.brief_key; }
  get difficulty() { return this.def.difficulty || 1; }
  get cold() { return !!this.def.cold; }

  demandAt(t) { return demandAt(this.demand, t); }

  /** Fällige Störungen herausgeben. Der Aufrufer löst sie aus. */
  due(t) {
    const out = [];
    for (const e of this.events) {
      if (!e.fired && t >= e.t) { e.fired = true; out.push(e); }
    }
    return out;
  }

  /** Fällige akustische Vorwarnungen -- je Ereignis einmal, 2-5 Minuten davor. */
  dueAlerts(t) {
    const out = [];
    for (const e of this.events) {
      if (!e.alertFired && t >= e.alertAt) { e.alertFired = true; out.push(e); }
    }
    return out;
  }

  /** Nächste Störung, die noch aussteht -- für die Vorwarnung im Briefing. */
  next(t) {
    for (const e of this.events) if (!e.fired && e.t > t) return e;
    return null;
  }
}

/**
 * Fortschritt eines Laufs. Sammelt Kennzahlen, keine Punkte -- gewertet wird
 * erst am Ende, und zwar an einer Stelle (game/scoring.js), damit Client und
 * Server dieselbe Formel benutzen können.
 */
export class RunState {
  constructor(scenario, spec) {
    this.scenario = scenario;
    this.P0_e = spec.P0_e;
    this.energyDelivered = 0;    // MWh
    this.energyDemanded = 0;     // MWh
    this.deviationMWh = 0;       // ∫|P_e − P_soll| dt
    this.violationSeconds = { 1: 0, 2: 0, 3: 0 };
    this.scramCount = 0;
    this.maxFuelK = 0;
    this.minDnbr = Infinity;
    this.minOrm = Infinity;
    this.destroyed = false;
    this.completed = false;
    this.failed = null;
    this.scramSeen = false;
  }

  /** Ein Rechenschritt an Kennzahlen. */
  accumulate(s, d, worstSeverity, dt) {
    const h = dt / 3600;
    const demand = this.scenario.demandAt(s.t_sim);
    this.energyDelivered += s.P_e * h;
    this.energyDemanded += demand * h;
    const dev = Math.abs(s.P_e - demand);
    if (dev > this.scenario.tolerance) this.deviationMWh += (dev - this.scenario.tolerance) * h;
    if (worstSeverity > 0) this.violationSeconds[worstSeverity] += dt;
    if (s.T_f > this.maxFuelK) this.maxFuelK = s.T_f;
    if (Number.isFinite(d.dnbr) && d.dnbr < this.minDnbr) this.minDnbr = d.dnbr;
    if (Number.isFinite(d.orm) && d.orm < this.minOrm) this.minOrm = d.orm;
    if (s.scram.active && !this.scramSeen) { this.scramSeen = true; this.scramCount++; }
    if (!s.scram.active) this.scramSeen = false;
    if (s.destroyed) this.destroyed = true;
  }

  /** Prüft die Fehlbedingungen des Szenarios. @returns {string|null} */
  checkFail(s, d) {
    if (this.failed) return this.failed;
    for (const f of this.scenario.def.fail || []) {
      if (f.if === 'difficulty>=3' && this.scenario.difficulty < 3) continue;
      if (f.type === 'fuel_damage' && s.destroyed) return (this.failed = 'fail_fuel_damage');
      if (f.type === 'scram' && s.scram.active) return (this.failed = 'fail_scram');
      if (f.type === 'grid_deviation') {
        const dev = Math.abs(s.P_e - this.scenario.demandAt(s.t_sim));
        if (dev > f.mw) {
          this._devFor = (this._devFor || 0) + 0.05;
          if (this._devFor > (f.for_s || 60)) return (this.failed = 'fail_grid_deviation');
        } else this._devFor = 0;
      }
    }
    return null;
  }

  /** Zusammenfassung für die Wertung. Bewusst nur Kennzahlen. */
  summary(s) {
    return {
      reactor: s.reactor,
      scenario: this.scenario.id,
      difficulty: this.scenario.difficulty,
      energy_mwh_delivered: round(this.energyDelivered, 2),
      energy_mwh_demanded: round(this.energyDemanded, 2),
      deviation_mwh: round(this.deviationMWh, 3),
      violation_seconds: {
        1: round(this.violationSeconds[1], 1),
        2: round(this.violationSeconds[2], 1),
        3: round(this.violationSeconds[3], 1),
      },
      alarm_seconds_unacked: 0,   // wird vom Aufrufer gesetzt
      scram_count: this.scramCount,
      fuel_damage: this.destroyed,
      max_fuel_c: round(this.maxFuelK - 273.15, 1),
      min_dnbr: Number.isFinite(this.minDnbr) ? round(this.minDnbr, 3) : null,
      min_orm: Number.isFinite(this.minOrm) ? round(this.minOrm, 1) : null,
      duration_s: round(s.t_sim, 1),
      completed: this.completed,
      failed: this.failed,
    };
  }
}

const round = (v, d) => Math.round(v * 10 ** d) / 10 ** d;

export { clamp };
