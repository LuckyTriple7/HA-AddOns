// Punktkinetik mit sechs Gruppen verzögerter Neutronen.
//
//   n'   = ((ρ − β)/Λ)·n + Σ λ_i c_i + S
//   c_i' = (β_i/Λ)·n − λ_i c_i
//
// Gelöst mit einem exponentiellen Integrator: über einen Teilschritt werden die
// Vorläufer als Quelle q = Σλ_i c_i + S festgehalten, und die dann lineare
// Leistungsgleichung n' = a·n + q mit a = (ρ−β)/Λ wird EXAKT gelöst:
//
//   n^{k+1} = n^k·e^{a·h} + (q/a)·(e^{a·h} − 1)
//   c_i^{k+1} = [c_i^k + h·(β_i/Λ)·n^{k+1}] / (1 + λ_i·h)   (implizit)
//
// Warum nicht Rückwärts-Euler? Er ist zwar stabil, ersetzt aber e^{a·h} durch
// 1/(1−a·h). Der Unterschied ist ein Ratenfehler von rund a·h/2, und bei einer
// prompt-kritischen Exkursion über viele e-Faltungen multipliziert sich dieser
// Fehler auf: bei dt = 0,05 s gegen dt = 0,0125 s lagen die Spitzenwerte 47 %
// auseinander. Der exponentielle Integrator ist für genau diesen Fall exakt und
// dadurch praktisch dt-unabhängig.
//
// Warum nicht die Prompt-Jump-Näherung? Sie ist bei ρ → β singulär und oberhalb
// davon schlicht ungültig -- also genau dort unbrauchbar, wo das RBMK-Szenario
// spielt. Der exponentielle Integrator liefert sie unterhalb prompt-kritisch
// von selbst: bei stark negativem a strebt n gegen −q/a, und das ist genau der
// Prompt-Jump-Wert. Oberhalb bleibt er endlich und richtig.

import { LAMBDA_I, BETA_FRAC, NGROUPS, SOURCE } from './constants.js';

/** Obergrenze der Untertakte. Ein Druckwasserkern bei ρ−β = 500 pcm bräuchte
 *  zur exakten Auflösung 125 000 davon -- an dem Punkt ist der Kern ohnehin
 *  zerstört, und die richtige Spielantwort ist ein Ende, kein exakter
 *  Mikrosekundenverlauf. Der exponentielle Integrator bleibt auch gedeckelt
 *  stabil -- er wird nur ungenauer in der Kopplung an die Vorläufer, die bei
 *  diesem Tempo ohnehin keine Rolle mehr spielen. */
const MAX_SUBSTEPS = 200;

/** Kinetikbeiwerte eines Reaktortyps, einmal je Lauf gebaut. */
export function makeKinetics(betaEff, Lambda, source = SOURCE) {
  const beta_i = BETA_FRAC.map((f) => f * betaEff);
  return {
    beta: betaEff,
    beta_i,
    Lambda,
    source,
    lambda: LAMBDA_I,
  };
}

/** Gleichgewichtsvorläufer zu einer Leistung -- so startet jeder Preset. */
export function equilibriumPrecursors(kin, n) {
  const c = new Float64Array(NGROUPS);
  for (let i = 0; i < NGROUPS; i++) {
    c[i] = kin.beta_i[i] * n / (kin.lambda[i] * kin.Lambda);
  }
  return c;
}

/**
 * Ein Zeitschritt der Kinetik.
 *
 * @param {{n:number, c:Float64Array}} s   Zustand (wird verändert)
 * @param {object} kin                      aus makeKinetics()
 * @param {number} rho                      Reaktivität zu Beginn des Schritts
 * @param {number} dt                       Simulationsschritt
 * @param {(dtSub:number, n:number)=>number|null} [onSubstep]
 *        Rückruf nach jedem Untertakt. Damit koppelt die Engine die
 *        Brennstofftemperatur INNERHALB der Untertakte ein und gibt die neue
 *        Reaktivität zurück. Ohne diese Kopplung dreht die Doppler-Rückkopplung
 *        eine Exkursion nie um, und die Leistung läuft davon -- das ist der
 *        Unterschied zwischen selbstbegrenzend und NaN.
 * @returns {{substeps:number, promptCritical:boolean}}
 */
