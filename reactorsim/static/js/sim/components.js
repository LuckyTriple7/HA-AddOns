// Wiederverwendbare Anlagenbausteine.
//
// Hier liegt, was alle drei Reaktortypen gemeinsam haben: Wärmeknoten,
// Transportstrecken, Pumpen, Ventile, Regler. Die Typdateien setzen daraus
// ihren Kreislauf zusammen. Wandert etwas davon in eine Typdatei, ist die
// Abstraktion undicht -- dann gehört es hierher.
//
// Alle Knoten erster Ordnung nutzen die exakte Exponentialform aus
// constants.relax(). Das ist keine Bequemlichkeit, sondern der Grund, warum
// in dieser Simulation keine Temperatur und kein Druck davonlaufen kann:
// unbedingt stabil, und exakt für eine über den Schritt konstante Quelle.

import { relax, clamp } from './constants.js';

/** Wärmeknoten mit Masse und spezifischer Wärme.
 *  C = m·c_p in kJ/K, Leistungen in kW, Temperaturen in Kelvin. */
export class ThermalNode {
  /** @param {number} C Wärmekapazität kJ/K @param {number} T0 Starttemperatur K */
  constructor(C, T0) {
    this.C = C;
    this.T = T0;
  }

  /**
   * Ein Schritt mit Zufuhr und Abfuhr.
   * @param {number} qIn   zugeführte Leistung in kW
   * @param {number} UA    Wärmedurchgang zur Senke in kW/K
   * @param {number} Tsink Temperatur der Senke in K
   */
  step(qIn, UA, Tsink, dt) {
    if (UA > 0) {
      // Gleichgewicht: qIn = UA·(T − T_senke)
      const Tss = Tsink + qIn / UA;
      const tau = this.C / UA;
      this.T = relax(this.T, Tss, dt, tau);
    } else {
      this.T += (qIn * dt) / this.C;
    }
    return this.T;
  }
}

/**
 * Transportverzögerung als Ringpuffer.
 *
 * Ein heißer Strang ist keine Zeitkonstante, sondern eine Laufzeit: was am
 * Kernaustritt passiert, erreicht den Dampferzeuger drei Sekunden später --
 * unverformt. Ein zusätzlicher Temperaturknoten würde daraus eine Glättung
 * machen und die Phase der Kreislaufschwingung verfälschen. Der Ringpuffer
 * kostet dafür fast nichts.
 */
export class TransportDelay {
  /** @param {number} tau Laufzeit in s @param {number} dt Schrittweite @param {number} fill Startwert */
  constructor(tau, dt, fill) {
    this.n = Math.max(1, Math.round(tau / dt));
    this.buf = new Float64Array(this.n).fill(fill);
    this.i = 0;
  }

  /** Neuen Wert einschieben, den um tau älteren herausnehmen. */
  push(value) {
    const out = this.buf[this.i];
    this.buf[this.i] = value;
    this.i = (this.i + 1) % this.n;
    return out;
  }

  peek() { return this.buf[this.i]; }

  fill(value) { this.buf.fill(value); }

  snapshot() { return { buf: Array.from(this.buf), i: this.i }; }
  restore(d) {
    if (Array.isArray(d.buf) && d.buf.length === this.buf.length) this.buf.set(d.buf);
    if (Number.isInteger(d.i) && d.i >= 0 && d.i < this.n) this.i = d.i;
  }
}

/**
 * Pumpe mit Auslauf.
 *
 * Fällt der Antrieb aus, bleibt die Pumpe nicht stehen -- das Schwungrad
 * treibt sie weiter, und der Durchsatz fällt mit der Zeitkonstanten des
 * Auslaufs. Genau dieser Auslauf hält den Kern in den ersten Sekunden nach
 * einem Ausfall kühl und entscheidet mit darüber, ob eine Störung glimpflich
 * endet.
 */
export class Pump {
  /**
   * @param {object} o
   * @param {number} o.W0        Nenndurchsatz kg/s
   * @param {number} o.coastTau  Auslaufzeitkonstante s
   * @param {number} o.rampTau   Zeitkonstante beim Hochlaufen s
   */
  constructor({ W0, coastTau = 12, rampTau = 4 }) {
    this.W0 = W0;
    this.coastTau = coastTau;
    this.rampTau = rampTau;
    this.speed = 1;        // 0..1,1 -- Anteil der Nenndrehzahl
    this.demand = 1;
    this.running = true;
    this.tripped = false;
  }

  trip() { this.tripped = true; this.running = false; this.demand = 0; }
  start() { this.tripped = false; this.running = true; this.demand = 1; }

  /** Betriebszustand fuer den Spielstand -- siehe net/persist.js. W0/coastTau/
   *  rampTau sind Anlagendaten, kein Zustand, und stehen deshalb nicht drin. */
  snapshot() { return { running: this.running, tripped: this.tripped, speed: this.speed, demand: this.demand }; }
  restore(d) {
    this.running = !!d.running;
    this.tripped = !!d.tripped;
    this.speed = Number.isFinite(d.speed) ? d.speed : this.speed;
    this.demand = Number.isFinite(d.demand) ? d.demand : this.demand;
  }

  step(dt) {
    const target = this.running ? this.demand : 0;
    const tau = target < this.speed ? this.coastTau : this.rampTau;
    this.speed = relax(this.speed, target, dt, tau);
    if (this.speed < 1e-4) this.speed = 0;
    return this.speed;
  }

