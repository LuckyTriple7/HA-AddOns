// RBMK-1000.
//
// 3200 MWth / 1000 MWe (zwei Turbosätze à 500), graphitmoderiert, Druckröhren,
// siedendes Leichtwasser, keine Volldruck-Sicherheitshülle.
//
// Die drei Eigenheiten, um die es in diesem Spiel geht:
//
// 1. POSITIVER DAMPFBLASENKOEFFIZIENT. Moderiert wird mit Graphit, nicht mit
//    Wasser. Das Wasser ist netto ein Absorber. Verschwindet es als Dampf,
//    steigt die Reaktivität -- mehr Leistung, mehr Dampf, noch mehr Leistung.
//    Wie stark, hängt davon ab, wie viele Absorberstäbe im Kern stecken: je
//    weniger, desto positiver.
//
// 2. ORM, die Abschaltreserve in Stabäquivalenten. Sie ist kein Kennwert für
//    die Statistik, sondern der Parameter, der den Blasenkoeffizienten
//    einstellt. Unter 30 Stäben ist der Betrieb verboten. Bei sechs ist der
//    Reaktor ein anderes Gerät.
//
// 3. AZ-5 MIT GRAPHITSPITZEN. Unter jedem Absorber hängt ein 4,5 m langer
//    Graphitverdränger, und über und unter dem 7-m-Kern steht je eine
//    1,25-m-Wassersäule. Fährt ein ganz gezogener Stab ein, schiebt sich
//    zuerst der Graphit in die untere Wassersäule: Absorber raus, Moderator
//    rein, und zwar genau dort, wo bei bodennahem Flussprofil die meiste
//    Leistung entsteht. Die Schnellabschaltung fügt in den ersten Sekunden
//    POSITIVE Reaktivität ein. Erst danach greift der Absorber -- nach
//    achtzehn Sekunden, mit einem Antrieb von 0,4 m/s.
//
// Keiner dieser drei Punkte ist nachträglich angeflanscht. Sie fallen aus
// denselben Gleichungen wie bei den anderen beiden Reaktortypen; nur die
// Vorzeichen und Kennwerte sind andere.

import { Pump, Valve, Lag } from '../sim/components.js';
import {
  FeedwaterController, GovernorController, RodController, PowerController,
} from '../sim/controllers.js';
import { tsat, psat, hg, hf, hfg, rhog, dpdT, averageVoid } from '../sim/steam.js';
import { clamp, toK, relax, LAMBDA_I135, LAMBDA_XE } from '../sim/constants.js';
import { stepPoisons, equilibriumPoisons } from '../sim/poisons.js';
import { rodWorthCurve } from '../sim/reactivity.js';
import { SEVERITY } from '../sim/trips.js';

const P0_DRUM = 69;
const T_FW = toK(165);
const H_FW = 4.2 * 165;

