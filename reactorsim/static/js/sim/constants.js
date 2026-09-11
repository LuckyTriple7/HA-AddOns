// Physikalische Konstanten und Einheitenhelfer.
//
// Alle Reaktivitäten laufen intern in Δk/k. Angezeigt werden sie in pcm
// (1 pcm = 1e-5) oder in Dollar (ρ/β_eff) -- umgerechnet wird erst in der
// Oberfläche, nie in der Rechnung.

// ── Verzögerte Neutronen (U-235, thermisch) ──────────────────────────────────
// Sechs Gruppen. Die Anteile werden als Form gespeichert und mit dem β_eff des
// jeweiligen Reaktortyps skaliert -- ein RBMK hat dieselbe Gruppenstruktur,
// aber ein kleineres β_eff als ein frischer Druckwasserkern.

export const BETA_I_U235 = [2.15e-4, 1.424e-3, 1.274e-3, 2.568e-3, 7.48e-4, 2.73e-4];
export const LAMBDA_I = [0.0124, 0.0305, 0.111, 0.301, 1.14, 3.01]; // 1/s

export const BETA_SUM_U235 = BETA_I_U235.reduce((a, b) => a + b, 0); // 0,006502
/** Normierte Gruppenanteile, Summe exakt 1. */
export const BETA_FRAC = BETA_I_U235.map((b) => b / BETA_SUM_U235);
export const NGROUPS = 6;

/** Quellterm, normiert wie n (Anteil der Nennleistung je Sekunde).
 *
 *  Ohne ihn gäbe es im unterkritischen Kern keine Anzeige im Quellbereich und
 *  kein Anfahren aus dem Stillstand. Die Größe folgt aus dem gewünschten
 *  Anzeigewert: im stationären unterkritischen Zustand gilt n = −S·Λ/ρ, also
 *  bei −1000 pcm und Λ = 2e-5 rund 2e-9 der Nennleistung. Das entspricht der
 *  Größenordnung eines echten Quellbereichskanals. */
export const SOURCE = 1e-6;

// ── Xenon-135 / Jod-135 ──────────────────────────────────────────────────────
// Gerechnet wird in Vielfachen des Volllast-Gleichgewichts (I* = X* = 1 bei
// 100 % Dauerleistung), nicht in Kernen je cm³. Das kürzt Σ_f und φ aus den
// Gleichungen heraus; übrig bleiben die Zerfallskonstanten und das Verhältnis
// von Abbrand zu Zerfall -- und genau dieses Verhältnis bestimmt die Höhe der
// Jod-Grube nach einer Abschaltung.

export const LAMBDA_I135 = 2.87e-5;  // 1/s, Halbwertszeit 6,57 h
export const LAMBDA_XE = 2.09e-5;    // 1/s, Halbwertszeit 9,17 h
export const GAMMA_I = 0.0639;       // Spaltausbeute Jod-135
export const GAMMA_XE = 0.00237;     // direkte Spaltausbeute Xenon-135
/** σ_Xe · φ bei Volllast. Rund viermal so groß wie λ_Xe -- deshalb brennt
 *  Xenon im Betrieb schneller ab als es zerfällt, und deshalb steigt es nach
 *  einer Abschaltung erst einmal an. */
export const SIGMA_XE_PHI100 = 7.95e-5; // 1/s

// ── Samarium-149 (über Promethium-149) ───────────────────────────────────────
export const LAMBDA_PM = 3.63e-6;      // 1/s, Halbwertszeit 53,1 h
export const SIGMA_SM_PHI100 = 1.2e-6; // 1/s

// ── Nachzerfallswärme ────────────────────────────────────────────────────────
// Way-Wigner (t^-0.2) braucht die gesamte Leistungsgeschichte und ist bei t=0
// singulär -- für eine laufende Simulation die falsche Form. Vier exponentielle
// Pseudogruppen bilden denselben Verlauf über fünf Zehnerpotenzen nach und
// tragen ihre Geschichte im eigenen Zustand.
export const DECAY_F = [0.030, 0.020, 0.013, 0.007];      // Anteil an P0
export const DECAY_L = [0.2, 0.01, 5e-4, 1e-5];           // 1/s
export const DECAY_SUM = DECAY_F.reduce((a, b) => a + b, 0); // 0,070
/** Anteil der Leistung, der prompt aus der Spaltung kommt. Der Rest ist
 *  Nachzerfallswärme -- sonst wären es im stationären Betrieb 107 %. */
export const PROMPT_FRACTION = 1 - DECAY_SUM;

// ── Umrechnungen ─────────────────────────────────────────────────────────────

export const K0 = 273.15;
export const toC = (kelvin) => kelvin - K0;
export const toK = (celsius) => celsius + K0;

/** Δk/k → pcm */
export const pcm = (rho) => rho * 1e5;
/** Δk/k → Dollar */
export const dollars = (rho, beta) => rho / beta;

export function clamp(x, lo, hi) {
  return x < lo ? lo : (x > hi ? hi : x);
}

/** Exakte Aktualisierung eines Knotens erster Ordnung:
 *  x' = (x_ss − x)/τ  →  x ← x_ss + (x − x_ss)·e^(−dt/τ)
 *  Unbedingt stabil, exakt für ein über den Schritt konstantes x_ss. Genau
 *  deshalb kann in dieser Simulation kein Wärmeknoten davonlaufen. */
export function relax(x, xSteady, dt, tau) {
  if (!(tau > 0)) return xSteady;
  const k = Math.exp(-dt / tau);
  return xSteady + (x - xSteady) * k;
}

/** Wie relax(), aber mit Zerfallsrate statt Zeitkonstante:
 *  x' = source − k·x */
export function relaxRate(x, source, k, dt) {
  if (!(k > 0)) return x + source * dt;
  const xs = source / k;
  return xs + (x - xs) * Math.exp(-k * dt);
}
