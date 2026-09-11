// Anlagenregler.
//
// Alle laufen im Untertakt von 0,2 s, nicht bei jedem Rechenschritt -- so
// arbeitet eine echte digitale Leittechnik auch, und es hält die schnellen
// Stellglieder davon ab, dem Rechenraster hinterherzuzappeln.
//
// Jeder Regler kennt Automatik und Hand. Der Wechsel ist stoßfrei: beim
// Umschalten auf Automatik übernimmt der Regler den Stellwert, der gerade
// steht, statt auf seinen alten Integralstand zurückzuspringen.

import { PI, RateLimiter } from './components.js';
import { clamp } from './constants.js';

/**
 * Stabregelung auf die programmierte Mitteltemperatur.
 *
 * Der Sollwert der Kühlmittel-Mitteltemperatur steigt mit der Last -- das ist
 * das Temperaturprogramm. Es ist ein Kompromiss: konstante Mitteltemperatur
 * schont die Komponenten, konstanter Dampfdruck wäre der Turbine lieber, also
 * fährt man dazwischen. Weicht die Isttemperatur ab, fahren die Stäbe.
 *
 * Das Totband ist kein Schönheitsfehler, sondern Absicht: ohne es liefen die
 * Stäbe dauernd, und die differentielle Stabwirksamkeit würde den Kern über
 * den Tag schief fahren.
 */
export class RodController {
  constructor({ tAvgLow, tAvgHigh, deadbandK = 0.8, speed = 0.0125, bank = 0 }) {
    this.tAvgLow = tAvgLow;     // Sollwert bei 0 % Last, K
    this.tAvgHigh = tAvgHigh;   // Sollwert bei 100 % Last, K
    this.deadband = deadbandK;
    this.speed = speed;         // Anteil der Stablänge je Sekunde
    this.bank = bank;
    this.auto = true;
    this.manual = 0;            // −1 ziehen, 0 halten, +1 einfahren
  }

  setpoint(load) { return this.tAvgLow + (this.tAvgHigh - this.tAvgLow) * clamp(load, 0, 1); }

  /** @returns {number} gewünschte Änderung der Stabstellung in diesem Takt */
  step(tAvg, load, dt) {
    if (!this.auto) return this.manual * this.speed * dt;
    const err = tAvg - this.setpoint(load);
    if (Math.abs(err) < this.deadband) return 0;
    // Zu heiß heißt: zu viel Reaktivität, Stäbe einfahren.
    const dir = err > 0 ? 1 : -1;
    // Außerhalb des doppelten Totbands mit voller Geschwindigkeit, darin
    // gedrosselt -- so wie ein echter Stabantrieb zwei Fahrstufen hat.
    const fast = Math.abs(err) > 2 * this.deadband;
    return dir * this.speed * (fast ? 1 : 0.35) * dt;
  }
}

/**
 * Druckhalterregelung: Heizstäbe gegen fallenden, Sprühwasser gegen steigenden
 * Druck. Dazwischen ein totes Band, damit nicht beides gleichzeitig läuft --
 * Heizen und Sprühen im Wechsel wäre der schnellste Weg, den Druckhalter
 * kaputtzuregeln.
 */
export class PressurizerController {
  constructor({ pSet, heaterMaxKW, sprayBandBar = 1.5, heaterBandBar = 1.0 }) {
    this.pSet = pSet;
    this.heaterMax = heaterMaxKW;
    this.sprayBand = sprayBandBar;
    this.heaterBand = heaterBandBar;
    this.auto = true;
    this.heaterManual = 0;
    this.sprayManual = 0;
  }

  step(p) {
    if (!this.auto) {
      return { heater: this.heaterManual * this.heaterMax, spray: this.sprayManual };
    }
    const err = this.pSet - p;
    // Grundlast der Heizstäbe hält die Wärmeverluste und die Ausdampfung aus.
    let heater = 0.08;
    if (err > 0) heater = clamp(0.08 + err / this.heaterBand, 0, 1);
    const spray = err < 0 ? clamp(-err / this.sprayBand, 0, 1) : 0;
    return { heater: heater * this.heaterMax, spray };
  }
}

/**
 * Speisewasserregelung mit drei Größen: Füllstand, Dampfstrom, Speisestrom.
 *
 * Nur auf den Füllstand zu regeln funktioniert nicht, weil die Anzeige beim
 * Lastwechsel erst in die falsche Richtung geht (Schrumpfen und Quellen). Der
 * Dampfstrom als Vorsteuerung fängt das ab: steigt die Dampfentnahme, geht die
 * Speisung sofort mit, ohne auf den Füllstand zu warten.
 */
export class FeedwaterController {
  constructor({ levelSet, kp = 2.5, ki = 0.05, W0 }) {
    this.levelSet = levelSet;
    this.pi = new PI({ kp, ki, min: -0.4, max: 0.4, out: 0 });
    this.W0 = W0;
    this.auto = true;
    this.manual = 1;
    this.rate = new RateLimiter(0.25, 1);
  }

  /** @returns {number} Speisewasserdurchsatz in kg/s */
  step(level, steamFlow, dt) {
    if (!this.auto) return this.rate.step(this.manual, dt) * this.W0;
    const trim = this.pi.step(this.levelSet - level, dt);
    const target = clamp(steamFlow / this.W0 + trim, 0, 1.3);
    return this.rate.step(target, dt) * this.W0;
  }
}

