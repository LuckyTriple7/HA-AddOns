// Nachzerfallswärme in vier exponentiellen Pseudogruppen.
//
//   dD_j/dt = f_j·λ_j·n − λ_j·D_j        P_zerfall = Σ D_j
//
// Jede Gruppe strebt gegen f_j·n und folgt der Leistung mit ihrer eigenen
// Zeitkonstante -- 5 s, 100 s, 33 min, gut ein Tag. Zusammen bilden sie den
// t^-0.2-Verlauf über fünf Zehnerpotenzen nach, tragen die Leistungsgeschichte
// aber im eigenen Zustand statt in einem Integral über die Vergangenheit.
//
// ACHTUNG, die häufigste Verwechslung an dieser Stelle:
//     P_th = P0 · (PROMPT_FRACTION·n + Σ D_j)
// Nicht n + ΣD_j. Im stationären Volllastbetrieb ist ΣD_j = 0,070; ohne den
// Abzug käme die Anlage auf 107 % und jede Wärmebilanz wäre falsch.

import { DECAY_F, DECAY_L, relax } from './constants.js';

export const NDECAY = DECAY_F.length;

/** Gleichgewicht zu einer Dauerleistung. */
export function equilibriumDecay(n) {
  const D = new Float64Array(NDECAY);
  for (let j = 0; j < NDECAY; j++) D[j] = DECAY_F[j] * n;
  return D;
}

/**
 * @param {Float64Array} D  vier Gruppen (wird verändert)
 * @param {number} n        relative neutronische Leistung
 * @param {number} dt       Sekunden
 * @returns {number} Nachzerfallswärme als Anteil der Nennleistung
 */
export function stepDecay(D, n, dt) {
  let sum = 0;
  for (let j = 0; j < NDECAY; j++) {
    D[j] = relax(D[j], DECAY_F[j] * n, dt, 1 / DECAY_L[j]);
    sum += D[j];
  }
  return sum;
}

export function decaySum(D) {
  let sum = 0;
  for (let j = 0; j < NDECAY; j++) sum += D[j];
  return sum;
}
