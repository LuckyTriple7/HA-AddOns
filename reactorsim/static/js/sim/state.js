// Zustandsvektor.
//
// Bewusst ein einfaches Objekt und keine getarnte Float64Array mit
// Namenszugriffen: die Lesbarkeit im Rest der Engine wiegt schwerer als ein
// paar Nanosekunden je Schritt, und bei rund sechzig Skalaren und 20 Schritten
// je Bild ist die Kopie ohnehin nicht der Engpass. Die Gruppenfelder (c, D)
// sind Float64Array, weil sie in Schleifen laufen.
//
// Was hier NICHT steht, ist genauso wichtig: abgeleitete Größen wie thermische
// Leistung, mittlere Temperatur, Periode oder DNBR werden je Bild gerechnet und
// nie gespeichert. Gespeicherte Ableitungen laufen früher oder später gegen den
// Zustand, aus dem sie stammen.

import { NGROUPS } from './constants.js';
import { equilibriumPrecursors } from './kinetics.js';
import { equilibriumDecay, NDECAY } from './decayheat.js';
import { equilibriumPoisons } from './poisons.js';

/** Plausible Bereiche. Verlässt ein Wert sie, ist das ein Fehler in der
 *  Rechnung -- die Engine hält an und meldet, statt NaN in die Anzeige zu
 *  schieben. Die Grenzen sind absichtlich weit: sie fangen Rechenfehler, nicht
 *  Betriebszustände. */
export const RANGES = {
  n: [0, 1e6],
  T_f: [250, 6000],
  T_cl: [250, 4000],
  // Bis 1000 K reichte, solange kein Typ die Kuehlmitteltemperatur ueber
  // normale Transienten hinaus brauchte. Der Siedewasserreaktor tut das jetzt
  // bei Kernfreilegung: die Dampfkuehlung dort erreicht huellrohraehnliche
  // Temperaturen (siehe bwr.js coreCoolant()), und 1000 K haette genau diesen
  // Fall als "Rechenfehler" geklemmt statt ihn zuzulassen.
  T_ci: [250, 4000],
  T_co: [250, 4000],
  T_mod: [250, 4000],
  T_gr: [250, 2000],
  W_core: [0, 1e6],
  p_prim: [0.01, 300],
  I: [0, 100],
  X: [0, 100],
  Pm: [0, 100],
  Sm: [0, 100],
  C_B: [0, 5000],
  alphaBar: [0, 1],
};

export function createState(spec, opts = {}) {
  const n = opts.n !== undefined ? opts.n : 1.0;
  const kin = opts.kin;

  const banks = spec.rodBanks || [];
  const rod = new Float64Array(banks.length);
  const rodDmd = new Float64Array(banks.length);
  for (let i = 0; i < banks.length; i++) {
    const h = opts.rod && opts.rod[i] !== undefined ? opts.rod[i] : (banks[i].initial || 0);
    rod[i] = h;
    rodDmd[i] = h;
  }

  const poisons = equilibriumPoisons(opts.poisonPower !== undefined ? opts.poisonPower : n);

  const s = {
    // Kennung
    reactor: spec.id,
    t_sim: 0,

    // Kinetik
    n,
    c: kin ? equilibriumPrecursors(kin, n) : new Float64Array(NGROUPS),
    D: equilibriumDecay(n),

    // Temperaturen (alle in Kelvin -- Grad Celsius erst in der Anzeige)
    T_f: 900,
    T_cl: 600,
    T_ci: 564,
    T_co: 599,
    T_mod: 578,
    T_gr: 800,

    // Hydraulik
    W_core: spec.coolant ? spec.coolant.W0 : 0,
    p_prim: spec.coolant ? spec.coolant.p0 : 70,
    alphaBar: 0,

    // Vergiftung und Chemie
    I: poisons.I,
    X: poisons.X,
    Pm: poisons.Pm,
    Sm: poisons.Sm,
    C_B: opts.C_B !== undefined ? opts.C_B : (spec.feedback ? spec.feedback.boron_ref_ppm || 0 : 0),
    burnup: opts.burnup !== undefined ? opts.burnup : 0,

    // Stäbe
    rod,
    rodDmd,

    // Leistung und Netz
    P_th: 0,
    P_e: 0,
    P_demand: spec.P0_e || 0,
    f_grid: 50.0,

    // Störungen, Auslösungen
    rho_ext: 0,
    scram: { active: false, t: 0, cause: null },
    promptCritical: false,
    enthalpy: 0,        // Brennstoffenthalpie in J/g
    enthalpyBase: 0,    // langsam nachgeführte Bezugslinie
    enthalpyRise: 0,    // Zuwachs gegenüber dem Betriebszustand
    destroyed: false,
    fault: null,     // gesetzt, wenn sanitize() etwas Unmögliches findet
  };

  return s;
}

/**
 * Nach jedem Schritt: Grenzen einhalten, Unmögliches melden.
 * @returns {boolean} true, wenn der Zustand brauchbar ist
 */
export function sanitize(s) {
  for (const [key, [lo, hi]] of Object.entries(RANGES)) {
    const v = s[key];
    if (v === undefined) continue;
    if (!Number.isFinite(v)) {
      s.fault = `${key} ist ${v}`;
      return false;
    }
    if (v < lo) s[key] = lo;
    else if (v > hi) s[key] = hi;
  }
  for (let i = 0; i < s.c.length; i++) {
    if (!Number.isFinite(s.c[i])) { s.fault = `c[${i}] ist ${s.c[i]}`; return false; }
    if (s.c[i] < 0) s.c[i] = 0;
  }
  for (let i = 0; i < s.D.length; i++) {
    if (!Number.isFinite(s.D[i])) { s.fault = `D[${i}] ist ${s.D[i]}`; return false; }
    if (s.D[i] < 0) s.D[i] = 0;
  }
  for (let i = 0; i < s.rod.length; i++) {
    s.rod[i] = s.rod[i] < 0 ? 0 : (s.rod[i] > 1 ? 1 : s.rod[i]);
  }
  return true;
}

/** Alle Zahlen in fester Reihenfolge -- Grundlage von Hash und Spielstand. */
export function numbers(s) {
  const out = [s.t_sim, s.n];
  for (let i = 0; i < s.c.length; i++) out.push(s.c[i]);
  for (let i = 0; i < s.D.length; i++) out.push(s.D[i]);
  out.push(s.T_f, s.T_cl, s.T_ci, s.T_co, s.T_mod, s.T_gr,
           s.W_core, s.p_prim, s.alphaBar,
           s.I, s.X, s.Pm, s.Sm, s.C_B, s.burnup,
           s.P_th, s.P_e, s.P_demand, s.f_grid, s.rho_ext, s.enthalpy, s.enthalpyBase);
  for (let i = 0; i < s.rod.length; i++) out.push(s.rod[i]);
  for (let i = 0; i < s.rodDmd.length; i++) out.push(s.rodDmd[i]);
  return out;
}

/**
 * Bitgenauer Hash über den Zustand (FNV-1a über die Rohbytes der Doubles).
 * Grundlage des Determinismustests: gleicher Startwert und gleiche Eingaben
 * müssen denselben Hash liefern, sonst sind Wiedergabe und spätere
 * serverseitige Nachrechnung eines Laufs nicht möglich.
 */
export function hash(s) {
  const arr = Float64Array.from(numbers(s));
  const bytes = new Uint8Array(arr.buffer);
  let h = 0x811c9dc5;
  for (let i = 0; i < bytes.length; i++) {
    h ^= bytes[i];
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}