/**
 * Turbinenregler.
 *
 * Zwei Betriebsarten. Im Lastbetrieb stellt das Regelventil die gewünschte
 * Generatorleistung ein. Im Druckbetrieb hält es stattdessen den Frischdampf-
 * druck konstant und lässt die Leistung folgen -- so fährt ein Siedewasser-
 * reaktor, bei dem die Leistung aus dem Kern kommt und nicht aus dem Ventil.
 */
export class GovernorController {
  /**
   * Vorsteuerung plus langsame Nachführung -- so arbeitet eine echte
   * Turbinenregelung auch.
   *
   * Der erste Entwurf regelte allein über einen PI auf die Leistungsabweichung.
   * Das ging schief, und zwar in beide Richtungen: mit vorsichtiger Auslegung
   * blieb bei 60 % Last eine Dauerabweichung von 5 % stehen, mit kräftiger
   * Auslegung entstand ein sauberer Grenzzyklus -- das Ventil sprang im
   * Sekundentakt zwischen 0,42 und 0,47, die Leistung zwischen 793 und 887 MW,
   * im Mittel genau richtig und in jedem Augenblick falsch.
   *
   * Der Grund ist die kleine Streckenverstärkung: mehr Ventilöffnung lässt
   * zwar mehr Dampf durch, senkt damit aber den Frischdampfdruck und die
   * Arbeit je Kilogramm. Ein Regler, der das allein über den Fehler aufholen
   * soll, braucht entweder viel Verstärkung (Grenzzyklus) oder viel Zeit
   * (Dauerabweichung). Die Vorsteuerung nimmt ihm die Arbeit ab: die grobe
   * Ventilstellung folgt direkt der Lastanforderung, der PI trimmt nur noch
   * den Rest und darf dafür klein und langsam bleiben.
   */
  constructor({ mode = 'load', pSet = 70, P0 = 1400, posNominal = 0.79,
                kp = 0.4, ki = 0.12, trim = 0.25 }) {
    this.mode = mode;
    this.pSet = pSet;
    this.P0 = P0;
    this.posNominal = posNominal;
    // Im Lastbetrieb trimmt der Regler nur die Vorsteuerung, im Druckbetrieb
    // stellt er das Ventil allein. Mit derselben schmalen Stellgrenze fuer
    // beide konnte das Ventil im Druckbetrieb nie unter 0,3 schliessen -- bei
    // kleiner Leistung lief die Anlage dann leer, der Trommeldruck fiel von
    // 69 auf 12 bar, und der Dampfblasenanteil im Kern stieg, obwohl die
    // Leistung sank.
    this.pi = mode === 'pressure'
      ? new PI({ kp, ki, min: 0, max: 1, out: posNominal })
      : new PI({ kp, ki, min: -trim, max: trim, out: 0 });
    this.auto = true;
    this.manual = posNominal;
    this.tripped = false;
  }

  /** @returns {number} Sollstellung des Regelventils 0..1 */
  step(P_e, P_demand, pSteam, dt) {
    if (this.tripped) return 0;
    if (!this.auto) return clamp(this.manual, 0, 1);
    if (this.mode === 'pressure') {
      // Druckbetrieb: das Ventil hält den Frischdampfdruck, die Leistung folgt
      // dem Kern. So fährt ein Siedewasserreaktor.
      return clamp(this.pi.step((pSteam - this.pSet) * 0.05, dt), 0, 1);
    }
    const ff = this.posNominal * clamp(P_demand / this.P0, 0, 1.1);
    // Fehler auf die Nennleistung normiert, nicht auf die Anforderung: sonst
    // wächst die Regelverstärkung bei kleiner Last ins Unangemessene.
    const err = (P_demand - P_e) / this.P0;
    return clamp(ff + this.pi.step(err, dt), 0, 1);
  }

  trip() { this.tripped = true; this.pi.preset(0); }

  /** Turbine wieder zuschalten. Der PI beginnt wieder bei null, nicht bei dem
   *  Wert von vor dem Trip -- sonst würde das Ventil im selben Augenblick auf
   *  eine Stellung springen, die mit der jetzigen Lage nichts zu tun hat. */
  resume() { this.tripped = false; this.pi.preset(0); }
}

/**
 * Leistungsregler auf die Stäbe.
 *
 * Der Druckwasserreaktor regelt die Stäbe auf eine Temperatur, weil die
 * Turbine dort die Leistung bestimmt. Wo der Kern selbst die Leistung macht --
 * beim RBMK -- muss ein Regler direkt auf die Leistung gehen. Das Original
 * hatte dafür eigene Regelstäbe.
 *
 * Ohne ihn treibt allein der Xenon-Abbrand die Anlage weg: ein Reaktor mit
 * schwachem Leistungskoeffizienten hat keinen Grund, von selbst auf seinem
 * Arbeitspunkt zu bleiben. Genau deshalb ist das Abschalten dieses Reglers im
 * Spiel eine Handlung mit Folgen und kein Schalter unter vielen.
 */
export class PowerController {
  constructor({ setpoint = 1, deadband = 0.004, speed = 0.005 }) {
    this.setpoint = setpoint;
    this.deadband = deadband;
    this.speed = speed;
    this.auto = true;
    this.manual = 0;
  }

  /** @returns {number} gewünschte Änderung der Stabstellung in diesem Takt */
  step(n, dt) {
    if (!this.auto) return this.manual * this.speed * dt;
    const err = n - this.setpoint;
    if (Math.abs(err) < this.deadband) return 0;
    const dir = err > 0 ? 1 : -1;
    const fast = Math.abs(err) > 4 * this.deadband;
    return dir * this.speed * (fast ? 1 : 0.3) * dt;
  }
}
