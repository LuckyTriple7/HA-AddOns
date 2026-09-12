// Siedewasserreaktor.
//
// 3840 MWth / 1344 MWe, ein Kreislauf: der im Kern erzeugte Dampf geht direkt
// zur Turbine. Kein Dampferzeuger, kein Druckhalter, kein Bor im Betrieb.
//
// Das Spielprinzip ist ein anderes als beim Druckwasserreaktor. Dort stellt
// die Turbine die Leistung und der Kern folgt. Hier ist es umgekehrt: das
// Regelventil hält den Dampfdruck konstant, und die Leistung macht der Kern --
// über den Umwälzstrom. Mehr Durchsatz schwemmt die Dampfblasen aus, mehr
// Moderator heißt mehr Reaktivität, und die Leistung steigt binnen Sekunden.
// Zwischen 60 und 110 % Durchsatz liegen rund 30 % Leistung, ohne dass ein Stab
// sich bewegt.
//
// Der Preis dafür ist die Instabilität. Bei viel Leistung und wenig Durchsatz
// koppeln Dampfgehalt, Druckverlust und Durchsatz zu einer Dichtewelle, die
// sich aufschaukelt statt abzuklingen. Dieser Bereich ist im
// Leistungs-Durchsatz-Kennfeld gesperrt, und das Spiel bildet ihn nach.

import { Pump, Valve, Lag, coldStopPumps } from '../sim/components.js';
import { FeedwaterController, GovernorController, RodController } from '../sim/controllers.js';
import { tsat, psat, hg, hf, hfg, rhog, dpdT, averageVoid } from '../sim/steam.js';
import { clamp, toK, relax } from '../sim/constants.js';
import { SEVERITY } from '../sim/trips.js';

const P0 = 70.7;                     // bar, Domdruck
const T_FW = toK(216);
const H_FW = 4.2 * 216;              // kJ/kg

