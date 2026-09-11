// Druckwasserreaktor, an einen KONVOI angelehnt.
//
// 3850 MWth / 1400 MWe, vier Schleifen, 158 bar im Primärkreis, kein Sieden im
// Kern. Die Leistung kommt aus der Turbine: was die Turbine an Dampf zieht,
// kühlt den Primärkreis, und der Kern folgt über die negativen Rückkopplungen
// von selbst. Der Fahrer stellt nur nach.
//
// Das Spielprinzip dieses Typs ist die Zeitkonstante. Stäbe wirken in Sekunden,
// Bor in Minuten, Xenon in Stunden. Wer Bor dosiert, um Stabreserve
// zurückzugewinnen, arbeitet gegen eine Totzeit von drei Minuten -- und was er
// vor drei Minuten losgeschickt hat, kommt jetzt an.

import { Pump, Valve, TransportDelay, Lag } from '../sim/components.js';
import {
  RodController, PressurizerController, FeedwaterController, GovernorController,
} from '../sim/controllers.js';
import { tsat, psat, hg, hf, rhog, dpdT } from '../sim/steam.js';
import { clamp, toK } from '../sim/constants.js';
import { SEVERITY } from '../sim/trips.js';

export const spec = {
  id: 'pwr',
  P0_th: 3850,          // MW thermisch
  P0_e: 1400,           // MW elektrisch
  cycleEFPD: 450,

  beta: { boc: 0.0065, eoc: 0.0055 },
  Lambda: 2e-5,

  fuel: {
    mass_t: 103,
    cp: 300,            // J/kgK
    tau: 5.5,           // s, Brennstoff gegen Hüllrohr
    depositFraction: 0.974,
    T_melt: 3120,       // K
  },
  clad: { C_frac: 0.12, tau: 0.05, T_fail: 1477 },

  coolant: {
    W0: 20000,          // kg/s, vier Hauptkühlmittelpumpen
    cp: 5.4,            // kJ/kgK bei 155 bar, 310 °C
    T_in: toK(291),
    T_out: toK(326),
    p0: 158,            // bar
    mass: 12000,        // kg im Kernknoten
  },

  feedbacks: ['rods', 'doppler', 'mtc', 'xenon', 'samarium', 'boron', 'excess'],

  feedback: {
    // Bezugstemperatur ist die mittlere Brennstofftemperatur bei Volllast.
    // Wichtig ist nicht der Nullpunkt -- den fängt die Bor-Einstellung beim
    // Start ab -- sondern die Steigung. Aus ihr folgt der Leistungsdefekt von
    // Volllast auf Nullleistung, hier rund 1700 pcm.
    doppler_pcm_per_K: -1.9,
    doppler_T_ref: 1300,

    // α_M = −60 + 0,03·ppm. Bei 2000 ppm ist der Moderatorkoeffizient null --
    // ein frisch beladener Kern ist deutlich weniger gutmütig als einer am
    // Zyklusende.
    mtc_pcm_per_K: -60,
    mtc_pcm_per_K_per_ppm: 0.03,
    mtc_T_ref: toK(310),

    xenon_worth_pcm: 2800,
    samarium_worth_pcm: 600,

    boron_pcm_per_ppm: 8,
    boron_ref_ppm: 0,

    // Überschussreaktivität des frischen Kerns. Sie legt zusammen mit der
    // Borwirksamkeit die kritische Borkonzentration fest: bei Volllast mit
    // eingeschwungenem Xenon und Samarium landet sie hier bei rund 1200 ppm,
    // wie im Betrieb üblich. Über den Zyklus läuft sie auf null -- dann ist
    // auch das Bor verbraucht und der Kern am Ende.
    excess_pcm: 12985,
  },

  // Zwei Gruppen: die Regelgruppe fährt im Betrieb, die Abschaltgruppe steht
  // oben und ist die Reserve. Eine Schnellabschaltung wirft beide ein.
  rodBanks: [
    { id: 'ctrl', worth: 1500, speed: 0.0125, initial: 0.18 },
    { id: 'sd', worth: 5500, speed: 0.0125, initial: 0.0 },
  ],
  scram: { timeS: 2.2 },   // Schwerkraftfall, 90 % in gut zwei Sekunden

  primary: {
    volume_m3: 320,
    expansion_per_K: 0.0025,
    hotLegTau: 3.0,
    coldLegTau: 4.0,
    boronMass: 250000,       // kg Primärinventar für die Bormischung
    boronMakeupFlow: 5,      // kg/s
    boronMakeupPpm: 7000,
    boronMixTau: 180,        // s, bis eine Dosierung durchgemischt ist
  },

  pressurizer: {
    p0: 158,
    level0: 0.55,
    area_m2: 4.5,
    heaterMaxKW: 1800,
    C_bar: 26000,            // kJ je bar Druckänderung im Dampfraum
    surge_bar_per_m3: 0.55,
    porv: 162,
    safety: 171,
    lossKW: 140,
  },

  sg: {
    n: 4,
    p0: 64,
    UA: 132800,              // kW/K, primär gegen sekundär
    metalTau: 10,
    mass: 45000,             // kg Sekundärinventar gesamt
    cp: 5.0,                 // kJ/kgK
    T_fw: toK(218),
    W_steam0: 2061,          // kg/s, folgt aus der Waermebilanz
    level0: 0.5,
    massSpan: 18000,         // kg zwischen leerem und vollem Anzeigebereich
    shrinkSwell: 0.9,        // Ausschlag der Anzeige je relativer Druckänderung
  },

  turbine: {
    Cv: 57,
    strokeS: 4,
    // (h_g − h_f,Kondensat) · Faktor = spezifische Arbeit. So gewaehlt, dass
    // 3850 MWth bei Nenndruck genau 1400 MWe ergeben -- das ist der
    // Gesamtwirkungsgrad des Kreisprozesses, hier in einen Faktor gefasst.
    workFactor: 0.2568,
    bypassCv: 26,
    bypassStrokeS: 1.2,
  },

  // Kuehlwasser 15 °C, Graedigkeit 6 K, dazu die lastabhaengige Aufwaermung:
  // bei Volllast 33 °C Kondensationstemperatur und damit 0,05 bar.
  condenser: { T_cw: toK(15), pinch: 6, rise: 12, p0: 0.05 },

  mimic: 'mimic-pwr',

  trips: [
    { id: 'power_high', key: 'trip_power_high', severity: SEVERITY.TRIP,
      test: (s) => s.n > 1.12, delay_s: 0.4, action: 'scram' },
    // Die Periodenauslösung ist unterhalb des Leistungsbereichs gesperrt.
    // Im tief unterkritischen Kern treibt allein die Neutronenquelle die
    // Anzeige, und eine kurze positive Periode dort ist normal, nicht gefährlich.
    { id: 'period_short', key: 'trip_period_short', severity: SEVERITY.TRIP,
      test: (s, d) => s.n > 1e-3 && d.period > 0 && d.period < 10,
      delay_s: 0.5, action: 'scram' },
    { id: 'pzr_press_low', key: 'trip_pzr_press_low', severity: SEVERITY.TRIP,
      test: (s) => s.pzr_p < 132, delay_s: 1.0, action: 'scram' },
    { id: 'pzr_press_high', key: 'trip_pzr_press_high', severity: SEVERITY.TRIP,
      test: (s) => s.pzr_p > 166, delay_s: 1.0, action: 'scram' },
    { id: 'pzr_level_low', key: 'trip_pzr_level_low', severity: SEVERITY.WARN,
      test: (s) => s.pzr_L < 0.17, delay_s: 2 },
    { id: 'dnbr_low', key: 'trip_dnbr_low', severity: SEVERITY.TRIP,
      test: (s, d) => d.dnbr < 1.3, delay_s: 0.5, action: 'scram' },
    { id: 'sg_level_low', key: 'trip_sg_level_low', severity: SEVERITY.TRIP,
      test: (s) => s.L_sg < 0.25, delay_s: 2.0, action: 'scram' },
    { id: 'sg_level_high', key: 'alarm_sg_level_high', severity: SEVERITY.WARN,
      test: (s) => s.L_sg > 0.78, delay_s: 2.0 },
    { id: 'sg_press_high', key: 'alarm_sg_press_high', severity: SEVERITY.WARN,
      test: (s) => s.p_sg > 84, delay_s: 0.5 },
    { id: 'rcp_lost', key: 'trip_rcp_lost', severity: SEVERITY.TRIP,
      test: (s) => s.W_core < 0.6 * 20000, delay_s: 1.0, action: 'scram' },
    { id: 'subcool_low', key: 'alarm_subcool_low', severity: SEVERITY.WARN,
      test: (s, d) => d.subcooling < 8, delay_s: 2 },
    { id: 'porv_open', key: 'alarm_porv_open', severity: SEVERITY.INFO,
      test: (s) => s.porv > 0.01, delay_s: 0 },
    { id: 'turbine_trip', key: 'alarm_turbine_trip', severity: SEVERITY.WARN,
      test: (s) => s.turbineTripped, delay_s: 0 },
    { id: 'clad_temp', key: 'trip_clad_temp', severity: SEVERITY.TRIP,
      test: (s) => s.T_cl > 1477, delay_s: 0, action: 'scram' },
  ],
};

