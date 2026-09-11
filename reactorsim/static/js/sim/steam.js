// Wasser- und Dampfeigenschaften aus einer Sättigungstabelle.
//
// Kein IAPWS-IF97. Die vollständige Formulierung wären mehrere hundert
// Koeffizienten für eine Genauigkeit, die in einem Spiel niemand sieht -- und
// sie wäre schwerer zu prüfen. 29 Stützstellen von 1 bis 180 bar, linear
// interpoliert, treffen jede hier gebrauchte Größe auf deutlich besser als ein
// Prozent und lassen sich mit einer einzigen Zusicherung auf Monotonie testen.
//
// Der obere Rand ist bewusst 180 bar und nicht 90: der Druckwasserreaktor
// fährt bei 158 bar, seine Sicherheitsventile öffnen bei 171 bar, und die
// Unterkühlungsspanne -- T_sat(p) minus heiße Strangtemperatur -- ist eine der
// wichtigsten Anzeigen im Primärkreis.
//
// Einheiten: p in bar, T in Kelvin, h in kJ/kg, v in m³/kg.

import { toK, clamp } from './constants.js';

// p, T_sat(°C), h_f, h_g, v_f, v_g
const TABLE = [
  // Der Kondensator faehrt bei 0,04 bis 0,06 bar -- ohne diese Zeilen haette
  // die Tabelle bei 1 bar ihren Rand genau dort, wo der Sekundaerkreis seine
  // Waerme loswird.
  [0.02, 17.51, 73.5, 2533.6, 0.001001, 67.0060],
  [0.05, 32.88, 137.8, 2561.6, 0.001005, 28.1940],
  [0.10, 45.81, 191.8, 2584.7, 0.001010, 14.6740],
  [0.20, 60.06, 251.4, 2609.7, 0.001017, 7.65000],
  [0.50, 81.33, 340.5, 2645.9, 0.001030, 3.24000],
  [1.0, 99.63, 417.5, 2675.4, 0.001043, 1.69400],
  [2.0, 120.23, 504.7, 2706.7, 0.001061, 0.88570],
  [5.0, 151.86, 640.1, 2748.7, 0.001093, 0.37490],
  [10, 179.91, 762.6, 2778.1, 0.001127, 0.19444],
  [15, 198.32, 844.7, 2792.2, 0.001154, 0.13177],
  [20, 212.42, 908.6, 2799.5, 0.001177, 0.09963],
  [25, 223.99, 962.0, 2803.1, 0.001197, 0.07998],
  [30, 233.90, 1008.4, 2804.2, 0.001217, 0.06668],
  [35, 242.60, 1049.8, 2803.4, 0.001235, 0.05707],
  [40, 250.40, 1087.3, 2801.4, 0.001252, 0.04978],
  [45, 257.49, 1122.1, 2798.3, 0.001269, 0.04406],
  [50, 263.99, 1154.2, 2794.3, 0.001286, 0.03944],
  [55, 270.00, 1184.9, 2789.9, 0.001302, 0.03563],
  [60, 275.64, 1213.7, 2784.3, 0.001319, 0.03244],
  [65, 280.86, 1241.1, 2778.6, 0.001335, 0.02972],
  [70, 285.88, 1267.4, 2772.1, 0.001351, 0.02737],
  [75, 290.59, 1292.7, 2765.5, 0.001368, 0.02533],
  [80, 295.06, 1317.1, 2758.0, 0.001384, 0.02352],
  [85, 299.27, 1340.7, 2750.1, 0.001401, 0.02192],
  [90, 303.40, 1363.7, 2742.1, 0.001418, 0.02048],
  [100, 311.06, 1408.0, 2727.7, 0.001452, 0.018026],
  [110, 318.08, 1450.6, 2711.4, 0.001489, 0.015987],
  [120, 324.75, 1491.8, 2693.8, 0.001527, 0.014263],
  [130, 330.93, 1531.5, 2673.8, 0.001567, 0.012780],
  [140, 336.75, 1571.1, 2651.6, 0.001611, 0.011485],
  [150, 342.24, 1610.5, 2627.0, 0.001658, 0.010340],
  [160, 347.44, 1650.1, 2600.3, 0.001710, 0.009318],
  [170, 352.37, 1690.3, 2571.0, 0.001770, 0.008391],
  [180, 357.06, 1732.0, 2538.4, 0.001840, 0.007545],
];

export const P_MIN = TABLE[0][0];
export const P_MAX = TABLE[TABLE.length - 1][0];

/** Tabellenzeile suchen: Index i mit TABLE[i][0] <= p < TABLE[i+1][0]. */
function findP(p) {
  let lo = 0;
  let hi = TABLE.length - 2;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (TABLE[mid][0] <= p) lo = mid; else hi = mid - 1;
  }
  return lo;
}

function interp(p, col) {
  const pc = clamp(p, P_MIN, P_MAX);
  const i = findP(pc);
  const a = TABLE[i];
  const b = TABLE[i + 1];
  const f = (pc - a[0]) / (b[0] - a[0]);
  return a[col] + f * (b[col] - a[col]);
}

/** Sättigungstemperatur in Kelvin. */
export function tsat(p) { return toK(interp(p, 1)); }
/** Enthalpie der siedenden Flüssigkeit, kJ/kg. */
export function hf(p) { return interp(p, 2); }
/** Enthalpie des Sattdampfs, kJ/kg. */
export function hg(p) { return interp(p, 3); }
/** Verdampfungsenthalpie, kJ/kg. */
export function hfg(p) { return hg(p) - hf(p); }
/** Spezifisches Volumen Flüssigkeit / Dampf, m³/kg. */
export function vf(p) { return interp(p, 4); }
export function vg(p) { return interp(p, 5); }
/** Dichten, kg/m³. */
export function rhof(p) { return 1 / vf(p); }
export function rhog(p) { return 1 / vg(p); }