export const spec = {
  id: 'rbmk',
  P0_th: 3200,
  P0_e: 1000,
  cycleEFPD: 1100,          // wird im Betrieb nachgeladen, daher lang

  beta: { boc: 0.0048, eoc: 0.0045 },
  // Graphit bremst langsamer als Wasser: die prompte Lebensdauer ist fünfzig
  // Mal länger als im Druckwasserreaktor. Deshalb läuft eine Exkursion hier
  // über Sekunden statt über Mikrosekunden -- und deshalb ist sie überhaupt
  // darstellbar.
  Lambda: 1e-3,

  fuel: {
    mass_t: 192,
    cp: 300,
    tau: 7.0,
    // Ein guter Teil der Energie landet direkt im Graphit, nicht im Brennstoff.
    depositFraction: 0.94,
    T_melt: 3120,
  },
  clad: { C_frac: 0.14, tau: 0.05, T_fail: 1477 },

  coolant: {
    W0: 10500,
    cp: 4.9,
    T_in: tsat(P0_DRUM) - 26,
    T_out: tsat(P0_DRUM),
    p0: P0_DRUM,
    mass: 24000,
    flowArea_m2: 9.0,
  },

  graphite: {
    mass_t: 1700,
    cp: 700,              // J/kgK
    powerFraction: 0.05,  // Anteil der Spaltenergie, der im Graphit landet
    UA: 560,              // kW/K zu den Druckröhren
    T0: toK(600),
  },

  feedbacks: ['rods', 'doppler', 'xenon', 'samarium', 'graphite', 'excess'],

  feedback: {
    // Der Doppler ist bei diesem Typ der einzige kräftige negative Beitrag im
    // Leistungskoeffizienten -- Graphit und Dampfblasen ziehen beide nach oben.
    // Mit -1,2 pcm/K blieb netto fast nichts übrig (-54 pcm je Einheit
    // Leistung), und die Anlage driftete allein durch den Xenon-Abbrand binnen
    // drei Stunden über die Leistungsauslösung. Auch -2,0 reichte noch nicht:
    // der Xenon-Abbrand liefert auf seiner eigenen Zeitskala rund +420 pcm je
    // Einheit, und dagegen muss der Leistungskoeffizient deutlich stehen.
    // -2,6 pcm/K ergibt netto etwa -730 pcm je Einheit. Bei Volllast ist die
    // Anlage damit ruhig -- und trotzdem weit weniger gutmütig als die beiden
    // Leichtwasserreaktoren. Ihre Gefahr liegt ohnehin nicht hier oben,
    // sondern bei kleiner Leistung: dort ist der Brennstoff kalt, der Doppler
    // schwach und der Dampfblasenkoeffizient wirksam.
    doppler_pcm_per_K: -2.6,
    doppler_T_ref: 1050,

    graphite_pcm_per_K: 0.5,
    graphite_T_ref: toK(600),

    xenon_worth_pcm: 3000,
    samarium_worth_pcm: 500,

    excess_pcm: 3700,

    // Der Blasenbeitrag steht NICHT in dieser Liste -- er kommt aus dem Haken,
    // weil sein Kennwert von der Abschaltreserve abhängt.
    void_ref: 0.25,
    void_pcm_per_pct_nominal: 20,   // bei ORM = 45
    void_pcm_per_pct_depleted: 62,  // bei ORM = 0
  },

  // Zwei Gruppen stellvertretend für 211 Stäbe. Die Stabzahl je Gruppe geht in
  // die Abschaltreserve ein -- sie wird in Stabäquivalenten gezählt, nicht in
  // pcm, weil der Betrieb sie so zählt.
  rodBanks: [
    { id: 'ctrl', worth: 2400, speed: 0.0056, initial: 0.22, rods: 120 },
    { id: 'sd', worth: 3200, speed: 0.0056, initial: 0.22, rods: 91 },
  ],
  // Motorantrieb, 0,4 m/s über sieben Meter Kern plus Wassersäulen.
  scram: { timeS: 18 },

  orm: { total: 211, nominal: 46, min: 30, alarm: 15 },

  // Graphitverdränger unter dem Absorber.
  tip: {
    // Wirksamkeit je Gruppe. So kalibriert, dass die Summe über beide Gruppen
    // bei flachem Flussprofil gut ein β ergibt und bei bodennahem Profil rund
    // zwei β -- zusammen mit dem Blasenkoeffizienten bei leerem Kern liegt die
    // Gesamteinfuhr dann in der Größenordnung, die am 26. April 1986 gemessen
    // wurde.
    worth_pcm: 320,
    // Nur Stäbe, die weit draußen stehen, schieben Graphit in die untere
    // Wassersäule. Wer schon halb drin steckt, hat dort längst Absorber.
    outThreshold: 0.12,
    // Über diesen Teil des Fahrwegs wirkt die Spitze, danach kommt der
    // Absorber.
    span: 0.30,
  },

  axial: {
    // Steifigkeit des Flussprofils: wie viel Reaktivitätsunterschied zwischen
    // oben und unten nötig ist, um die Verteilung ganz zu verschieben.
    //
    // Der Wert entscheidet über die Schleifenverstärkung der axialen
    // Xenon-Rückkopplung: mehr Fluss unten heißt dort zunächst WENIGER Xenon
    // (Abbrand ist schneller als der Jod-Nachschub), und das kippt das Profil
    // weiter. Mit 1400 pcm lag die Verstärkung über eins -- das Profil kippte
    // binnen zwei Stunden ganz nach unten und blieb dort. Mit 2500 bleibt die
    // Rückkopplung darunter: das Profil wandert sichtbar, läuft aber nicht weg.
    // Mit 1400 lag die Schleifenverstaerkung ueber eins und das Profil kippte
    // binnen zwei Stunden ganz nach unten; mit 2500 dauerte es sechs Stunden.
    // 4200 fasst zusammen, was dagegen haelt: die Geometrie des Kerns und vor
    // allem der oertliche Doppler -- die Zone mit mehr Fluss hat heisseren
    // Brennstoff und draengt den Fluss von selbst zurueck. Ein RBMK brauchte
    // dafuer im Original eine eigene Regelung der oertlichen
    // Leistungsverteilung; hier steckt sie in dieser einen Zahl.
    stiffness_pcm: 4200,
    tau: 300,            // s, das Profil folgt träge
    rodPush_pcm: 900,    // Stäbe fahren von oben ein und drücken den Fluss nach unten
  },

  drum: {
    p0: P0_DRUM,
    mass: 160000,
    cp: 5.2,
    level0: 0.5,
    massSpan: 36000,
    shrinkSwell: 1.2,
    voidCollapse: 0.014,
    T_fw: T_FW,
    W_steam0: 1538,
    subcool0: 26,
  },

  mcp: { count: 8, W0: 10500, coastTau: 8, rampTau: 5 },

  // workFactor so gewaehlt, dass 3200 MWth die 1000 MWe der beiden Turbosaetze
  // ergeben -- 31 % Gesamtwirkungsgrad, der niedrigste der drei Typen.
  turbine: { Cv: 44, strokeS: 3, workFactor: 0.2467, bypassCv: 22, bypassStrokeS: 1.0 },
  condenser: { T_cw: toK(15), pinch: 6, rise: 12, p0: 0.05 },

  mimic: 'mimic-rbmk',

  trips: [
    { id: 'power_high', key: 'trip_power_high', severity: SEVERITY.TRIP,
      test: (s) => s.n > 1.12, delay_s: 0.3, action: 'scram' },
    { id: 'period_short', key: 'trip_period_short', severity: SEVERITY.TRIP,
      test: (s, d) => s.n > 1e-3 && d.period > 0 && d.period < 10,
      delay_s: 1.0, action: 'scram' },
    { id: 'orm_low', key: 'alarm_orm_low', severity: SEVERITY.WARN,
      test: (s, d) => d.orm < 30, delay_s: 1.0 },
    { id: 'orm_critical', key: 'alarm_orm_critical', severity: SEVERITY.TRIP,
      test: (s, d) => d.orm < 15, delay_s: 1.0 },
    { id: 'void_positive', key: 'alarm_void_positive', severity: SEVERITY.WARN,
      test: (s, d) => d.voidCoeff > 45, delay_s: 2.0 },
    { id: 'drum_press_high', key: 'trip_dome_press_high', severity: SEVERITY.TRIP,
      test: (s) => s.p_drum > 76, delay_s: 0.5, action: 'scram' },
    { id: 'drum_level_low', key: 'trip_level_low', severity: SEVERITY.TRIP,
      test: (s) => s.L_drum < 0.25, delay_s: 1.5, action: 'scram' },
    { id: 'drum_level_high', key: 'alarm_level_high', severity: SEVERITY.WARN,
      test: (s) => s.L_drum > 0.78, delay_s: 2.0 },
    { id: 'mcp_cavitation', key: 'alarm_mcp_cavitation', severity: SEVERITY.WARN,
      test: (s, d) => d.subcooling < 4 && s.W_core > 0.9 * 10500, delay_s: 1.0 },
    { id: 'graphite_hot', key: 'alarm_graphite_hot', severity: SEVERITY.WARN,
      test: (s) => s.T_gr > toK(760), delay_s: 5 },
    { id: 'axial_tilt', key: 'alarm_axial_tilt', severity: SEVERITY.WARN,
      test: (s, d) => Math.abs(d.axialOffset) > 0.35, delay_s: 5 },
    { id: 'turbine_trip', key: 'alarm_turbine_trip', severity: SEVERITY.WARN,
      test: (s) => s.turbineTripped, delay_s: 0 },
    { id: 'clad_temp', key: 'trip_clad_temp', severity: SEVERITY.TRIP,
      test: (s) => s.T_cl > 1477, delay_s: 0, action: 'scram' },
  ],
};

