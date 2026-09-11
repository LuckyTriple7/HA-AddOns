// PLATZHALTER-ENGINE (P0).
//
// Diese Datei wird in P1/P2 durch die echte Simulation ersetzt: Punktkinetik
// mit sechs Gruppen verzögerter Neutronen, Rückkopplungen, Xenon, Thermo-
// hydraulik. Bis dahin liefert sie einen groben, aber in sich stimmigen
// Betriebszustand, damit Anordnung, Taktbremse und Statuszeile schon jetzt an
// bewegten Zahlen geprüft werden können.
//
// Die Schnittstelle ist bereits die endgültige: `state` als einfaches Objekt,
// `step(dt)` mit festem dt, kein Zugriff auf das DOM. Dadurch bleibt das Modul
// unter node --test lauffähig und kann später in einen Web Worker wandern.

const SPECS = {
  pwr:  { P0_th: 3850, P0_e: 1400, p_prim: 158.0, t_in: 291, t_out: 326, w_core: 20000 },
  bwr:  { P0_th: 3840, P0_e: 1344, p_prim: 70.7,  t_in: 278, t_out: 286, w_core: 13000 },
  rbmk: { P0_th: 3200, P0_e: 1000, p_prim: 69.0,  t_in: 270, t_out: 284, w_core: 10500 },
};

export function createEngine(reactorId = 'pwr') {
  const spec = SPECS[reactorId] || SPECS.pwr;

  const state = {
    reactor: reactorId,
    spec,
    t_sim: 0,
    n: 1.0,            // neutronische Leistung, 1,0 = Nennleistung
    decay: 0.07,       // Nachzerfallswärme als Anteil von P0
    demand_e: spec.P0_e,
    period: Infinity,
    scram: false,
    placeholder: true,
  };

  // Der Bedarf pendelt langsam, damit die Anzeige nicht totsteht.
  let phase = 0;

  function step(dt) {
    state.t_sim += dt;
    phase += dt;

    // Netzanforderung: sehr langsame Schwingung um 85 % der Nennleistung.
    state.demand_e = spec.P0_e * (0.85 + 0.12 * Math.sin(phase / 240));

    // Leistung folgt der Anforderung träge (erster Ordnung, tau = 40 s).
    const target = state.scram ? 0 : state.demand_e / spec.P0_e;
    const tau = 40;
    const prev = state.n;
    state.n += (target - state.n) * (1 - Math.exp(-dt / tau));

    // Reaktorperiode aus der relativen Änderungsrate.
    const rate = (state.n - prev) / dt / Math.max(state.n, 1e-9);
    state.period = Math.abs(rate) < 1e-6 ? Infinity : 1 / rate;
  }

  return { state, step };
}

/** Aus dem Zustand abgeleitete Anzeigewerte -- nie gespeichert, immer gerechnet. */
export function derive(s) {
  const spec = s.spec;
  const p_th = spec.P0_th * (0.93 * s.n + s.decay);
  const load = p_th / spec.P0_th;
  const t_cold = spec.t_in + 4 * load;
  const t_hot = t_cold + (spec.t_out - spec.t_in) * load;
  return {
    p_th,
    power_th_pct: 100 * p_th / spec.P0_th,
    n_pct: 100 * s.n,
    decay_pct: 100 * s.decay,
    power_e: spec.P0_e * s.n * 0.995,
    demand_e: s.demand_e,
    deviation: spec.P0_e * s.n * 0.995 - s.demand_e,
    t_cold,
    t_hot,
    t_avg: 0.5 * (t_hot + t_cold),
    t_fuel: 300 + 1200 * load,
    t_clad: t_hot + 30 * load,
    p_prim: spec.p_prim,
    w_core: spec.w_core,
    period: s.period,
    freq: 50.0,
  };
}