export const hooks = {
  /** Zustandsfelder, die nur dieser Typ hat. */
  extraState(s, sp, ctx) {
    s.C_B = 1000;              // ppm, wird von trim() gesetzt
    s.C_B_cmd = 1000;
    s.boronFlow = 0;           // >0 aufborieren, <0 verdünnen

    s.pzr_p = sp.pressurizer.p0;
    s.pzr_L = sp.pressurizer.level0;
    s.pzr_htr = 0;
    s.pzr_spray = 0;
    s.porv = 0;

    s.T_sgm = 0.5 * (sp.coolant.T_in + sp.coolant.T_out) - 12;
    s.p_sg = sp.sg.p0;
    s.M_sg = sp.sg.mass;
    s.L_sg = sp.sg.level0;
    s.W_steam = sp.sg.W_steam0;
    s.W_fw = sp.sg.W_steam0;
    s.gov = 0.8;
    s.bypass = 0;
    s.p_cond = sp.condenser.p0;
    s.turbineTripped = false;
    s.breaker = true;

    s.p_prim = sp.pressurizer.p0;
    s.P_demand = sp.P0_e;

    // Anlagenteile mit eigenem Gedächtnis.
    ctx.pumps = [0, 1, 2, 3].map(() => new Pump({ W0: sp.coolant.W0 / 4, coastTau: 14 }));
    ctx.govValve = new Valve(sp.turbine.strokeS, 0.8);
    ctx.bypassValve = new Valve(sp.turbine.bypassStrokeS, 0);
    ctx.hotLeg = new TransportDelay(sp.primary.hotLegTau, 0.05, sp.coolant.T_out);
    ctx.coldLeg = new TransportDelay(sp.primary.coldLegTau, 0.05, sp.coolant.T_in);
    ctx.boronMix = new Lag(sp.primary.boronMixTau, 1000);
    ctx.tAvgPrev = 0.5 * (sp.coolant.T_in + sp.coolant.T_out);

    // Temperaturprogramm: der Sollwert der Mitteltemperatur steigt mit der Last.
    // Der obere Wert MUSS die Mitteltemperatur sein, die sich bei Volllast aus
    // der Waermebilanz ergibt -- 0,5·(291 + 326,6) °C. Steht dort ein hoeherer
    // Wert, zieht die Regelung die Staebe bis zum Anschlag und faehrt den Kern
    // ueber die Nennleistung, ohne dass je ein Grenzwert verletzt wird.
    const tAvgFull = 0.5 * (sp.coolant.T_in + sp.coolant.T_out);
    ctx.rodCtl = new RodController({
      tAvgLow: sp.coolant.T_in, tAvgHigh: tAvgFull, deadbandK: 0.8, speed: 0.0125, bank: 0,
    });
    ctx.pzrCtl = new PressurizerController({
      pSet: sp.pressurizer.p0, heaterMaxKW: sp.pressurizer.heaterMaxKW,
    });
    ctx.fwCtl = new FeedwaterController({ levelSet: sp.sg.level0, W0: sp.sg.W_steam0 });
    ctx.govCtl = new GovernorController({
      mode: 'load', P0: sp.P0_e, posNominal: 0.79,
    });
  },

  /**
   * Anfangszustand aufs Gleichgewicht ziehen.
   *
   * Statt Startwerte zu raten, wird gerechnet: die Temperaturen folgen aus der
   * Wärmebilanz, und die Borkonzentration wird so gesetzt, dass die
   * Reaktivitätsbilanz null ergibt. Genau das macht ein Betrieb auch -- die
   * Borkonzentration IST das Ergebnis aller anderen Beiträge.
   */
  trim(s, sp, ctx, rx) {
    const n = s.n;
    const P = sp.P0_th * n;
    s.W_core = sp.coolant.W0;
    s.T_ci = sp.coolant.T_in;
    const dT = (P * 1000) / (s.W_core * sp.coolant.cp);
    s.T_co = s.T_ci + dT;
    const Tavg = 0.5 * (s.T_ci + s.T_co);
    s.T_mod = Tavg;
    s.T_cl = Tavg + (P * 1000 * sp.fuel.depositFraction) / ctx.UA_cc;
    s.T_f = s.T_cl + (P * 1000 * sp.fuel.depositFraction) / ctx.UA_fc;
    s.P_th = P;
    ctx.hotLeg.fill(s.T_co);
    ctx.coldLeg.fill(s.T_ci);
    ctx.tAvgPrev = Tavg;

    // Bor so wählen, dass ρ = 0. Genau das tut ein Betrieb auch: die kritische
    // Borkonzentration ist kein Sollwert, sondern das Ergebnis aller anderen
    // Beiträge. Der Borterm selbst ist linear, aber Bor verändert auch den
    // Moderatorkoeffizienten -- deshalb ein paar Durchgänge statt einem.
    const w = sp.feedback.boron_pcm_per_ppm * 1e-5;
    s.C_B = 0;
    for (let i = 0; i < 8; i++) {
      const rho = rx.compute(s, sp);
      if (Math.abs(rho) < 1e-7) break;
      s.C_B = clamp(s.C_B + rho / w, 0, 2400);
    }
    s.C_B_cmd = s.C_B;
    ctx.boronMix.set(s.C_B);
    rx.compute(s, sp);

    // Sekundärseite auf die abzuführende Leistung einstellen.
    s.p_sg = sp.sg.p0;
    // Im Beharrungszustand ist die Rohrmetalltemperatur genau die Hälfte des
    // Gesamtgefälles über der Sättigungstemperatur -- beide Hälften führen
    // dieselbe Leistung.
    s.T_sgm = tsat(s.p_sg) + (P * 1000) / (2 * sp.sg.UA);
    s.W_steam = (P * 1000) / (hg(s.p_sg) - _hfw(sp));
    s.W_fw = s.W_steam;
    s.P_e = (s.W_steam * (hg(s.p_sg) - hf(s.p_cond)) * sp.turbine.workFactor) / 1000;
    s.P_demand = s.P_e;
    ctx.fwCtl.pi.preset(0);
  },

  moderatorTemp(s, sp, Tc) { return Tc; },

  /** Primär- und Sekundärkreis. */
  stepLoop(s, sp, ctx, dt) {
    // ── Pumpen und Kerndurchsatz ─────────────────────────────────────────────
    let W = 0;
    for (const p of ctx.pumps) { p.step(dt); W += p.flow(0.04); }
    s.W_core = W;

    // ── Strangtemperaturen mit Laufzeit ──────────────────────────────────────
    const T_hotSG = ctx.hotLeg.push(s.T_co);
    const Tavg = 0.5 * (s.T_ci + s.T_co);

    // ── Dampferzeuger ────────────────────────────────────────────────────────
    const Tsat_sg = tsat(s.p_sg);
    // Rohrmetall zwischen beiden Seiten: es ist der Grund, warum eine Störung
    // im Primärkreis nicht sofort auf der Sekundärseite steht.
    const Tm = s.T_sgm;
    const UA2 = 2 * sp.sg.UA;     // halbe Strecke je Seite, in Reihe
    // Treibendes Gefälle auf der Primärseite ist die MITTLERE Rohrbündel-
    // temperatur, nicht die Eintrittstemperatur: das Wasser kühlt sich auf dem
    // Weg durch den Erzeuger um die volle Schleifenspreizung ab. Mit T_heiß
    // stünde hier das doppelte Gefälle und damit die doppelte Leistung -- der
    // Primärkreis wurde in der ersten Fassung so stark unterkühlt, dass der
    // Moderatorkoeffizient den Reaktor binnen Sekunden über die Leistungs-
    // auslösung trieb. Eingesetzt und nach q aufgelöst:
    //   q = UA2·(T_heiß − q/(2·W·c_p) − T_m)
    const Wcp = Math.max(W * sp.coolant.cp, 1);
    const qPrim = (UA2 * (T_hotSG - Tm)) / (1 + UA2 / (2 * Wcp));
    const qSec = UA2 * (Tm - Tsat_sg);
    s.T_sgm = Tm + ((qPrim - qSec) * dt) / (sp.sg.mass * 0.5 * sp.sg.cp);

    // Kalter Strang: was der Dampferzeuger entzieht, fehlt dem Rücklauf.
    const T_coldNew = T_hotSG - qPrim / Wcp;
    s.T_ci = ctx.coldLeg.push(T_coldNew);

    // ── Frischdampf ──────────────────────────────────────────────────────────
    const hfw = _hfw(sp);
    const W_gen = Math.max(qSec / Math.max(hg(s.p_sg) - hfw, 1), 0);

    ctx.govValve.demand = s.turbineTripped ? 0 : s.gov;
    ctx.govValve.step(dt);
    ctx.bypassValve.demand = s.bypass;
    ctx.bypassValve.step(dt);

    const dpTurb = Math.max(s.p_sg - s.p_cond, 0);
    const rhoS = rhog(s.p_sg);
    const W_t = ctx.govValve.flow(sp.turbine.Cv, rhoS, dpTurb);
    const W_bp = ctx.bypassValve.flow(sp.turbine.bypassCv, rhoS, dpTurb);
    s.W_steam = W_t + W_bp;

    // Druck aus der Energiebilanz des Sekundärinventars. Die Kapazität ist
    // M·c_p·dT_sat/dp -- dieselbe Wärme hebt den Druck bei 64 bar anders als
    // bei 88 bar, weil die Sättigungskurve dort flacher liegt.
    const C_p = sp.sg.mass * sp.sg.cp / Math.max(dpdT(s.p_sg), 1e-6);
    const qOut = s.W_steam * Math.max(hg(s.p_sg) - hfw, 1);
    s.p_sg = clamp(s.p_sg + ((qSec - qOut) * dt) / C_p, 1, 110);

    // Sicherheitsventile der Sekundärseite.
    if (s.p_sg > 88) {
      const relief = (s.p_sg - 88) * 400;
      s.p_sg -= (relief * Math.max(hg(s.p_sg) - hfw, 1) * dt) / C_p;
      s.M_sg -= relief * dt;
    }

    // ── Füllstand ────────────────────────────────────────────────────────────
    s.M_sg = Math.max(s.M_sg + (s.W_fw - s.W_steam) * dt, 1000);
    const Ltrue = clamp(0.5 + (s.M_sg - sp.sg.mass) / sp.sg.massSpan, 0, 1);
    // Schrumpfen und Quellen: fällt der Druck, bilden sich mehr Blasen und der
    // Füllstand steigt SCHEINBAR -- obwohl Wasser fehlt. Ohne diesen Term
    // fühlt sich die Speisewasserregelung falsch an, und der klassische
    // Bedienfehler nach einem Lastabwurf wäre gar nicht möglich.
    s.L_sg = clamp(Ltrue + sp.sg.shrinkSwell * (sp.sg.p0 - s.p_sg) / sp.sg.p0, 0, 1);

    // ── Druckhalter ──────────────────────────────────────────────────────────
    const dTavg = (Tavg - ctx.tAvgPrev) / dt;
    ctx.tAvgPrev = Tavg;
    // Ausdehnung des Primärinventars schiebt Wasser in den Druckhalter.
    const surge = sp.primary.volume_m3 * sp.primary.expansion_per_K * dTavg;   // m³/s
    s.pzr_L = clamp(s.pzr_L + (surge / sp.pressurizer.area_m2 / 12) * dt, 0, 1);

    const qNet = s.pzr_htr - s.pzr_spray * 2600 - sp.pressurizer.lossKW;
    s.pzr_p += ((qNet * dt) / sp.pressurizer.C_bar)
             + sp.pressurizer.surge_bar_per_m3 * surge * dt;

    // Abblaseventil und Sicherheitsventile.
    s.porv = s.pzr_p > sp.pressurizer.porv ? 1 : 0;
    if (s.porv) s.pzr_p -= (s.pzr_p - sp.pressurizer.porv) * 0.6 * dt;
    if (s.pzr_p > sp.pressurizer.safety) {
      s.pzr_p -= (s.pzr_p - sp.pressurizer.safety) * 2.5 * dt;
    }
    s.pzr_p = clamp(s.pzr_p, 1, 200);
    s.p_prim = s.pzr_p;

    // ── Bor ──────────────────────────────────────────────────────────────────
    if (s.boronFlow !== 0) {
      const Wm = sp.primary.boronMakeupFlow * Math.sign(s.boronFlow);
      const Cm = s.boronFlow > 0 ? sp.primary.boronMakeupPpm : 0;
      s.C_B_cmd = clamp(
        s.C_B_cmd + ((Math.abs(Wm) * (Cm - s.C_B_cmd)) / sp.primary.boronMass) * dt,
        0, 2400);
    }
    // Die Mischung braucht drei Minuten. Was jetzt dosiert wird, wirkt später --
    // und was vor drei Minuten dosiert wurde, wirkt jetzt.
    s.C_B = ctx.boronMix.step(s.C_B_cmd, dt);

    // ── Turbine, Kondensator, Netz ───────────────────────────────────────────
    s.p_cond = _condenserPressure(sp, s.W_steam);
    const wSpec = (hg(s.p_sg) - hf(s.p_cond)) * sp.turbine.workFactor;
    s.P_e = s.breaker && !s.turbineTripped ? (W_t * wSpec) / 1000 : 0;
  },

  /** Regler: Stäbe, Druckhalter, Speisewasser, Turbinenventil. */
  stepControls(s, sp, ctx, dt) {
    const Tavg = 0.5 * (s.T_ci + s.T_co);
    const load = clamp(s.P_demand / sp.P0_e, 0, 1);

    if (!s.scram.active) {
      s.rodDmd[0] = clamp(s.rodDmd[0] + ctx.rodCtl.step(Tavg, load, dt), 0, 1);
    }

    const pz = ctx.pzrCtl.step(s.pzr_p);
    s.pzr_htr = pz.heater;
    s.pzr_spray = pz.spray;

    s.W_fw = ctx.fwCtl.step(s.L_sg, s.W_steam, dt);

    s.gov = ctx.govCtl.step(s.P_e, s.P_demand, s.p_sg, dt);

    // Umleitstation: nimmt den Dampf auf, den die Turbine nicht mehr nimmt.
    // Ohne sie endet jeder Turbinenschnellschluss am Sicherheitsventil.
    //
    // Der Ansprechpunkt liegt bewusst 8 bar ueber dem Betriebsdruck. Bei 4 bar
    // griff sie schon in den normalen Regelvorgang ein: der Turbinenregler
    // hob den Druck beim Nachstellen kurz ueber die Schwelle, die Umleitung
    // blies Dampf an der Turbine vorbei, und die Leistung blieb dauerhaft 3 %
    // unter dem Sollwert -- bei voller thermischer Leistung.
    const dumpSet = sp.sg.p0 + 8;
    s.bypass = s.p_sg > dumpSet ? clamp((s.p_sg - dumpSet) / 8, 0, 1) : 0;
  },

  onScram(s, sp, ctx) {
    s.turbineTripped = true;
    ctx.govCtl.trip();
    s.gov = 0;
    s.breaker = false;
  },

  /** Anzeigewerte, die nur dieser Typ kennt. */
  derived(s, sp, ctx, base) {
    return {
      dnbr: _dnbr(s, sp, base),
      p_sg: s.p_sg,
      L_sg: s.L_sg,
      W_steam: s.W_steam,
      W_fw: s.W_fw,
      gov: s.gov,
      bypass: s.bypass,
      p_cond: s.p_cond,
      pzr_p: s.pzr_p,
      pzr_L: s.pzr_L,
      C_B: s.C_B,
      C_B_cmd: s.C_B_cmd,
      T_sgm: s.T_sgm,
      pumpStates: ctx.pumps.map((p) => p.state),
      shutdownMargin: _shutdownMargin(s, sp, ctx),
    };
  },
};