export const spec = {
  id: 'bwr',
  P0_th: 3840,
  P0_e: 1344,
  cycleEFPD: 500,

  beta: { boc: 0.0056, eoc: 0.0050 },
  Lambda: 4e-5,

  fuel: {
    mass_t: 140,
    cp: 300,
    tau: 6.0,
    depositFraction: 0.974,
    T_melt: 3120,
  },
  clad: { C_frac: 0.12, tau: 0.05, T_fail: 1477 },

  coolant: {
    W0: 13000,          // kg/s Kerndurchsatz bei Nennbedingungen
    cp: 4.9,
    T_in: tsat(P0) - 12,
    T_out: tsat(P0),
    p0: P0,
    mass: 20000,
    flowArea_m2: 10.0,  // fuer die Massenstromdichte im Drift-Flux-Modell
  },

  feedbacks: ['rods', 'doppler', 'void', 'xenon', 'samarium', 'excess'],

  feedback: {
    doppler_pcm_per_K: -2.0,
    doppler_T_ref: 1150,

    // Stark negativ -- das ist die Sicherheitsreserve dieses Typs und
    // gleichzeitig sein Regelorgan.
    void_pcm_per_pct: -100,
    // Blasenanteil im Nennbetrieb -- der Nullpunkt dieses Beitrags.
    void_ref: 0.385,

    xenon_worth_pcm: 2600,
    samarium_worth_pcm: 550,

    // Der Ueberschuss wird hier nicht von Bor gehalten, sondern von den
    // Staeben und vom abbrennbaren Gift im Brennstoff. Uebrig bleibt der
    // Anteil, den die Regelgruppe traegt -- gut 800 pcm bei Nennleistung.
    // trim() sucht deshalb die Stabstellung statt einer Borkonzentration.
    excess_pcm: 3900,
  },

  // Steuerstaebe fahren von UNTEN ein: oben sitzt der Dampfabscheider.
  // Fuer die Rechnung ist das gleichgueltig, fuer das Fliessbild nicht.
  rodBanks: [
    { id: 'ctrl', worth: 2600, speed: 0.008, initial: 0.35 },
    { id: 'sd', worth: 5200, speed: 0.008, initial: 0.0 },
  ],
  // Hydraulisch eingeschossen, gegen den Kerndruck.
  scram: { timeS: 2.7, labelKey: 'btn_scram_resa', titleKey: 'btn_scram_resa_title' },

  recirc: {
    W0: 13000,
    min: 0.45,
    max: 1.10,
    tau: 6,               // s, Hochlauf der Umwaelzpumpen
    coastTau: 5,
  },

  vessel: {
    p0: P0,
    mass: 180000,          // kg Wasserinventar im Druckbehaelter
    cp: 5.2,
    level0: 0.5,
    massSpan: 40000,
    shrinkSwell: 1.6,      // staerker als beim DWR: der Kern selbst siedet
    // Blasenkollaps je bar/s Druckanstieg. Bei einer Frischdampf-Absperrung
    // steigt der Druck mit rund 2,5 bar/s, das sind gut 4 Prozentpunkte
    // Blasenanteil und damit rund 400 pcm positive Reaktivitaet.
    voidCollapse: 0.017,
    // Kernfreilegung, siehe coreCoolant(). mUncoverStart liegt bewusst weit
    // unter der Anzeige-Untergrenze (L_rpv erreicht 0 schon bei 160 000 kg) --
    // der Bediener hat also Vorwarnzeit, bevor die Dampfkuehlung tatsaechlich
    // einsetzt. mUncoverFloor liegt knapp ueber dem Boden von M_rpv (20 000 kg).
    mUncoverStart: 90000,
    mUncoverFloor: 25000,
    // Temperaturhub über die Sättigung, den die reine Dampfkühlung bei
    // vollständig freiliegendem Kern erreicht -- deutlich über der
    // Hüllrohrgrenze (1204 °C), damit Nachzerfallswärme ohne Bedeckung
    // tatsächlich zum Hüllrohrversagen führt und nicht in einem Gleich-
    // gewicht knapp darunter steckenbleibt.
    dryOverheatK: 3200,
    T_fw: T_FW,
    W_steam0: 2059,
    subcool0: 12,
  },

  turbine: {
    Cv: 55,
    strokeS: 3,
    // So gewaehlt, dass 3840 MWth bei Nenndruck 1344 MWe ergeben -- der
    // Gesamtwirkungsgrad von 35 %, in einen Faktor gefasst.
    workFactor: 0.2477,
    bypassCv: 30,
    bypassStrokeS: 0.8,
  },

  condenser: { T_cw: toK(15), pinch: 6, rise: 12, p0: 0.05 },

  // Notkondensator (Isolation Condenser). Reiner Naturumlauf-Wärmetauscher:
  // Dampf aus dem Dom kondensiert in einem Vorratsbehälter oberhalb des
  // Kerns, das Kondensat läuft von selbst zurück -- keine Pumpe nötig. Er
  // schaltet sich bei Isolierung (SCRAM + geschlossene Frischdampf-
  // Absperrung) automatisch zu und schluckt die Nachzerfallswärme, solange
  // Vorrat und Gleichstrom für die Ventile reichen. W0 ist Dampf-Äquivalent
  // in kg/s, deutlich über der anfänglichen Nachzerfallswärme (~7 % P0_th)
  // ausgelegt -- genau deshalb hätte er im Original gereicht.
  ic: { W0: 130, enduranceS: 7200 },

  // Löschwassereinspeisung als letzter Handgriff: kein Motor, keine
  // Elektronik, funktioniert auch im vollständigen Stromausfall -- dafür
  // viel weniger Durchsatz als die reguläre Speisewasseranlage.
  fireInj: { W0: 35 },

  // Sicherheitsbehälter (Druckkammer + Kondensationskammer). Baut sich aus
  // dem Sicherheitsventil-Dampf auf, der in die Kondensationskammer bläst --
  // genau der Pfad, über den bei einer Isolierung Wärme den Reaktor
  // überhaupt noch verlässt. capacity ist die Dampfmasse (kg-äquivalent),
  // die den Druck von p0 auf designLimit hebt.
  containment: { p0: 1.05, capacity: 2600, designLimit: 4.3, ventCv: 9 },

  // Wasserstoff aus der Zirkon-Wasser-Reaktion. Setzt oberhalb von 1200 °C
  // Hüllrohrtemperatur ein, lange bevor der Brennstoff selbst schmilzt --
  // historisch genau der Punkt, an dem Fukushima-1 die Hülle verlor, ohne
  // dass der Kern schon "zerstört" im Sinne der Enthalpie-Grenze war.
  h2: { onsetK: toK(1200), rate: 0.012 },

  // Instabilitaet: Kennzahl S = Leistung / relativer Durchsatz.
    // Ansprechwert der Schwingungsueberwachung. Bewusst bei 22 % und nicht bei
  // 30 %: der Grenzzyklus begrenzt sich zwar selbst -- die schwingende Leistung
  // treibt ueber den Blasenanteil die mittlere Leistung herunter, damit sinkt
  // die Kennzahl und die Schwingung klingt wieder ab -- aber er tut das erst
  // bei knapp 30 % Ausschlag. Darauf zu setzen waere kein Sicherheitskonzept.
  stability: { sThreshold: 1.2, drSlope: 1.2, drBase: 0.2, freqHz: 0.5, oprm: 0.22 },

  // Bei siedenden Kernen heisst die Kennzahl nicht DNBR, sondern CPR --
  // kritisches Leistungsverhaeltnis. Im Kern siedet es ohnehin ueberall;
  // gefragt ist, wieviel Leistung bis zur Austrocknung fehlt.
  marginKey: 'val_cpr',

  // Domdruck-Rundinstrument. Nennwert 70,7 bar, Auslösung bei 78,5 -- eigene
  // Skala statt der DWR-Vorgabe (100-180 bar), sonst stünde die Nadel im
  // sauberen Volllastbetrieb dauerhaft unten im roten Bereich.
  pressureGauge: { min: 40, max: 90, bands: [[40, 58, 'warn'], [58, 76, 'ok'], [76, 90, 'danger']] },

  // Welches Fließbild-Bauteil zu welcher Meldung gehört. Der Siedewasser-
  // reaktor zeichnet Kern, Fallraum und Dampfraum als EIN Bauteil (rpv) --
  // anders als beim Druckwasserreaktor gibt es hier keinen eigenen Druck-
  // halter oder Dampferzeuger, die das trennen würden.
  alarmComponents: {
    power_high: 'rpv', period_short: 'rpv', oprm: 'rpv', instability: 'rpv',
    dome_press_high: 'rpv', level_low: 'rpv', level_high: 'rpv', srv_open: 'rpv', clad_temp: 'rpv',
    recirc_low: 'rcp',
    turbine_trip: 'gen',
    cont_press_high: 'rpv', h2_critical: 'rpv',
  },

  mimic: 'mimic-bwr',

  trips: [
    { id: 'power_high', key: 'trip_power_high', severity: SEVERITY.TRIP,
      test: (s) => s.n > 1.18, delay_s: 0.3, action: 'scram' },
    // Zwei Sekunden Verzoegerung statt einer halben. In der Instabilitaetszone
    // schwingt die Leistung mit rund 0,5 Hz; die gemessene Periode geht dabei
    // in jedem Aufwaertsast kurz unter zehn Sekunden. Mit kurzer Verzoegerung
    // loeste deshalb die Periodenueberwachung aus, bevor die eigentlich
    // zustaendige Schwingungsueberwachung ueberhaupt ansprach -- und der
    // Spieler haette nie gesehen, was ihn erwischt hat.
    { id: 'period_short', key: 'trip_period_short', severity: SEVERITY.TRIP,
      test: (s, d) => s.n > 1e-3 && d.period > 0 && d.period < 10,
      delay_s: 2.0, action: 'scram' },
    { id: 'dome_press_high', key: 'trip_dome_press_high', severity: SEVERITY.TRIP,
      test: (s) => s.p_dome > 78.5, delay_s: 0.5, action: 'scram' },
    { id: 'level_low', key: 'trip_level_low', severity: SEVERITY.TRIP,
      test: (s) => s.L_rpv < 0.25, delay_s: 1.0, action: 'scram' },
    { id: 'level_high', key: 'alarm_level_high', severity: SEVERITY.WARN,
      test: (s) => s.L_rpv > 0.78, delay_s: 2.0 },
    { id: 'oprm', key: 'trip_oprm', severity: SEVERITY.TRIP,
      test: (s, d) => d.oscAmp > 0.22, delay_s: 0.2, action: 'scram' },
    { id: 'instability', key: 'alarm_instability', severity: SEVERITY.WARN,
      test: (s, d) => d.decayRatio > 0.8, delay_s: 1.0 },
    { id: 'recirc_low', key: 'alarm_recirc_low', severity: SEVERITY.WARN,
      test: (s, d) => s.W_core < 0.5 * 13000 && s.n > 0.4, delay_s: 1.0 },
    { id: 'msiv', key: 'alarm_msiv_closed', severity: SEVERITY.WARN,
      test: (s) => s.msiv < 0.5, delay_s: 0 },
    { id: 'srv_open', key: 'alarm_srv_open', severity: SEVERITY.INFO,
      test: (s) => s.srv > 0.01, delay_s: 0 },
    { id: 'turbine_trip', key: 'alarm_turbine_trip', severity: SEVERITY.WARN,
      test: (s) => s.turbineTripped, delay_s: 0 },
    { id: 'clad_temp', key: 'trip_clad_temp', severity: SEVERITY.TRIP,
      test: (s) => s.T_cl > 1477, delay_s: 0, action: 'scram' },
    { id: 'cont_press_high', key: 'alarm_cont_press_high', severity: SEVERITY.WARN,
      test: (s, d) => d.pCont !== undefined && d.pCont > 3.5, delay_s: 2.0 },
    { id: 'h2_critical', key: 'alarm_h2_critical', severity: SEVERITY.WARN,
      test: (s, d) => d.h2Mass !== undefined && d.h2Mass > 40, delay_s: 2.0 },
  ],
};

