// Reaktivitätsbilanz als Registry einzelner Beiträge.
//
//   ρ = ρ_Stäbe + ρ_Doppler + ρ_Moderator + ρ_Void + ρ_Xe + ρ_Sm + ρ_Bor
//       + ρ_Graphit + ρ_Spitzen + ρ_Abbrand + ρ_extern
//
// Jeder Summand ist ein Eintrag {id, fn(state, spec)}. Die Engine verzweigt
// dadurch nie nach Reaktortyp -- ein Typ setzt seine Liste zusammen und hängt
// über hooks.reactivity() eigene Beiträge an. Nebeneffekt, und zwar der
// wertvollste: die Oberfläche bekommt die Aufschlüsselung geschenkt und kann
// zeigen, welcher Effekt gerade wie viele pcm liefert.
//
// Kennwerte kommen aus den Typdateien in pcm (so stehen sie in der Literatur),
// gerechnet wird durchgehend in Δk/k. Umgerechnet wird einmal hier beim Bauen.

const PCM = 1e-5;

/** Integrale Stabwirksamkeit. S(0) = 0 (ganz gezogen), S(1) = 1 (ganz drin).
 *  Die Ableitung ist in der Kernmitte am größten -- dort ist der Fluss am
 *  höchsten, und dort bewegt ein Zentimeter Stab am meisten. */
export function rodWorthCurve(h) {
  const x = h < 0 ? 0 : (h > 1 ? 1 : h);
  return x - Math.sin(2 * Math.PI * x) / (2 * Math.PI);
}

/**
 * Baut die Beitragsliste eines Reaktortyps.
 * @param {object} spec   Typdatenobjekt (plants/*.js)
 * @param {object} [hooks] optional, hooks.reactivity(spec) → zusätzliche Einträge
 */