// ── Hilfsfunktionen ───────────────────────────────────────────────────────────

/** Enthalpie des Speisewassers. */
function _hfw(sp) {
  // Näherung über die Flüssigkeitsenthalpie bei Speisewassertemperatur.
  return 4.2 * (sp.sg.T_fw - 273.15);
}

/** Kondensatordruck aus Kühlwassertemperatur, Last und Grädigkeit. */
function _condenserPressure(sp, W_steam) {
  const load = clamp(W_steam / sp.sg.W_steam0, 0, 1.2);
  const T = sp.condenser.T_cw + sp.condenser.pinch + (sp.condenser.rise || 12) * load;
  return clamp(psat(T), 0.02, 1.5);
}

/**
 * Abstand zum Siedekrisenpunkt, als monotone Kennzahl statt echter Korrelation.
 *
 * Eine W-3- oder EPRI-Korrelation bräuchte örtliche Massenstromdichte,
 * Heißkanalfaktoren und Gitterabstandshalter -- Daten, die dieses Spiel nicht
 * hat. Die Form ist die richtige: mehr Durchsatz hilft, mehr Leistung schadet,
 * weniger Unterkühlung schadet. Die Zahl ist so skaliert, dass sie bei Volllast
 * und Nenndurchsatz auf den üblichen Auslegungswert von etwa 2,3 kommt und bei
 * 1,3 die Abschaltung auslöst.
 */
function _dnbr(s, sp, base) {
  const flow = clamp(s.W_core / sp.coolant.W0, 0.05, 1.3);
  const power = clamp(base.load, 0.02, 2);
  const sub = clamp(base.subcooling / 20, 0.05, 2);
  return clamp(2.3 * Math.pow(flow, 0.6) * Math.pow(sub, 0.25) / power, 0, 20);
}

/** Abschaltreserve: wie viel negative Reaktivität steckt noch in den Stäben. */
function _shutdownMargin(s, sp, ctx) {
  let left = 0;
  for (let i = 0; i < sp.rodBanks.length; i++) {
    left += sp.rodBanks[i].worth * (1 - s.rod[i]);
  }
  return left;
}

export default { spec, hooks };