  /** Förderstrom. Der Naturumlauf bleibt IMMER als Sockel -- ob nach einem
   *  Ausfall, oder weil die Pumpe (Kaltstart) noch nie lief. Ohne ihn ginge
   *  die Kernkühlung in beiden Fällen rechnerisch auf null, was falsch ist. */
  flow(naturalCirc = 0.05) {
    return this.W0 * Math.max(this.speed, naturalCirc);
  }

  get state() { return this.tripped ? 'tripped' : (this.speed > 0.05 ? 'run' : 'stopped'); }
}

/** Pumpen fuer einen Kaltstart abschalten: der Konstruktor faengt immer bei
 *  Volldrehzahl an (Normalfall ist Vollastbetrieb). Bewusst trip() NICHT
 *  benutzt -- das waere fuer die Anzeige ein Stoerungsauslauf (rot,
 *  "tripped"), hier soll es schlicht "steht, nie gestartet" heissen (grau,
 *  "stopped"). Der Spieler startet sie ueber denselben Knopf wie sonst
 *  einen ausgefallenen Pumpe (togglePump ruft dafuer .start()). flow()
 *  liefert trotzdem den Naturumlauf-Sockel weiter, kein Nullstrom. */
export function coldStopPumps(pumps) {
  for (const p of [].concat(pumps)) { p.running = false; p.speed = 0; }
}

/**
 * Ventil mit Hubratenbegrenzung.
 *
 * Ein Ventil, das in einem Rechenschritt von zu auf offen springt, macht den
 * angeschlossenen Druckknoten steif und die Rechnung zappelig. Die Begrenzung
 * ist aber ohnehin physikalisch: ein Frischdampf-Regelventil braucht Sekunden,
 * eine Umleitstation Bruchteile davon. Hier fällt physikalisch richtig und
 * numerisch gutmütig zusammen.
 */
export class Valve {
  /** @param {number} strokeS volle Fahrt von zu nach offen in s */
  constructor(strokeS = 3, position = 0) {
    this.rate = 1 / Math.max(strokeS, 0.05);
    this.pos = position;
    this.demand = position;
  }

  step(dt) {
    const d = clamp(this.demand, 0, 1) - this.pos;
    const max = this.rate * dt;
    this.pos += clamp(d, -max, max);
    this.pos = clamp(this.pos, 0, 1);
    return this.pos;
  }

  /** Durchfluss nach der Ventilgleichung: W = Cv·pos·√(ρ·Δp). */
  flow(Cv, rho, dp) {
    if (!(dp > 0)) return 0;
    return Cv * this.pos * Math.sqrt(rho * dp);
  }

  snapshot() { return { pos: this.pos, demand: this.demand }; }
  restore(d) {
    if (Number.isFinite(d.pos)) this.pos = clamp(d.pos, 0, 1);
    if (Number.isFinite(d.demand)) this.demand = d.demand;
  }
}

/**
 * PI-Regler mit Stellbegrenzung und Windup-Schutz.
 *
 * Ohne Windup-Schutz läuft der I-Anteil weiter, während der Stellwert schon
 * am Anschlag steht -- nach einer Störung fährt der Regler dann erst minutenlang
 * zurück, bevor überhaupt etwas passiert. In einer Anlage, die man von Hand
 * übernehmen können soll, ist das inakzeptabel.
 */
export class PI {
  constructor({ kp, ki, min = 0, max = 1, out = 0 }) {
    this.kp = kp;
    this.ki = ki;
    this.min = min;
    this.max = max;
    this.i = out;
    this.out = out;
  }

  step(error, dt) {
    const p = this.kp * error;
    const i = this.i + this.ki * error * dt;
    const raw = p + i;
    if (raw > this.max) {
      // Am Anschlag den I-Anteil stehen lassen, statt ihn weiter aufzuladen.
      this.out = this.max;
    } else if (raw < this.min) {
      this.out = this.min;
    } else {
      this.i = i;
      this.out = raw;
    }
    return this.out;
  }

  /** Stoßfreie Übernahme aus dem Handbetrieb. */
  preset(out) { this.i = clamp(out, this.min, this.max); this.out = this.i; }

  snapshot() { return { i: this.i, out: this.out }; }
  restore(d) {
    if (Number.isFinite(d.i)) this.i = clamp(d.i, this.min, this.max);
    if (Number.isFinite(d.out)) this.out = clamp(d.out, this.min, this.max);
  }
}

/** Verzögerung erster Ordnung -- für Messwerte, Mischvorgänge, Rückkopplungen,
 *  die sonst algebraische Schleifen bilden würden. */
export class Lag {
  constructor(tau, value = 0) { this.tau = tau; this.v = value; }
  step(target, dt) { this.v = relax(this.v, target, dt, this.tau); return this.v; }
  set(value) { this.v = value; }
  snapshot() { return { v: this.v }; }
  restore(d) { if (Number.isFinite(d.v)) this.v = d.v; }
}

/** Begrenzt die Änderungsrate eines Sollwerts (Einheiten je Sekunde). */
export class RateLimiter {
  constructor(rate, value = 0) { this.rate = rate; this.v = value; }
  step(target, dt) {
    const max = this.rate * dt;
    this.v += clamp(target - this.v, -max, max);
    return this.v;
  }
  snapshot() { return { v: this.v }; }
  restore(d) { if (Number.isFinite(d.v)) this.v = d.v; }
}