export function makeReactivity(spec, hooks) {
  const fb = spec.feedbacks || [];
  const parts = [];
  const has = (id) => fb.includes(id);

  // ── Steuerstäbe ────────────────────────────────────────────────────────────
  if (has('rods')) {
    const banks = spec.rodBanks || [];
    const worth = banks.map((b) => (b.worth || 0) * PCM);
    parts.push({
      id: 'rods',
      fn: (s) => {
        let r = 0;
        for (let i = 0; i < banks.length; i++) r -= worth[i] * rodWorthCurve(s.rod[i]);
        return r;
      },
    });
  }

  // ── Doppler ────────────────────────────────────────────────────────────────
  // ρ_D = K_D·(√T_f − √T_ref) mit K_D = 2·α_D·√T_ref.
  // Die Wurzelform ist die übliche Reduktion: die Verbreiterung der
  // Resonanzen geht mit √T, der Effekt schwächt sich also bei hoher Temperatur
  // ab und begrenzt sich selbst.
  if (has('doppler')) {
    const a = (spec.feedback.doppler_pcm_per_K || 0) * PCM;
    const Tref = spec.feedback.doppler_T_ref || 900;
    const K = 2 * a * Math.sqrt(Tref);
    parts.push({
      id: 'doppler',
      fn: (s) => K * (Math.sqrt(Math.max(s.T_f, 1)) - Math.sqrt(Tref)),
    });
  }

  // ── Moderatortemperatur ────────────────────────────────────────────────────
  // α_M = α_M0 + k_B·C_B. Bor ist ein Absorber im Wasser: wird das Wasser
  // wärmer und dünner, verschwindet mit dem Moderator auch Absorber. Bei hoher
  // Borkonzentration hebt das den negativen Moderatorkoeffizienten auf -- ein
  // frisch beladener Kern mit 2000 ppm ist deshalb spürbar weniger gutmütig.
  if (has('mtc')) {
    const a0 = (spec.feedback.mtc_pcm_per_K || 0) * PCM;
    const kB = (spec.feedback.mtc_pcm_per_K_per_ppm || 0) * PCM;
    const Tref = spec.feedback.mtc_T_ref || 578;
    parts.push({
      id: 'moderator',
      fn: (s) => (a0 + kB * (s.C_B || 0)) * (s.T_mod - Tref),
    });
  }

  // ── Dampfblasen ────────────────────────────────────────────────────────────
  // Kennwert in pcm je Prozent Blasenanteil. Beim Siedewasserreaktor stark
  // negativ, beim RBMK positiv -- dort ersetzt der Hook den Beitrag durch eine
  // von der Abschaltreserve abhängige Fassung.
  if (has('void')) {
    const a = (spec.feedback.void_pcm_per_pct || 0) * PCM;
    const ref = spec.feedback.void_ref || 0;
    parts.push({ id: 'void', fn: (s) => a * (s.alphaBar - ref) * 100 });
  }

  // ── Vergiftung ─────────────────────────────────────────────────────────────
  if (has('xenon')) {
    const w = (spec.feedback.xenon_worth_pcm || 0) * PCM;
    parts.push({ id: 'xenon', fn: (s) => -w * s.X });
  }
  if (has('samarium')) {
    const w = (spec.feedback.samarium_worth_pcm || 0) * PCM;
    parts.push({ id: 'samarium', fn: (s) => -w * s.Sm });
  }

  // ── Bor ────────────────────────────────────────────────────────────────────
  if (has('boron')) {
    const w = (spec.feedback.boron_pcm_per_ppm || 0) * PCM;
    const ref = spec.feedback.boron_ref_ppm || 0;
    parts.push({ id: 'boron', fn: (s) => -w * ((s.C_B || 0) - ref) });
  }

  // ── Graphit ────────────────────────────────────────────────────────────────
  if (has('graphite')) {
    const a = (spec.feedback.graphite_pcm_per_K || 0) * PCM;
    const Tref = spec.feedback.graphite_T_ref || 800;
    parts.push({ id: 'graphite', fn: (s) => a * ((s.T_gr || Tref) - Tref) });
  }

  // ── Überschussreaktivität des Brennstoffs ──────────────────────────────────
  // Ein frisch beladener Kern ist weit überkritisch -- sonst könnte er nicht
  // ein Jahr lang laufen, während Spaltprodukte und Abbrand ihn Stück für Stück
  // vergiften. Dieser Überschuss wird niedergehalten: beim Druckwasserreaktor
  // durch Bor, bei den anderen Typen durch die Stäbe. Ohne diesen Beitrag wäre
  // die Bilanz um Xenon und Samarium zu negativ und der Kern nicht kritisch
  // zu bekommen.
  if (has('excess')) {
    const e0 = (spec.feedback.excess_pcm || 0) * PCM;
    const cycle = spec.cycleEFPD || 450;
    parts.push({
      id: 'excess',
      fn: (s) => e0 * (1 - Math.min((s.burnup || 0) / cycle, 1)),
    });
  }

  // ── Störungen und Szenarien ────────────────────────────────────────────────
  parts.push({ id: 'external', fn: (s) => s.rho_ext || 0 });

  if (hooks && typeof hooks.reactivity === 'function') {
    for (const extra of hooks.reactivity(spec) || []) parts.push(extra);
  }

  return new Reactivity(parts);
}

export class Reactivity {
  constructor(parts) {
    this.parts = parts;
    /** Aufschlüsselung des letzten Aufrufs, in Δk/k. Die Oberfläche liest sie,
     *  die Rechnung nicht -- hier wird nichts zwischengespeichert, was den
     *  nächsten Schritt beeinflussen könnte. */
    this.breakdown = Object.create(null);
    for (const p of parts) this.breakdown[p.id] = 0;
    this.total = 0;
  }

  /** @returns {number} ρ in Δk/k */
  compute(s, spec) {
    let sum = 0;
    for (const p of this.parts) {
      const v = p.fn(s, spec) || 0;
      this.breakdown[p.id] = v;
      sum += v;
    }
    this.total = sum;
    return sum;
  }
}
