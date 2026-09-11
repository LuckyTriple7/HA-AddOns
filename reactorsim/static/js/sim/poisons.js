// Spaltprodukt-Vergiftung: Jod-135 → Xenon-135 und Promethium-149 → Samarium-149.
//
// Gerechnet in Vielfachen des Volllast-Gleichgewichts. I* = X* = 1 bedeutet
// „so viel wie nach langem Betrieb bei 100 %". Das kürzt Σ_f und φ heraus und
// lässt genau die Größen stehen, die das Spielverhalten bestimmen.
//
// Herleitung der Xenon-Gleichung in dieser Normierung:
//   dX/dt = γ_Xe·Σφ + λ_I·I − λ_Xe·X − σ_Xe·φ·X
// mit I_gl = γ_I·A/λ_I und X_gl = (γ_I+γ_Xe)·A/(λ_Xe+σφ₁₀₀) folgt
//   dX*/dt = (λ_Xe+σφ₁₀₀)/(γ_I+γ_Xe) · (γ_Xe·n + γ_I·I*) − (λ_Xe + σφ₁₀₀·n)·X*
// Probe bei n = I* = X* = 1: beide Terme sind (λ_Xe+σφ₁₀₀), die Ableitung ist
// null. Genau so muss es sein.
//
// Integriert wird mit der exakten Exponentialform des linearen Abbauterms,
// nicht mit explizitem Euler. Bei dt = 0,05 s wäre Euler zwar unkritisch
// (λ·dt ≈ 1e-6), aber der Abbrandterm σφ·n wächst mit der Leistung, und die
// exakte Form ist bei gleichem Aufwand für jedes dt stabil -- auch für die
// Xenon-Vorausschau, die mit Minutenschritten in die Zukunft rechnet.

import {
  LAMBDA_I135, LAMBDA_XE, GAMMA_I, GAMMA_XE, SIGMA_XE_PHI100,
  LAMBDA_PM, SIGMA_SM_PHI100, relaxRate,
} from './constants.js';

const GAMMA_SUM = GAMMA_I + GAMMA_XE;
const XE_K100 = LAMBDA_XE + SIGMA_XE_PHI100;

/**
 * Ein Zeitschritt der Vergiftung.
 * @param {{I:number, X:number, Pm:number, Sm:number}} p  Zustand (wird verändert)
 * @param {number} n   relative Leistung (0 = abgeschaltet, 1 = Volllast)
 * @param {number} dt  Sekunden
 */
export function stepPoisons(p, n, dt) {
  const flux = n < 0 ? 0 : n;

  // Jod: reine Produktion aus der Spaltung, reiner Zerfall. Strebt gegen n.
  p.I = relaxRate(p.I, LAMBDA_I135 * flux, LAMBDA_I135, dt);

  // Xenon: Quelle aus direkter Ausbeute und Jodzerfall, Senke aus Zerfall und
  // Neutroneneinfang. Der Einfang verschwindet mit der Leistung -- deshalb
  // steigt Xenon nach einer Abschaltung, obwohl nichts mehr nachproduziert wird.
  const src = (XE_K100 / GAMMA_SUM) * (GAMMA_XE * flux + GAMMA_I * p.I);
  const k = LAMBDA_XE + SIGMA_XE_PHI100 * flux;
  p.X = relaxRate(p.X, src, k, dt);

  // Promethium/Samarium. Samarium zerfällt praktisch nicht; es verschwindet nur
  // durch Einfang. Nach einer Abschaltung wächst es auf einen neuen, höheren
  // Wert und bleibt dort -- anders als Xenon geht es nicht von selbst weg.
  p.Pm = relaxRate(p.Pm, LAMBDA_PM * flux, LAMBDA_PM, dt);
  p.Sm = relaxRate(p.Sm, SIGMA_SM_PHI100 * p.Pm, SIGMA_SM_PHI100 * flux, dt);
}

/** Startwerte im Gleichgewicht zu einer Dauerleistung. */
export function equilibriumPoisons(n) {
  const flux = n < 0 ? 0 : n;
  const I = flux;
  const X = flux <= 0
    ? 0
    : (XE_K100 / GAMMA_SUM) * (GAMMA_XE * flux + GAMMA_I * I) / (LAMBDA_XE + SIGMA_XE_PHI100 * flux);
  return { I, X, Pm: flux, Sm: flux > 0 ? 1 : 0 };
}

/**
 * Xenon-Vorausschau: wo steht die Vergiftung in `horizonS` Sekunden, wenn die
 * Leistung so bleibt wie jetzt? Damit zeigt das Chemie-Panel die Jod-Grube an,
 * bevor der Spieler in ihr sitzt. Läuft außerhalb des Rechentakts mit großen
 * Schritten -- die exakte Exponentialform verträgt das.
 *
 * @returns {{t:number, X:number}[]} Stützstellen relativ zu jetzt
 */
export function forecastXenon(p, n, horizonS = 24 * 3600, stepS = 300) {
  const work = { I: p.I, X: p.X, Pm: p.Pm, Sm: p.Sm };
  const out = [{ t: 0, X: work.X }];
  // Innen feiner rechnen als außen ausgegeben wird: die Xenon-Quelle ist der
  // zerfallende Jodbestand und ändert sich während eines 5-Minuten-Schritts
  // spürbar. Mit 30 s bleibt die Vorausschau auf ein Promille bei der
  // schrittweisen Rechnung -- sonst zeigt die Kurve im Panel eine andere Grube
  // als die, in die der Spieler tatsächlich fährt.
  const inner = 30;
  for (let t = stepS; t <= horizonS; t += stepS) {
    let done = 0;
    while (done < stepS) {
      const h = Math.min(inner, stepS - done);
      stepPoisons(work, n, h);
      done += h;
    }
    out.push({ t, X: work.X });
  }
  return out;
}