/** Sättigungsdruck zu einer Temperatur (Kelvin) -- die Umkehrung von tsat().
 *  Die Tabelle ist in T streng monoton, also genügt dieselbe Suche. */
export function psat(T) {
  const Tc = T - 273.15;
  if (Tc <= TABLE[0][1]) return P_MIN;
  if (Tc >= TABLE[TABLE.length - 1][1]) return P_MAX;
  let lo = 0;
  let hi = TABLE.length - 2;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (TABLE[mid][1] <= Tc) lo = mid; else hi = mid - 1;
  }
  const a = TABLE[lo];
  const b = TABLE[lo + 1];
  return a[0] + ((Tc - a[1]) / (b[1] - a[1])) * (b[0] - a[0]);
}

/** dp_sat/dT in bar/K. Bestimmt, wie stark ein Dampfraum auf eine
 *  Temperaturänderung mit Druck antwortet. */
export function dpdT(p) {
  const pc = clamp(p, P_MIN, P_MAX);
  const i = findP(pc);
  return (TABLE[i + 1][0] - TABLE[i][0]) / (TABLE[i + 1][1] - TABLE[i][1]);
}

/**
 * Mittlerer Dampfblasenanteil nach Zuber-Findlay (Drift-Flux).
 *
 *   α = x / [ C₀·(x + (1−x)·ρ_g/ρ_f) + V_gj·ρ_g/G ]
 *
 * C₀ = 1,13 berücksichtigt, dass Dampf bevorzugt in der schnellen Kanalmitte
 * läuft; V_gj ist der Auftrieb der Blasen gegenüber dem Wasser. Ohne den
 * Driftterm käme bei kleinem Massenstrom ein viel zu hoher Blasenanteil heraus
 * -- und genau dieser Bereich ist beim Siedewasserreaktor der interessante.
 *
 * @param {number} x  Dampfgehalt (Massenanteil) am Kernaustritt
 * @param {number} p  Druck in bar
 * @param {number} G  Massenstromdichte in kg/m²s
 */
export function voidFraction(x, p, G) {
  if (!(x > 0)) return 0;
  const xc = clamp(x, 0, 1);
  const rg = rhog(p);
  const rf = rhof(p);
  const C0 = 1.13;
  // V_gj = 2,9·(σ·g·Δρ/ρ_f²)^0,25. Die Oberflächenspannung von Wasser fällt
  // mit dem Druck; die Näherung σ ≈ 0,0588·(1 − T/T_krit)^1,2 reicht hier.
  const T = tsat(p);
  const Tkrit = 647.1;
  const sigma = Math.max(0.0588 * Math.pow(Math.max(1 - T / Tkrit, 1e-3), 1.2), 1e-4);
  const Vgj = 2.9 * Math.pow((sigma * 9.81 * (rf - rg)) / (rf * rf), 0.25);
  const Gc = Math.max(G, 1);
  const denom = C0 * (xc + (1 - xc) * (rg / rf)) + (Vgj * rg) / Gc;
  return clamp(xc / denom, 0, 0.99);
}

/**
 * Austrittsdampfgehalt aus der Wärmebilanz eines siedenden Kanals.
 * Erst wird das unterkühlte Wasser auf Sättigung gebracht, der Rest verdampft.
 *
 * @param {number} P_th   Wärmeleistung in MW
 * @param {number} W      Massenstrom in kg/s
 * @param {number} dTsub  Unterkühlung am Eintritt in K
 * @param {number} p      Druck in bar
 * @param {number} cp     spezifische Wärme in kJ/kgK
 */
export function exitQuality(P_th, W, dTsub, p, cp = 4.9) {
  if (!(W > 0)) return 0;
  const q = (P_th * 1000) / W;          // kJ/kg zugeführt
  const sub = Math.max(dTsub, 0) * cp;  // kJ/kg bis zur Sättigung
  const x = (q - sub) / hfg(p);
  return clamp(x, 0, 1);
}

/**
 * Mittlerer Blasenanteil über die Kernhöhe.
 *
 * voidFraction() liefert den Wert am Kernaustritt. Der Kern ist aber nicht
 * überall gleich: unten tritt unterkühltes Wasser ein, der Dampfgehalt wächst
 * über die Höhe bis zum Austrittswert. Für die Reaktivität zählt der
 * Mittelwert, und der liegt deutlich unter dem Austrittswert -- ein
 * Siedewasserreaktor mit 70 % Blasen am Austritt hat im Mittel rund 40 %.
 *
 * Der Dampfgehalt wird linear über die Siedezone angenommen und α(x) darüber
 * numerisch gemittelt. Die unterkühlte Vorlaufstrecke zählt mit null.
 *
 * @param {number} xe     Dampfgehalt am Austritt
 * @param {number} p      Druck in bar
 * @param {number} G      Massenstromdichte in kg/m²s
 * @param {number} fBoil  Anteil der Kernhöhe, in dem gesiedet wird (0..1)
 */
export function averageVoid(xe, p, G, fBoil = 0.8) {
  if (!(xe > 0) || !(fBoil > 0)) return 0;
  const N = 8;
  let sum = 0;
  for (let i = 0; i < N; i++) {
    const f = (i + 0.5) / N;          // Position in der Siedezone
    sum += voidFraction(xe * f, p, G);
  }
  return clamp((sum / N) * clamp(fBoil, 0, 1), 0, 0.95);
}