export const hooks = {
  extraState(s, sp, ctx) {
    s.p_drum = sp.drum.p0;
    s.L_drum = sp.drum.level0;
    s.M_drum = sp.drum.mass;
    s.x_e = 0;
    s.alphaBar = sp.feedback.void_ref;
    s.dTsub = sp.drum.subcool0;
    s.W_steam = sp.drum.W_steam0;
    s.W_fw = sp.drum.W_steam0;
    s.gov = 0.8;
    s.bypass = 0;
    s.p_cond = sp.condenser.p0;
    s.turbineTripped = false;
    s.breaker = true;
    s.p_prim = sp.drum.p0;
    s.P_demand = sp.P0_e;
    s.mcpDmd = 1.0;
    s.T_gr = sp.graphite.T0;

    // Axiales Flussprofil. ao > 0 heißt bodennah -- genau der Zustand, in dem
    // die Graphitspitzen am gefährlichsten sind.
    s.ao = 0;

    // Zonenweises Xenon. Die Zonen sehen unterschiedliche Leistung, also baut
    // sich die Vergiftung oben und unten unterschiedlich auf, und daraus
    // entstehen axiale Xenon-Schwingungen von selbst.
    const eq = equilibriumPoisons(s.n);
    s.zTop = { I: eq.I, X: eq.X, Pm: eq.Pm, Sm: eq.Sm };
    s.zBot = { I: eq.I, X: eq.X, Pm: eq.Pm, Sm: eq.Sm };

    // Stellung der Stäbe beim Auslösen der Schnellabschaltung -- nur wer weit
    // draußen stand, schiebt Graphit in die untere Wassersäule.
    s.tipArmed = [0, 0];
    s.az5 = { armed: false, t: 0 };

    ctx.mcp = [];
    for (let i = 0; i < sp.mcp.count; i++) {
      ctx.mcp.push(new Pump({
        W0: sp.mcp.W0 / sp.mcp.count, coastTau: sp.mcp.coastTau, rampTau: sp.mcp.rampTau,
      }));
    }
    ctx.govValve = new Valve(sp.turbine.strokeS, 0.8);
    ctx.bypassValve = new Valve(sp.turbine.bypassStrokeS, 0);
    ctx.voidLag = new Lag(1.0, sp.feedback.void_ref);
    ctx.dpLag = new Lag(0.3, 0);
    ctx.pPrev = sp.drum.p0;
    ctx.aoLag = new Lag(sp.axial.tau, 0);

    // Der Stabregler dieses Typs geht auf die Leistung, nicht auf eine
    // Temperatur -- die liegt durch den Trommeldruck fest.
    ctx.rodCtl = new RodController({
      tAvgLow: tsat(sp.drum.p0), tAvgHigh: tsat(sp.drum.p0), deadbandK: 99, bank: 0,
    });
    ctx.rodCtl.auto = false;
    ctx.powerCtl = new PowerController({
      setpoint: s.n, deadband: 0.004, speed: sp.rodBanks[0].speed,
    });

    ctx.fwCtl = new FeedwaterController({
      levelSet: sp.drum.level0, W0: sp.drum.W_steam0, kp: 2.0, ki: 0.04,
    });
    ctx.govCtl = new GovernorController({
      mode: 'pressure', pSet: sp.drum.p0, P0: sp.P0_e, posNominal: 0.8,
      kp: 0.9, ki: 0.35, trim: 0.5,
    });
  },

  /** Der Blasenbeitrag hängt von der Abschaltreserve ab -- deshalb ein Haken. */
  reactivity(sp) {
    return [
      {
        id: 'void',
        fn: (s) => {
          const a = _voidCoeff(s, sp) * 1e-5;     // pcm/%Blasen → Δk/k
          return a * (s.alphaBar - sp.feedback.void_ref) * 100;
        },
      },
      {
        id: 'tip',
        fn: (s) => _tipReactivity(s, sp),
      },
    ];
  },

  trim(s, sp, ctx, rx) {
    const n = s.n;
    const P = sp.P0_th * n;
    s.W_core = sp.mcp.W0;
    s.p_drum = sp.drum.p0;
    s.p_prim = sp.drum.p0;

    const Tsat = tsat(s.p_drum);
    s.W_steam = (P * 1000) / (hg(s.p_drum) - H_FW);
    s.W_fw = s.W_steam;
    s.dTsub = _subcooling(s, sp);
    s.T_ci = Tsat - s.dTsub;
    s.T_co = Tsat;
    s.T_mod = Tsat;
    s.x_e = clamp(s.W_steam / s.W_core, 0, 1);
    s.P_th = P;
    s.alphaBar = _void(s, sp);
    ctx.voidLag.set(s.alphaBar);

    // Graphit im Gleichgewicht: was hineingeht, geht auch wieder heraus.
    s.T_gr = Tsat + (P * 1000 * sp.graphite.powerFraction) / sp.graphite.UA;

    // Bezugstemperatur der Brennstoffkette ist die MITTLERE Kuehlmittel-
    // temperatur, so wie die Engine sie im Rechenschritt bildet -- nicht die
    // Saettigungstemperatur. Der Unterschied betraegt nur die halbe
    // Unterkuehlung, aber er landet unverduennt in der Doppler-Rueckkopplung,
    // und beim RBMK mit seinem fast neutralen Leistungskoeffizienten wurden
    // daraus fuenf Prozent Leistungssprung in der ersten Minute.
    const Tbase = Tsat - 0.5 * s.dTsub;
    s.T_cl = Tbase + (P * 1000 * sp.fuel.depositFraction) / ctx.UA_cc;
    s.T_f = s.T_cl + (P * 1000 * sp.fuel.depositFraction) / ctx.UA_fc;

    // Kritisch über die Stabstellung. Beide Gruppen werden gemeinsam gefahren,
    // damit die Abschaltreserve ein sinnvoller Mittelwert bleibt.
    let lo = 0, hi = 1;
    for (let i = 0; i < 60; i++) {
      const mid = 0.5 * (lo + hi);
      s.rod[0] = mid; s.rod[1] = mid;
      if (rx.compute(s, sp) > 0) lo = mid; else hi = mid;
    }
    const h = 0.5 * (lo + hi);
    s.rod[0] = h; s.rod[1] = h;
    s.rodDmd[0] = h; s.rodDmd[1] = h;

    ctx.powerCtl.setpoint = n;

    // Axiales Profil ins Gleichgewicht setzen.
    s.ao = _axialTarget(s, sp);
    ctx.aoLag.set(s.ao);
    rx.compute(s, sp);

    s.P_e = (s.W_steam * (hg(s.p_drum) - hf(s.p_cond)) * sp.turbine.workFactor) / 1000;
    s.P_demand = s.P_e;
    ctx.fwCtl.pi.preset(0);
  },

  /** Siedender Kanal wie beim Siedewasserreaktor, plus der Graphitknoten. */
  coreCoolant(s, sp, ctx, qCoolKW, h) {
    const Tsat = tsat(s.p_drum);
    s.T_co = Tsat;
    s.T_mod = Tsat;
    s.T_ci = relax(s.T_ci, Tsat - s.dTsub, h, 4.0);

    const W = Math.max(s.W_core, 1);
    const qSub = W * sp.coolant.cp * Math.max(Tsat - s.T_ci, 0);
    const qBoil = Math.max(qCoolKW - qSub, 0);
    s.x_e = clamp(qBoil / (W * hfg(s.p_drum)), 0, 1);

    const collapse = sp.drum.voidCollapse * ctx.dpLag.v;
    s.alphaBar = ctx.voidLag.step(clamp(_void(s, sp) - collapse, 0, 0.95), h);

    // Graphit: große Masse, lange Zeitkonstante. Er ist der Grund, warum der
    // Reaktor nach einer Leistungsänderung noch minutenlang nachwirkt.
    const C_gr = (sp.graphite.mass_t * 1000 * sp.graphite.cp) / 1000;   // kJ/K
    const qGr = s.P_th * 1000 * sp.graphite.powerFraction;
    s.T_gr = relax(s.T_gr, Tsat + qGr / sp.graphite.UA, h, C_gr / sp.graphite.UA);
  },

  stepLoop(s, sp, ctx, dt) {
    // ── Hauptumwälzpumpen ───────────────────────────────────────────────────
    let W = 0;
    for (const p of ctx.mcp) { p.demand = clamp(s.mcpDmd, 0, 1.1); p.step(dt); W += p.flow(0.06); }
    s.W_core = W;

    // ── Dampfabgabe ─────────────────────────────────────────────────────────
    ctx.govValve.demand = s.turbineTripped ? 0 : s.gov;
    ctx.govValve.step(dt);
    ctx.bypassValve.demand = s.bypass;
    ctx.bypassValve.step(dt);

    const dp = Math.max(s.p_drum - s.p_cond, 0);
    const rhoS = rhog(s.p_drum);
    const W_t = ctx.govValve.flow(sp.turbine.Cv, rhoS, dp);
    const W_bp = ctx.bypassValve.flow(sp.turbine.bypassCv, rhoS, dp);
    s.srv = s.p_drum > 75 ? clamp((s.p_drum - 75) / 3, 0, 1) : 0;
    s.W_steam = W_t + W_bp + s.srv * 700;

    // ── Trommeldruck ────────────────────────────────────────────────────────
    const W_gen = s.x_e * s.W_core;
    const C_p = (sp.drum.mass * sp.drum.cp) / Math.max(dpdT(s.p_drum), 1e-6);
    const dh = Math.max(hg(s.p_drum) - H_FW, 1);
    const pNew = clamp(s.p_drum + (((W_gen - s.W_steam) * dh) * dt) / C_p, 1, 110);
    ctx.dpLag.step((pNew - ctx.pPrev) / dt, dt);
    ctx.pPrev = pNew;
    s.p_drum = pNew;
    s.p_prim = s.p_drum;

    // ── Trommelfüllstand ────────────────────────────────────────────────────
    s.M_drum = Math.max(s.M_drum + (s.W_fw - s.W_steam) * dt, 20000);
    const Ltrue = clamp(0.5 + (s.M_drum - sp.drum.mass) / sp.drum.massSpan, 0, 1);
    s.L_drum = clamp(Ltrue + sp.drum.shrinkSwell * (sp.drum.p0 - s.p_drum) / sp.drum.p0, 0, 1);

    s.dTsub = _subcooling(s, sp);

    // ── Axiales Flussprofil und zonenweise Vergiftung ───────────────────────
    // Die Zonen sehen unterschiedliche Leistung. Daraus wächst die Vergiftung
    // ungleich, daraus kippt das Profil, und daraus entstehen die axialen
    // Xenon-Schwingungen, für die dieser Reaktortyp bekannt ist.
    const fBot = 1 + s.ao;
    const fTop = 1 - s.ao;
    stepPoisons(s.zTop, s.n * fTop, dt);
    stepPoisons(s.zBot, s.n * fBot, dt);
    s.ao = ctx.aoLag.step(_axialTarget(s, sp), dt);

    // ── Turbine und Netz ────────────────────────────────────────────────────
    s.p_cond = clamp(psat(sp.condenser.T_cw + sp.condenser.pinch
      + (sp.condenser.rise || 12) * clamp(s.W_steam / sp.drum.W_steam0, 0, 1.2)), 0.02, 1.5);
    const wSpec = (hg(s.p_drum) - hf(s.p_cond)) * sp.turbine.workFactor;
    s.P_e = s.breaker && !s.turbineTripped ? (W_t * wSpec) / 1000 : 0;
  },

  stepControls(s, sp, ctx, dt) {
    if (!s.scram.active) {
      const d = ctx.powerCtl.step(s.n, dt);
      if (d !== 0) {
        s.rodDmd[0] = clamp(s.rodDmd[0] + d, 0, 1);
        s.rodDmd[1] = clamp(s.rodDmd[1] + d, 0, 1);
      }
    }
    s.W_fw = ctx.fwCtl.step(s.L_drum, s.W_steam, dt);
    s.gov = ctx.govCtl.step(s.P_e, s.P_demand, s.p_drum, dt);
    s.bypass = s.p_drum > sp.drum.p0 + 4 ? clamp((s.p_drum - sp.drum.p0 - 4) / 6, 0, 1) : 0;
  },

  /**
   * AZ-5. Beim Auslösen wird festgehalten, welche Gruppen weit draußen standen
   * -- nur die schieben Graphit in die untere Wassersäule.
   */
  onScram(s, sp, ctx) {
    for (let i = 0; i < s.rod.length; i++) {
      s.tipArmed[i] = s.rod[i] < sp.tip.outThreshold ? 1 : 0;
    }
    s.az5 = { armed: true, t: s.t_sim };
    s.turbineTripped = true;
    ctx.govCtl.trip();
    s.gov = 0;
    s.breaker = false;
  },

  uiControls(s, sp, ctx, kit) {
    const mcp = kit.slider({
      labelKey: 'ctl_mcp', min: 40, max: 110, step: 1,
      value: Math.round(s.mcpDmd * 100), digits: 0, unitKey: 'unit_percent',
      onInput: (v) => { s.mcpDmd = v / 100; },
    });
    return [
      { mount: 'primary', node: mcp.node, set: (st) => mcp.set(Math.round(st.mcpDmd * 100)) },
    ];
  },

  togglePump(s, sp, ctx, i) {
    const p = ctx.mcp[i];
    if (!p) return;
    if (p.state === 'run') p.trip(); else p.start();
  },

  derived(s, sp, ctx, base) {
    return {
      p_sg: s.p_drum,
      L_sg: s.L_drum,
      W_steam: s.W_steam,
      W_fw: s.W_fw,
      gov: s.gov,
      bypass: s.bypass,
      p_cond: s.p_cond,
      voidFrac: s.alphaBar,
      quality: s.x_e,
      subcooling: s.dTsub,
      orm: _orm(s, sp),
      voidCoeff: _voidCoeff(s, sp),
      axialOffset: s.ao,
      T_gr: s.T_gr,
      tip_pcm: _tipReactivity(s, sp) * 1e5,
      dnbr: _cpr(s, sp, base),
      shutdownMargin: sp.rodBanks.reduce((a, b, i) => a + b.worth * (1 - s.rod[i]), 0),
      pumpStates: ctx.mcp.map((p) => p.state),
    };
  },
};