export const hooks = {
  extraState(s, sp, ctx) {
    s.p_dome = sp.vessel.p0;
    s.L_rpv = sp.vessel.level0;
    s.M_rpv = sp.vessel.mass;
    s.W_rec = sp.recirc.W0;
    s.recircDmd = 1.0;
    s.x_e = 0;
    s.alphaBar = sp.feedback.void_ref;
    s.dTsub = sp.vessel.subcool0;
    s.W_steam = sp.vessel.W_steam0;
    s.W_fw = sp.vessel.W_steam0;
    s.gov = 0.8;
    s.bypass = 0;
    s.srv = 0;
    s.msiv = 1;
    s.p_cond = sp.condenser.p0;
    s.turbineTripped = false;
    s.breaker = true;
    s.p_prim = sp.vessel.p0;
    s.P_demand = sp.P0_e;

    // Schwingungszustand der Dichtewelle.
    s.osc = 0;
    s.oscV = 0;

    // Stromversorgung -- im Normalbetrieb immer da. Eine Störung (Station-
    // Blackout) setzt beides auf false; ohne Gleichstrom fallen die
    // Notkondensator-Ventile in ihre sichere Stellung: ZU, unbemerkt, weil
    // dieselbe Störung auch die Anzeigen mitreißt.
    s.acPower = true;
    s.dcPower = true;

    // Notkondensator. icDemand ist die Bedienerabsicht (Automatik/Auf per
    // Default), icOpen die tatsächliche Ventilstellung -- die beiden fallen
    // auseinander, sobald der Gleichstrom fehlt.
    s.icDemand = 1;
    s.icOpen = false;
    s.icWater = 1.0;

    // Löschwassereinspeisung: von Hand, ohne jede Elektronik.
    s.fireInjOn = false;

    // Sicherheitsbehälter.
    s.contMass = 0;
    s.pCont = sp.containment.p0;
    s.contVentOpen = false;
    s.contFailed = false;

    // Wasserstoff aus der Hüllrohrreaktion, in kg (grobe Näherung).
    s.h2Mass = 0;
    s.h2Exploded = false;

    ctx.recircPump = new Pump({
      W0: sp.recirc.W0, coastTau: sp.recirc.coastTau, rampTau: sp.recirc.tau,
    });
    // Kaltstart: Umwaelzpumpe steht, der Spieler schaltet sie selbst zu --
    // genauso wie er selbst die Staebe zieht. Nur Naturumlauf bis dahin.
    if (ctx.cold) coldStopPumps(ctx.recircPump);
    ctx.govValve = new Valve(sp.turbine.strokeS, 0.8);
    ctx.bypassValve = new Valve(sp.turbine.bypassStrokeS, 0);
    ctx.voidLag = new Lag(1.0, sp.feedback.void_ref);
    ctx.dpLag = new Lag(0.3, 0);     // geglaettete Druckaenderungsrate
    ctx.pPrev = sp.vessel.p0;
    ctx.decayRatio = 0.2;

    ctx.rodCtl = new RodController({
      tAvgLow: tsat(sp.vessel.p0), tAvgHigh: tsat(sp.vessel.p0), deadbandK: 99, bank: 0,
    });
    // Beim Siedewasserreaktor regelt die Stabgruppe nicht auf eine
    // Mitteltemperatur -- die ist durch den Druck festgenagelt. Die Automatik
    // ist deshalb aus; geregelt wird ueber den Umwaelzstrom.
    ctx.rodCtl.auto = false;
    // Kein Regler fuehrt hier die Staebe -- deshalb zeigt das Kern-Panel auch
    // keinen Automatik-Schalter dafuer. Das Stellglied ist der Umwaelzstrom.
    ctx.rodAutoCtl = null;

    ctx.fwCtl = new FeedwaterController({
      levelSet: sp.vessel.level0, W0: sp.vessel.W_steam0, kp: 2.0, ki: 0.04,
    });
    ctx.govCtl = new GovernorController({
      mode: 'pressure', pSet: sp.vessel.p0, P0: sp.P0_e, posNominal: 0.8,
      kp: 0.9, ki: 0.35, trim: 0.5,
    });
  },

  trim(s, sp, ctx, rx) {
    const n = s.n;
    const P = sp.P0_th * n;
    s.W_core = sp.recirc.W0;
    s.W_rec = sp.recirc.W0;
    s.p_dome = sp.vessel.p0;
    s.p_prim = sp.vessel.p0;

    const Tsat = tsat(s.p_dome);
    s.W_steam = (P * 1000) / (hg(s.p_dome) - H_FW);
    s.W_fw = s.W_steam;
    s.dTsub = _subcooling(s, sp);
    s.T_ci = Tsat - s.dTsub;
    s.T_co = Tsat;
    s.T_mod = Tsat;
    s.x_e = clamp(s.W_steam / s.W_core, 0, 1);
    // P_th muss vor _void stehen: die Siedezone folgt aus dem Verhaeltnis von
    // zugefuehrter Waerme zu Unterkuehlung. Stand P_th hier noch auf null, kam
    // ein Blasenanteil von 2 % heraus statt 38 %, und der Kern startete fast
    // zwei Dollar ueberkritisch.
    s.P_th = P;
    s.alphaBar = _void(s, sp);
    ctx.voidLag.set(s.alphaBar);
    // Kein Nachziehen von sp.feedback.void_ref an dieser Stelle: die
    // Beitragsregistry hat den Bezugswert beim Bauen uebernommen, eine
    // spaetere Aenderung am gemeinsam genutzten Typdatenobjekt wirkt nicht
    // mehr -- und wuerde bei zwei gleichzeitigen Laeufen auch den anderen
    // treffen. Der Bezugswert steht fest in der Typdatei, der kleine
    // Restbeitrag wird von der Stabstellung aufgenommen.

    // Bezugstemperatur der Brennstoffkette ist die MITTLERE Kuehlmittel-
    // temperatur, so wie die Engine sie im Rechenschritt bildet -- nicht die
    // Saettigungstemperatur. Der Unterschied betraegt nur die halbe
    // Unterkuehlung, aber er landet unverduennt in der Doppler-Rueckkopplung,
    // und beim RBMK mit seinem fast neutralen Leistungskoeffizienten wurden
    // daraus fuenf Prozent Leistungssprung in der ersten Minute.
    const Tbase = Tsat - 0.5 * s.dTsub;
    s.T_cl = Tbase + (P * 1000 * sp.fuel.depositFraction) / ctx.UA_cc;
    s.T_f = s.T_cl + (P * 1000 * sp.fuel.depositFraction) / ctx.UA_fc;

    if (ctx.cold) {
      // Kaltstart: ALLE Bankstellungen drin stehen lassen, nicht nur die
      // Regelbank -- die Abschaltbank steht sonst auf ihrem Vollast-Anfangs-
      // wert (ganz draussen) und macht den Kern trotz eingefahrener Regelbank
      // deutlich UEBERkritisch. Der Spieler zieht selbst, bis er kritisch wird.
      for (let i = 0; i < s.rod.length; i++) { s.rod[i] = 1; s.rodDmd[i] = 1; }
      // _void() lieferte eben (Zeile 339) einen Blasenanteil nahe null, weil
      // bei n ≈ 0 noch nichts siedet -- witzigerweise genau der Fall aus dem
      // Kommentar oben ("startete fast zwei Dollar ueberkritisch"), nur ohne
      // den rettenden P_th-Ramp direkt danach. Der Bezugswert der Rueck-
      // kopplung gilt fuer Betrieb bei Nennlast, nicht fuer einen Kern, der
      // noch gar nicht kritisch ist -- deshalb hier auf den Referenzwert
      // zurueckgesetzt, denselben, den extraState() schon als Anfangswert
      // eingetragen hatte. Sobald der Spieler den Kern hochfaehrt, uebernimmt
      // wieder die echte Formel.
      s.alphaBar = sp.feedback.void_ref;
      ctx.voidLag.set(s.alphaBar);
      rx.compute(s, sp);
    } else {
      // Kritisch wird hier ueber die Stabstellung, nicht ueber Bor. Die
      // Stabwirksamkeit ist nicht linear (S-Kurve), also Bisektion statt
      // Division.
      let lo = 0, hi = 1;
      for (let i = 0; i < 60; i++) {
        const mid = 0.5 * (lo + hi);
        s.rod[0] = mid;
        // Mehr Einfahrt heisst weniger Reaktivitaet.
        if (rx.compute(s, sp) > 0) lo = mid; else hi = mid;
      }
      s.rod[0] = 0.5 * (lo + hi);
      s.rodDmd[0] = s.rod[0];
      rx.compute(s, sp);
    }

    s.P_e = (s.W_steam * (hg(s.p_dome) - hf(s.p_cond)) * sp.turbine.workFactor) / 1000;
    s.P_demand = s.P_e;
    ctx.fwCtl.pi.preset(0);
  },

  /**
   * Siedender Kern: die Austrittstemperatur ist die Sättigungstemperatur, die
   * Wärme geht in den Dampfgehalt. Läuft in den Kinetik-Untertakten.
   */
  coreCoolant(s, sp, ctx, qCoolKW, h) {
    const Tsat = tsat(s.p_dome);

    // Kernfreilegung: solange genug Wasser im Behaelter steht, siedet der
    // Kern und haelt seine Austrittstemperatur an der Saettigung fest, ganz
    // gleich wie klein der Durchsatz ist -- Sieden ist ein sehr guter
    // Waermeuebergang. Faellt der Fuellstand unter die obere Kernkante,
    // kuehlt dort nur noch vorbeistroemender Dampf, und der Waermeuebergang
    // bricht auf einen Bruchteil ein. covered nutzt die RAW-Masse (M_rpv),
    // nicht die auf 0..1 gestauchte Anzeigegroesse L_rpv -- die ist am
    // unteren Ende laengst bei 0, waehrend physisch noch Wasser im
    // Ringraum steht.
    const covered = clamp((s.M_rpv - sp.vessel.mUncoverFloor) /
      (sp.vessel.mUncoverStart - sp.vessel.mUncoverFloor), 0, 1);
    // Bewusst KEIN Ziel aus qCoolKW hergeleitet: qCoolKW ist bereits das
    // Ergebnis von UA_cc·(T_cl−T_cool) aus dem VORIGEN Schritt -- ein Ziel,
    // das davon selbst wieder abhaengt, pendelt sich zirkulaer irgendwo
    // unterhalb der Grenztemperatur ein, sobald T_cl an T_cool heranrueckt,
    // und die Nachzerfallswaerme "findet" scheinbar von selbst ein
    // Gleichgewicht, das keins ist. dryOverheatK ist stattdessen ein fester
    // Wert: voll frei liegend strebt die Kuehlmitteltemperatur so weit über
    // die Saettigung, dass sie über die Huellrohrgrenze hinaustreibt --
    // genau das Szenario, das Fukushima-1 zeigt: kein Leistungsausflug,
    // reiner Kuehlungsverlust.
    const dryTarget = Tsat + sp.vessel.dryOverheatK;
    const coolTarget = Tsat + (1 - covered) * (dryTarget - Tsat);
    // Bedeckt reagiert die Saettigungstemperatur sofort (Sieden ist traege-
    // frei), unbedeckt braucht die Dampfkuehlung ein paar Minuten, um sich
    // einzustellen -- beides ueber dieselbe relax()-Zeitkonstante, nur nach
    // covered gewichtet.
    s.T_co = relax(s.T_co, coolTarget, h, 3.0 + (1 - covered) * 180);
    s.T_mod = Tsat;
    // Eintritt: die Unterkuehlung folgt der Mischung aus Umwaelzwasser und
    // Speisewasser, aber traege -- der Weg durch den Fallraum dauert. Sobald
    // der Kern ueberwiegend frei liegt, verliert "Eintritt" seinen Sinn --
    // dieselbe Dampfkuehlung erfasst dann den ganzen Kanal, Ein- und Austritt
    // gleichermassen. Ohne das hier wuerde die generische T_cool =
    // 0,5·(T_ci+T_co) der Motorengine die Kernfreilegung zur Haelfte wieder
    // wegmitteln, weil T_ci stur an der Saettigung haengen bliebe.
    s.T_ci = relax(s.T_ci, covered > 0.5 ? (Tsat - s.dTsub) : coolTarget, h, 3.0 + (1 - covered) * 180);

    const W = Math.max(s.W_core, 1);
    const qSub = W * sp.coolant.cp * Math.max(Tsat - s.T_ci, 0);
    // Bewusst NICHT mit covered multipliziert: der noch bedeckte Teil des
    // Kerns siedet unabhaengig davon weiter, wieviel oben schon frei liegt --
    // sonst wuerde ein einsetzender Kernfreilegung den Massenverlust
    // druckseitig wieder ABBREMSEN, statt ihn (wie in Wirklichkeit) unbeirrt
    // weiterlaufen zu lassen, waehrend zusaetzlich die Huellrohrtemperatur
    // ueber T_co/dryTarget hochlaeuft.
    const qBoil = Math.max(qCoolKW - qSub, 0);
    s.x_e = clamp(qBoil / (W * hfg(s.p_dome)), 0, 1);

    // Blasenkollaps bei schneller Druckerhoehung.
    //
    // Die quasistationaere Bilanz oben sieht nur das Gleichgewicht: so viel
    // Waerme, so viel Dampf. Sie kann nicht sehen, dass ein schneller
    // Druckanstieg den bereits vorhandenen Dampf zusammendrueckt und teilweise
    // kondensiert -- der Dampfinhalt des Kerns kann sich in Sekundenbruchteilen
    // gar nicht so aendern, wie die Bilanz es vorgibt.
    //
    // Genau dieser Effekt ist die klassische Druckstoerung des
    // Siedewasserreaktors: Frischdampf absperren, Druck steigt, Blasen fallen
    // zusammen, mehr Moderator, POSITIVE Reaktivitaet. Ohne den Term ging in
    // der ersten Fassung die Leistung bei einer Absperrung zurueck statt hoch --
    // der Reaktor haette sich falsch herum verhalten, und zwar bei genau der
    // Stoerung, fuer die dieser Typ bekannt ist.
    const collapse = sp.vessel.voidCollapse * ctx.dpLag.v;
    s.alphaBar = ctx.voidLag.step(clamp(_void(s, sp) - collapse, 0, 0.95), h);
  },

  stepLoop(s, sp, ctx, dt) {
    // ── Umwaelzstrom ────────────────────────────────────────────────────────
    ctx.recircPump.demand = clamp(s.recircDmd, 0, sp.recirc.max);
    ctx.recircPump.step(dt);
    s.W_rec = ctx.recircPump.flow(0.12);   // Naturumlauf bleibt

    // ── Dichtewelleninstabilitaet ───────────────────────────────────────────
    // Kennzahl: viel Leistung bei wenig Durchsatz. Daraus ein Abklingverhaeltnis
    // und daraus die Daempfung eines Schwingers zweiter Ordnung bei 0,5 Hz.
    // Ueber 1 wird die Daempfung negativ und die Schwingung waechst.
    const st = sp.stability;
    const flowRel = Math.max(s.W_rec / sp.recirc.W0, 0.05);
    const S = s.n / flowRel;
    const DR = clamp(st.drBase + st.drSlope * Math.max(0, S - st.sThreshold), 0.05, 1.4);
    ctx.decayRatio = DR;
    const lnDR = Math.log(DR);
    const zeta = -lnDR / Math.sqrt(4 * Math.PI * Math.PI + lnDR * lnDR);
    const w = 2 * Math.PI * st.freqHz;
    // Anregung: das Rauschen des siedenden Kerns. Ohne sie bliebe eine
    // instabile Anlage rechnerisch still stehen.
    const noise = (ctx.rng ? ctx.rng.normal() : 0) * 0.004;
    s.oscV += (-2 * zeta * w * s.oscV - w * w * s.osc + noise * w * w) * dt;
    s.osc = clamp(s.osc + s.oscV * dt, -0.6, 0.6);

    s.W_core = Math.max(s.W_rec * (1 + s.osc), 100);

    // ── Dampfabgabe ─────────────────────────────────────────────────────────
    ctx.govValve.demand = (s.turbineTripped || s.msiv < 0.5) ? 0 : s.gov;
    ctx.govValve.step(dt);
    ctx.bypassValve.demand = s.msiv < 0.5 ? 0 : s.bypass;
    ctx.bypassValve.step(dt);

    const dp = Math.max(s.p_dome - s.p_cond, 0);
    const rhoS = rhog(s.p_dome);
    const W_t = ctx.govValve.flow(sp.turbine.Cv, rhoS, dp);
    const W_bp = ctx.bypassValve.flow(sp.turbine.bypassCv, rhoS, dp);

    // Sicherheitsventile: blasen in die Kondensationskammer, nicht zur Turbine.
    s.srv = s.p_dome > 78 ? clamp((s.p_dome - 78) / 3, 0, 1) : 0;
    const W_srv = s.srv * 900;

    s.W_steam = W_t + W_bp + W_srv;

    // ── Notkondensator ──────────────────────────────────────────────────────
    // Automatik will ihn offen, sobald isoliert wurde (SCRAM + Frischdampf
    // zu) und noch Vorrat da ist -- der Bediener kann das mit icDemand
    // uebersteuern. Die tatsaechliche Ventilstellung braucht zusaetzlich
    // Gleichstrom: fehlt er, faellt das Ventil in seine sichere Stellung
    // (ZU) und bleibt dort, ganz gleich was die Automatik will. Das ist die
    // Kernstoerung von Fukushima-1 -- unbemerkt, weil dieselbe Stoerung auch
    // die Anzeige mitreisst (siehe uiControls()).
    const icWanted = !!s.icDemand && s.scram.active && s.msiv < 0.5 && s.icWater > 0;
    s.icOpen = icWanted && s.dcPower;
    // Nie mehr, als der Kern gerade tatsaechlich an Dampf erzeugt -- sonst
    // entzieht die feste Nennleistung dem Dom mehr Waerme, als ueberhaupt da
    // ist, und der Druck stuerzt auf den unteren Anschlag statt sich auf
    // einen Gleichgewichtswert nahe der Saettigung einzupendeln.
    const W_ic = s.icOpen ? Math.min(sp.ic.W0, Math.max(s.x_e * s.W_core, 0)) : 0;
    if (W_ic > 0) {
      // Kondensat laeuft von selbst in den Behaelter zurueck -- der
      // Notkondensator entzieht dem Dom Waerme (und damit Druck), aber
      // keine Masse. Der Vorrat schwindet trotzdem, weil sein EIGENER
      // Behaelter dabei verdampft.
      s.icWater = Math.max(s.icWater - (W_ic / sp.ic.W0) * (dt / sp.ic.enduranceS), 0);
    }

    // ── Druck ───────────────────────────────────────────────────────────────
    // Erzeugt wird, was im Kern verdampft; abgefuehrt, was die Ventile UND
    // der Notkondensator lassen. Der IC zaehlt nur hier, nicht im
    // Fuellstand weiter unten -- sein Kondensat bleibt im eigenen Kreislauf.
    const W_gen = s.x_e * s.W_core;
    const W_out = s.W_steam + W_ic;
    const C_p = (sp.vessel.mass * sp.vessel.cp) / Math.max(dpdT(s.p_dome), 1e-6);
    const dh = Math.max(hg(s.p_dome) - H_FW, 1);
    const pNew = clamp(s.p_dome + (((W_gen - W_out) * dh) * dt) / C_p, 1, 110);
    // Die geglaettete Aenderungsrate treibt den Blasenkollaps im Kern.
    ctx.dpLag.step((pNew - ctx.pPrev) / dt, dt);
    ctx.pPrev = pNew;
    s.p_dome = pNew;
    s.p_prim = s.p_dome;

    // ── Sicherheitsbehälter ─────────────────────────────────────────────────
    // Der Sicherheitsventil-Dampf blaest in die Kondensationskammer und
    // haelt den Behaelterdruck hoch -- der einzige Weg, ueber den bei
    // Isolierung ueberhaupt Masse aus dem Dom in den Sicherheitsbehaelter
    // gelangt. Venten laesst kontrolliert wieder ab (dafuer verlaesst
    // radioaktives Gas die Anlage), sonst steigt der Druck weiter, bis der
    // Behaelter selbst versagt.
    s.contMass = Math.max(0, s.contMass + W_srv * dt
      - (s.contVentOpen ? sp.containment.ventCv : 0) * dt);
    s.pCont = sp.containment.p0 + (s.contMass / sp.containment.capacity)
      * (sp.containment.designLimit - sp.containment.p0);
    if (!s.contFailed && s.pCont > sp.containment.designLimit) {
      s.contFailed = true;
      ctx.log.push({ t: s.t_sim, key: 'event_cont_failure', severity: 3 });
      // Ein geborstener Sicherheitsbehaelter haelt nichts mehr zurueck --
      // von hier an wirkt er wie ein offenes Ventil.
    }
    if (s.contFailed) s.contMass = Math.max(0, s.contMass - sp.containment.ventCv * 2 * dt);

    // ── Wasserstoff ─────────────────────────────────────────────────────────
    // Zirkon-Wasser-Reaktion oberhalb von 1200 °C Huellrohrtemperatur --
    // lange vor der eigentlichen Kernzerstoerung ueber die Enthalpie.
    if (s.T_cl > sp.h2.onsetK) {
      s.h2Mass += sp.h2.rate * (s.T_cl - sp.h2.onsetK) * dt;
    }
    if (!s.h2Exploded && s.contVentOpen && s.h2Mass > 25) {
      // Der Wasserstoff geht beim Fukushima-Unfall nicht kontrolliert durch
      // den Kamin ab, sondern sucht sich seinen Weg zurueck ins
      // Reaktorgebaeude -- genau beim Venten wird er dorthin gedrueckt.
      s.h2Exploded = true;
      ctx.log.push({ t: s.t_sim, key: 'event_h2_explosion', severity: 3 });
    }

    // ── Fuellstand ──────────────────────────────────────────────────────────
    s.M_rpv = Math.max(s.M_rpv + (s.W_fw - s.W_steam) * dt, 20000);
    const Ltrue = clamp(0.5 + (s.M_rpv - sp.vessel.mass) / sp.vessel.massSpan, 0, 1);
    // Schrumpfen und Quellen ist hier staerker als beim Druckwasserreaktor:
    // der Kern selbst siedet, ein Druckabfall laesst den ganzen Behaelter
    // aufwallen.
    s.L_rpv = clamp(Ltrue + sp.vessel.shrinkSwell * (sp.vessel.p0 - s.p_dome) / sp.vessel.p0, 0, 1);

    // ── Unterkuehlung am Kerneintritt ───────────────────────────────────────
    s.dTsub = _subcooling(s, sp);

    // ── Turbine und Netz ────────────────────────────────────────────────────
    s.p_cond = clamp(psat(sp.condenser.T_cw + sp.condenser.pinch
      + (sp.condenser.rise || 12) * clamp(s.W_steam / sp.vessel.W_steam0, 0, 1.2)), 0.02, 1.5);
    const wSpec = (hg(s.p_dome) - hf(s.p_cond)) * sp.turbine.workFactor;
    s.P_e = s.breaker && !s.turbineTripped ? (W_t * wSpec) / 1000 : 0;
  },

  stepControls(s, sp, ctx, dt) {
    if (!s.scram.active && ctx.rodCtl.auto) {
      s.rodDmd[0] = clamp(s.rodDmd[0] + ctx.rodCtl.step(s.T_mod, 1, dt), 0, 1);
    }
    // Ohne Wechselstrom laufen weder Speisewasserpumpen noch ihre Regelung --
    // was dann noch Wasser bringt, ist ausschliesslich die Loeschwasser-
    // einspeisung, motorlos und ohne jede Elektronik.
    s.W_fw = s.acPower ? ctx.fwCtl.step(s.L_rpv, s.W_steam, dt)
      : (s.fireInjOn ? sp.fireInj.W0 : 0);
    // Das Regelventil haelt den Druck, nicht die Leistung.
    s.gov = ctx.govCtl.step(s.P_e, s.P_demand, s.p_dome, dt);
    s.bypass = s.p_dome > sp.vessel.p0 + 4
      ? clamp((s.p_dome - sp.vessel.p0 - 4) / 6, 0, 1) : 0;
  },

  onScram(s, sp, ctx) {
    s.turbineTripped = true;
    ctx.govCtl.trip();
    s.gov = 0;
    s.breaker = false;
    // Die Umwaelzpumpen laufen mit ab -- so ist es verschaltet, und es haelt
    // den Naturumlauf frei.
    ctx.recircPump.trip();
  },

  /**
   * Bedienung dieses Typs: der Umwaelzstrom ist das Leistungsstellglied, und
   * die Frischdampf-Absperrung ist die Stoerung, die man selbst ausloesen
   * koennen soll.
   */
  uiControls(s, sp, ctx, kit) {
    const recirc = kit.slider({
      labelKey: 'ctl_recirc', min: Math.round(sp.recirc.min * 100),
      max: Math.round(sp.recirc.max * 100), step: 1,
      value: Math.round(s.recircDmd * 100), digits: 0, unitKey: 'unit_percent',
      onInput: (v) => { s.recircDmd = v / 100; },
    });
    const msiv = kit.buttonGroup('ctl_msiv', [
      { key: 'state_open', value: '1' },
      { key: 'state_closed', value: '0' },
    ], '1', (v) => { s.msiv = Number(v); });

    // Notkondensator: der Bediener stellt nur die ABSICHT (icDemand), die
    // tatsächliche Ventilstellung braucht zusätzlich Gleichstrom. Genau
    // deshalb wird die Anzeige unten bewusst NICHT mehr nachgeführt, sobald
    // der Gleichstrom fehlt -- sie zeigt dann die letzte Stellung, die noch
    // gemeldet wurde, nicht die echte. Das ist die Meldung, die es 2011 nie
    // gab, absichtlich als Leerstelle nachgebildet statt als Alarmkachel.
    const ic = kit.buttonGroup('ctl_ic', [
      { key: 'state_open', value: '1' },
      { key: 'state_closed', value: '0' },
    ], '1', (v) => { s.icDemand = Number(v); });

    // Löschwassereinspeisung: einzige Wasserquelle, die auch ohne jeden
    // Strom funktioniert.
    const fireInj = kit.buttonGroup('ctl_fire_inj', [
      { key: 'state_open', value: '1' },
      { key: 'state_closed', value: '0' },
    ], '0', (v) => { s.fireInjOn = !!Number(v); });

    // Sicherheitsbehälter-Venten: kontrollierte Freisetzung, um einen
    // unkontrollierten Bruch zu verhindern.
    const contVent = kit.buttonGroup('ctl_cont_vent', [
      { key: 'state_open', value: '1' },
      { key: 'state_closed', value: '0' },
    ], '0', (v) => { s.contVentOpen = !!Number(v); });

    return [
      { mount: 'primary', node: recirc.node, set: (st) => recirc.set(Math.round(st.recircDmd * 100)) },
      { mount: 'secondary', node: msiv.node, set: (st) => msiv.set(String(st.msiv)) },
      {
        mount: 'safety',
        node: ic.node,
        // Kein Update, solange kein Gleichstrom da ist -- die Anzeige friert
        // auf dem letzten bekannten Stand ein, statt die wahre (geschlossene)
        // Stellung zu verraten.
        set: (st) => { if (st.dcPower) ic.set(String(st.icDemand)); },
      },
      { mount: 'safety', node: fireInj.node, set: (st) => fireInj.set(st.fireInjOn ? '1' : '0') },
      { mount: 'safety', node: contVent.node, set: (st) => contVent.set(st.contVentOpen ? '1' : '0') },
    ];
  },

  togglePump(s, sp, ctx) {
    const p = ctx.recircPump;
    if (p.state === 'run') p.trip(); else p.start();
  },

  derived(s, sp, ctx, base) {
    return {
      p_sg: s.p_dome,
      L_sg: s.L_rpv,
      W_steam: s.W_steam,
      W_fw: s.W_fw,
      gov: s.gov,
      bypass: s.bypass,
      p_cond: s.p_cond,
      voidFrac: s.alphaBar,
      quality: s.x_e,
      recirc: s.W_rec / sp.recirc.W0,
      subcooling: s.dTsub,
      decayRatio: ctx.decayRatio,
      oscAmp: Math.abs(s.osc),
      dnbr: _cpr(s, sp, base),
      shutdownMargin: sp.rodBanks.reduce((a, b, i) => a + b.worth * (1 - s.rod[i]), 0),
      pumpStates: [ctx.recircPump.state],
      pCont: s.pCont,
      h2Mass: s.h2Mass,
    };
  },
};