export function stepKinetics(s, kin, rho, dt, onSubstep) {
  const { beta, beta_i, Lambda, lambda, source } = kin;

  // Untertakte nur, wenn die prompte Zeitkonstante Λ/(ρ−β) kürzer wird als
  // ein Zehntel des Schritts. Unterhalb prompt-kritisch ist m = 1.
  const excess = rho - beta;
  let m = 1;
  if (excess > 0) {
    m = Math.ceil((dt * excess) / (0.1 * Lambda));
    if (!Number.isFinite(m) || m < 1) m = 1;
  }
  // ρ > β heißt prompt kritisch: die Kettenreaktion trägt sich ohne die
  // verzögerten Neutronen. Das meldet die Kinetik nach oben, damit Engine und
  // Oberfläche den Zeitraffer sperren und das Abbruchkriterium greifen kann.
  const promptCritical = excess > 0;
  if (m > MAX_SUBSTEPS) m = MAX_SUBSTEPS;

  const h = dt / m;
  const c = s.c;
  let rhoNow = rho;

  for (let k = 0; k < m; k++) {
    let q = source;                      // Quelle aus den Vorläufern
    for (let i = 0; i < NGROUPS; i++) q += lambda[i] * c[i];

    const a = (rhoNow - beta) / Lambda;
    let x = a * h;
    // Deckel gegen Überlauf: e^40 ist ein Wachstum um 2e17 in einem Teilschritt.
    // Wer hier landet, hat den Kern ohnehin verloren; das Abbruchkriterium über
    // die Brennstoffenthalpie greift im selben oder nächsten Schritt.
    if (x > 40) x = 40;

    if (Math.abs(x) < 1e-8) {
      // Reihenentwicklung -- bei a → 0 wäre (e^x − 1)/a numerisch 0/0.
      s.n = s.n + (a * s.n + q) * h;
    } else {
      const E = Math.exp(x);
      s.n = s.n * E + (q / a) * (E - 1);
    }
    if (s.n < 0) s.n = 0;

    for (let i = 0; i < NGROUPS; i++) {
      c[i] = (c[i] + (h * beta_i[i] * s.n) / Lambda) / (1 + lambda[i] * h);
    }

    if (onSubstep) {
      const r = onSubstep(h, s.n);
      if (typeof r === 'number' && Number.isFinite(r)) rhoNow = r;
    }
  }

  return { substeps: m, promptCritical };
}

/**
 * Stabile Reaktorperiode zur Reaktivität ρ (Inhour-Gleichung).
 *
 *   ρ = Λ/T + Σ β_i/(1 + λ_i·T)
 *
 * Nur für Prüfung und Anzeige gedacht, nicht im Rechenpfad. Gelöst per
 * Bisektion über 1/T, weil die Gleichung in T Pole bei −1/λ_i hat.
 */
export function inhourPeriod(kin, rho) {
  if (Math.abs(rho) < 1e-12) return Infinity;
  const { beta_i, Lambda, lambda } = kin;
  const f = (w) => {   // w = 1/T
    let r = Lambda * w;
    for (let i = 0; i < NGROUPS; i++) r += (beta_i[i] * w) / (w + lambda[i]);
    return r - rho;
  };
  // Die stabile Wurzel liegt für ρ>0 in (0, ∞), für ρ<0 in (−λ_1, 0).
  let lo, hi;
  if (rho > 0) {
    lo = 1e-12; hi = 1;
    while (f(hi) < 0 && hi < 1e9) hi *= 2;
  } else {
    hi = -1e-12; lo = -lambda[0] + 1e-9;
  }
  for (let i = 0; i < 200; i++) {
    const mid = 0.5 * (lo + hi);
    if (f(mid) > 0) hi = mid; else lo = mid;
  }
  return 1 / (0.5 * (lo + hi));
}

/** Momentane Periode aus der Änderungsrate -- das ist, was ein echtes
 *  Periodenmessgerät anzeigt. */
export function measuredPeriod(nPrev, nNow, dt) {
  if (!(nPrev > 0) || !(nNow > 0) || !(dt > 0)) return Infinity;
  const rate = Math.log(nNow / nPrev) / dt;
  return Math.abs(rate) < 1e-7 ? Infinity : 1 / rate;
}