// ── Hilfsfunktionen ───────────────────────────────────────────────────────────

/**
 * Abschaltreserve in Stabäquivalenten.
 *
 * Der Betrieb zählt sie in Stäben, nicht in pcm -- und genau deshalb steht sie
 * hier auch so. Nominal 46 von 211, betriebliches Minimum 30. In der Nacht des
 * 26. April 1986 waren es sechs bis acht.
 */
function _orm(s, sp) {
  let sum = 0;
  for (let i = 0; i < sp.rodBanks.length; i++) {
    sum += (sp.rodBanks[i].rods || 0) * clamp(s.rod[i], 0, 1);
  }
  return sum;
}

/**
 * Dampfblasenkoeffizient in pcm je Prozentpunkt Blasenanteil.
 *
 * Er ist immer positiv und wird mit sinkender Abschaltreserve schlimmer: jeder
 * gezogene Absorberstab ist ein Stück Absorber weniger, das den Effekt des
 * verschwindenden Wassers dämpft. Bei nominal 46 Stäben sind es 20 pcm je
 * Prozentpunkt, bei leerem Kern über 60.
 */
function _voidCoeff(s, sp) {
  const orm = _orm(s, sp);
  // Oberhalb der nominalen Abschaltreserve wird der Koeffizient nicht weiter
  // besser -- ohne diese Begrenzung waere er bei vollstaendig eingefahrenen
  // Staeben rechnerisch negativ, und der gefaehrlichste Kennwert dieses
  // Reaktortyps haette sich stillschweigend in eine Sicherheit verwandelt.
  const f = clamp(orm / sp.orm.nominal, 0, 1);
  const a0 = sp.feedback.void_pcm_per_pct_nominal;
  const a1 = sp.feedback.void_pcm_per_pct_depleted;
  return a1 + (a0 - a1) * f;
}