// ── Hilfsfunktionen ───────────────────────────────────────────────────────────

/** Unterkuehlung am Kerneintritt aus der Mischung Umwaelzwasser + Speisewasser. */
function _subcooling(s, sp) {
  const W = Math.max(s.W_core, 1);
  const Wfw = clamp(s.W_fw, 0, W);
  const hSat = hf(s.p_dome);
  const hMix = (Wfw * H_FW + (W - Wfw) * hSat) / W;
  return clamp((hSat - hMix) / sp.coolant.cp, 0, 60);
}

/**
 * Mittlerer Blasenanteil ueber die Kernhoehe.
 *
 * Die Siedezone ist der Teil des Kanals oberhalb des Siedebeginns. Ihr Anteil
 * folgt aus dem Verhaeltnis der Enthalpien: was zum Aufheizen bis zur
 * Saettigung draufgeht, siedet nicht.
 *
 *   f_sieden = 1 − (c_p · ΔT_unterkuehlt) / (q / W)
 *
 * Der erste Ansatz nahm stattdessen f_sieden = 1 − ΔT/55 K. Das sah aehnlich
 * aus und war trotzdem falsch, denn es haengt nur an der Unterkuehlung und
 * nicht am Durchsatz. Folge: bei 80 % Umwaelzstrom stieg zwar der Dampfgehalt,
 * gleichzeitig sank aber die gerechnete Siedezone -- beides hob sich auf, der
 * Blasenanteil bewegte sich um 0,4 Prozentpunkte, und die Leistung um 1,9 %
 * statt um die erwarteten 10 bis 20 %. Damit waere das Regelorgan dieses
 * Reaktortyps wirkungslos gewesen.
 */