/**
 * Graphitspitzen der Schnellabschaltung.
 *
 *   ρ_Spitze = W · f_unten · Σ g(h)      g(h) = sin(π·h/span) für h < span
 *
 * Es zählen nur die Gruppen, die beim Auslösen weit draußen standen. f_unten
 * gewichtet mit dem Flussprofil: bei bodennahem Fluss wirkt der Graphit dort,
 * wo die meiste Leistung entsteht, und die Einfuhr wird doppelt so groß.
 *
 * Jenseits von span sitzt der Absorber im Kern und der Beitrag ist weg -- die
 * Reaktivität wird stark negativ. Nur eben zu spät.
 */
function _tipReactivity(s, sp) {
  if (!s.az5 || !s.az5.armed) return 0;
  const span = sp.tip.span;
  const fBot = clamp(1 + s.ao, 0, 2);
  let tip = 0;
  let notYet = 0;
  for (let i = 0; i < s.rod.length; i++) {
    if (!s.tipArmed[i]) continue;
    const h = s.rod[i];
    if (h <= 0) continue;

    // Der Graphitverdränger schiebt sich in die untere Wassersäule.
    if (h < span) tip += Math.sin((Math.PI * h) / span);

    // Und solange er das tut, ist der Absorber noch gar nicht im Kern -- er
    // hängt fünf Meter darüber. Der allgemeine Stabbeitrag rechnet ihn aber
    // vom ersten Zentimeter an mit, weil er nichts von Verdrängern weiß.
    // Hier wird er deshalb wieder herausgerechnet und über den doppelten
    // Verdrängerweg langsam wieder zugelassen.
    //
    // Ohne diese Verrechnung gewinnt der Absorber jede Sekunde: bei h = 0,3
    // stehen +350 pcm Graphit gegen −830 pcm Absorber, die Schnellabschaltung
    // wäre auch mit leerem Kern sofort negativ, und die Eigenheit, um die es
    // bei diesem Reaktortyp geht, gäbe es im Spiel nicht.
    const worth = sp.rodBanks[i].worth || 0;
    const fade = h <= span ? 1 : clamp((2 * span - h) / span, 0, 1);
    if (fade > 0) notYet += worth * rodWorthCurve(h) * fade;
  }
  return (sp.tip.worth_pcm * fBot * tip + notYet) * 1e-5;
}

/**
 * Zielwert des axialen Flussprofils.
 *
 * Ein einzonales Punktkinetikmodell kennt keine Achse. Statt die Engine auf
 * zwei Zonen umzubauen -- was alle drei Reaktortypen beträfe, obwohl nur einer
 * es braucht -- wird die Verteilung als eigener, langsamer Zustand geführt:
 * der Unterschied der Reaktivität zwischen oben und unten, geteilt durch eine
 * Steifigkeit. Xenon oben verschiebt den Fluss nach unten, eingefahrene Stäbe
 * (sie kommen von oben) ebenfalls.
 */
function _axialTarget(s, sp) {
  const wXe = sp.feedback.xenon_worth_pcm;
  const dXe = ((s.zTop ? s.zTop.X : 0) - (s.zBot ? s.zBot.X : 0)) * wXe;
  let meanRod = 0;
  for (let i = 0; i < s.rod.length; i++) meanRod += s.rod[i];
  meanRod /= Math.max(s.rod.length, 1);
  const push = sp.axial.rodPush_pcm * meanRod;
  return clamp((dXe + push) / sp.axial.stiffness_pcm, -0.5, 0.5);
}

function _subcooling(s, sp) {
  const W = Math.max(s.W_core, 1);
  const Wfw = clamp(s.W_fw, 0, W);
  const hSat = hf(s.p_drum);
  const hMix = (Wfw * H_FW + (W - Wfw) * hSat) / W;
  return clamp((hSat - hMix) / sp.coolant.cp, 0, 80);
}

function _void(s, sp) {
  const W = Math.max(s.W_core, 1);
  const G = W / sp.coolant.flowArea_m2;
  const qPerKg = (s.P_th * 1000) / W;
  const subPerKg = sp.coolant.cp * s.dTsub;
  const fBoil = clamp(1 - subPerKg / Math.max(qPerKg, 1e-3), 0.05, 0.98);
  return averageVoid(s.x_e, s.p_drum, G, fBoil);
}

function _cpr(s, sp, base) {
  const flow = clamp(s.W_core / sp.mcp.W0, 0.05, 1.3);
  const power = clamp(base.load, 0.02, 2);
  const q = clamp(1 - s.x_e / 0.30, 0.05, 1);
  return clamp(1.8 * Math.pow(flow, 0.5) * Math.pow(q, 0.35) / power, 0, 20);
}

export default { spec, hooks };