function _void(s, sp) {
  const W = Math.max(s.W_core, 1);
  const G = W / sp.coolant.flowArea_m2;
  const qPerKg = (s.P_th * 1000) / W;              // kJ/kg zugefuehrt
  const subPerKg = sp.coolant.cp * s.dTsub;        // kJ/kg bis zur Saettigung
  const fBoil = clamp(1 - subPerKg / Math.max(qPerKg, 1e-3), 0.05, 0.98);
  return averageVoid(s.x_e, s.p_dome, G, fBoil);
}

/**
 * Abstand zur Siedekrise, beim Siedewasserreaktor als kritisches
 * Leistungsverhaeltnis. Wie beim Druckwasserreaktor eine monotone Kennzahl mit
 * der richtigen Form, keine echte Korrelation: mehr Durchsatz hilft, mehr
 * Leistung und mehr Dampfgehalt schaden.
 */
function _cpr(s, sp, base) {
  const flow = clamp(s.W_core / sp.recirc.W0, 0.05, 1.3);
  const power = clamp(base.load, 0.02, 2);
  const q = clamp(1 - s.x_e / 0.28, 0.05, 1);
  return clamp(1.9 * Math.pow(flow, 0.5) * Math.pow(q, 0.35) / power, 0, 20);
}

export default { spec, hooks };
