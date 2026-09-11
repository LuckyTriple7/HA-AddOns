// Aufbau und Nachführung der Panels.
//
// Hier wird einmal alles gebaut und beim Renderlauf nur noch nachgeführt. Die
// Zuordnung „welcher Wert steht wo" liegt bewusst an einer Stelle, damit ein
// neuer Reaktortyp die Anzeige erweitern kann, ohne dass main.js wächst.

import { $, el, setText, setAttr } from './dom.js';
import { t, num, clock } from './i18n.js';
import { gauge, bar, reactivityBars } from './gauges.js';
import { TrendRecorder } from './trend.js';
import { Annunciator, Horn } from './annunciator.js';
import {
  autoSwitch, slider, buttonGroup, jogButtons, pumpRow,
} from './controls.js';

const U = (key) => ' ' + t(key);

export function buildPanels(engine, render) {
  const s = engine.state;
  const sp = engine.spec;
  const ctx = engine.ctx;

  // ── Wertebindungen einsammeln ──────────────────────────────────────────────
  const binds = new Map();
  for (const node of document.querySelectorAll('[data-v]')) {
    const key = node.dataset.v;
    const list = binds.get(key);
    if (list) list.push(node); else binds.set(key, [node]);
  }
  const put = (key, text, sev) => {
    const list = binds.get(key);
    if (!list) return;
    for (const n of list) {
      setText(n, text);
      if (sev !== undefined) setAttr(n, 'data-sev', sev);
    }
  };

  // ── Rundinstrumente ────────────────────────────────────────────────────────
  const gCore = [
    { g: gauge({ label: t('status_power_th'), min: 0, max: 120, digits: 1, unitKey: 'unit_percent',
        bands: [[0, 100, 'ok'], [100, 110, 'warn'], [110, 120, 'danger']] }),
      get: (d) => d.power_th_pct },
    { g: gauge({ label: t('val_fuel_temp'), min: 200, max: 2000, digits: 0, unitKey: 'unit_celsius',
        bands: [[200, 1400, 'ok'], [1400, 1700, 'warn'], [1700, 2000, 'danger']] }),
      get: (d, st) => st.T_f - 273.15 },
    { g: gauge({ label: t('val_reactivity'), min: -500, max: 500, digits: 0, unitKey: 'unit_pcm',
        bands: [[-500, -200, 'warn'], [-200, 200, 'ok'], [200, 500, 'danger']] }),
      get: (d) => d.rho_pcm },
  ];
  const coreBox = $('#rs-core-gauges');
  for (const x of gCore) coreBox.append(x.g.node);

  const gPrim = [
    { g: gauge({ label: t('status_pressure'), min: 100, max: 180, digits: 1, unitKey: 'unit_bar',
        bands: [[100, 140, 'danger'], [140, 168, 'ok'], [168, 180, 'danger']] }),
      get: (d, st) => st.p_prim },
    { g: gauge({ label: t('val_subcooling'), min: 0, max: 40, digits: 1, unitKey: 'unit_kelvin',
        bands: [[0, 8, 'danger'], [8, 15, 'warn'], [15, 40, 'ok']] }),
      get: (d) => d.subcooling },
    { g: gauge({ label: t('val_dnbr'), min: 1, max: 4, digits: 2,
        bands: [[1, 1.3, 'danger'], [1.3, 1.8, 'warn'], [1.8, 4, 'ok']] }),
      get: (d) => d.dnbr },
  ];
  const primBox = $('#rs-prim-gauges');
  for (const x of gPrim) primBox.append(x.g.node);

  const gSec = [
    { g: gauge({ label: t('val_sg_press'), min: 40, max: 100, digits: 1, unitKey: 'unit_bar',
        bands: [[40, 55, 'warn'], [55, 76, 'ok'], [76, 100, 'danger']] }),
      get: (d, st) => st.p_sg },
    { g: gauge({ label: t('val_sg_level'), min: 0, max: 100, digits: 0, unitKey: 'unit_percent',
        bands: [[0, 25, 'danger'], [25, 40, 'warn'], [40, 70, 'ok'], [70, 100, 'warn']] }),
      get: (d, st) => st.L_sg * 100 },
    { g: gauge({ label: t('val_generator'), min: 0, max: sp.P0_e * 1.15, digits: 0, unitKey: 'unit_mwe',
        bands: [[0, sp.P0_e, 'ok'], [sp.P0_e, sp.P0_e * 1.15, 'warn']] }),
      get: (d, st) => st.P_e },
  ];
  const secBox = $('#rs-sec-gauges');
  for (const x of gSec) secBox.append(x.g.node);

  // ── Stabstellungen ─────────────────────────────────────────────────────────
  const rodBars = sp.rodBanks.map((b) => bar({ label: t('ctl_rod_bank_' + b.id) }));
  const rodsBox = $('#rs-rods');
  rodsBox.replaceChildren(el('div.rs-bars', null, rodBars.map((r) => r.node)));

  // ── Reaktivitätsbilanz ─────────────────────────────────────────────────────
  const rhoIds = engine.reactivity.parts.map((p) => p.id).filter((id) => id !== 'excess');
  const rho = reactivityBars([...rhoIds, 'total']);
  $('#rs-rho').replaceChildren(rho.node);

  // ── Bedienung ──────────────────────────────────────────────────────────────
  const rodAuto = autoSwitch('ctl_rod_auto', true, (v) => { ctx.rodCtl.auto = v; });
  const rodJog = jogButtons('ctl_rods', (dir) => {
    ctx.rodCtl.auto = false;
    rodAuto.set(false);
    s.rodDmd[0] = Math.max(0, Math.min(1, s.rodDmd[0] + dir * 0.005));
  });
  $('#rs-rod-ctl').replaceChildren(rodAuto.node, rodJog.node);

  const pumps = pumpRow(ctx.pumps.length, (i) => {
    const p = ctx.pumps[i];
    if (p.state === 'run') p.trip(); else p.start();
  });
  $('#rs-pumps').replaceChildren(pumps.node);

  const govAuto = autoSwitch('ctl_turbine', true, (v) => { ctx.govCtl.auto = v; });
  const fwAuto = autoSwitch('ctl_feedwater', true, (v) => { ctx.fwCtl.auto = v; });
  const pzrAuto = autoSwitch('ctl_pressurizer', true, (v) => { ctx.pzrCtl.auto = v; });
  $('#rs-sec-ctl').replaceChildren(govAuto.node, fwAuto.node, pzrAuto.node);

  const demand = slider({
    labelKey: 'ctl_demand', min: 0, max: Math.round(sp.P0_e), step: 5,
    value: Math.round(s.P_demand), digits: 0, unitKey: 'unit_mwe',
    onInput: (v) => { s.P_demand = v; },
  });
  $('#rs-grid-ctl').replaceChildren(demand.node);

  const boron = buttonGroup('ctl_boron', [
    { key: 'ctl_boron_dilute', value: '-1' },
    { key: 'ctl_boron_stop', value: '0' },
    { key: 'ctl_boron_add', value: '1' },
  ], '0', (v) => { s.boronFlow = Number(v); });
  $('#rs-chem-ctl').replaceChildren(boron.node);

  // ── Trendschreiber ─────────────────────────────────────────────────────────
  const trends = [
    new TrendRecorder([
      { id: 'pth', key: 'trend_ch_pth', color: '#64d8ff', get: (st, d) => d.power_th_pct },
      { id: 'pe', key: 'trend_ch_pe', color: '#3fd67f', get: (st) => (100 * st.P_e) / sp.P0_e },
      { id: 'dem', key: 'trend_ch_demand', color: '#ffb020', get: (st) => (100 * st.P_demand) / sp.P0_e },
    ], { titleKey: 'trend_power', fmt: 1 }),
    new TrendRecorder([
      { id: 'thot', key: 'trend_ch_thot', color: '#ff7a3d', get: (st) => st.T_co - 273.15 },
      { id: 'tavg', key: 'trend_ch_tavg', color: '#ffd27a', get: (st, d) => d.T_avg - 273.15 },
      { id: 'tcold', key: 'trend_ch_tcold', color: '#4b8fd6', get: (st) => st.T_ci - 273.15 },
    ], { titleKey: 'trend_temp', fmt: 1 }),
    new TrendRecorder([
      { id: 'pprim', key: 'trend_ch_pprim', color: '#64d8ff', get: (st) => st.p_prim },
      { id: 'psg', key: 'trend_ch_psg', color: '#cfd9e2', get: (st) => st.p_sg },
    ], { titleKey: 'trend_pressure', fmt: 1 }),
    new TrendRecorder([
      { id: 'rho', key: 'trend_ch_rho', color: '#ff4d4d', get: (st, d) => d.rho_pcm },
      { id: 'xe', key: 'trend_ch_xenon', color: '#b489ff', get: (st) => st.X * 100 },
    ], { titleKey: 'trend_reactivity', fmt: 0 }),
  ];
  const trendBox = $('#rs-trends');
  trendBox.replaceChildren(...trends.map((r) => r.node));

  const ranges = [['trend_10min', 600], ['trend_1h', 3600], ['trend_8h', 28800]];
  const rangeBtns = ranges.map(([key, secs]) => {
    const b = el('button.rs-gbtn', { type: 'button' }, [t(key)]);
    b.addEventListener('click', () => {
      for (const r of trends) r.setRange(secs);
      for (const other of rangeBtns) other.classList.toggle('rs-on', other === b);
    });
    return b;
  });
  rangeBtns[0].classList.add('rs-on');
  $('#rs-trend-range').replaceChildren(...rangeBtns);

  // ── Meldetafel ─────────────────────────────────────────────────────────────
  const annun = new Annunciator($('#rs-annun'), $('#rs-log'), sp.trips || []);
  const horn = new Horn();
  let hornNext = 0;

  $('#rs-ack').addEventListener('click', () => { horn.unlock(); engine.trips.ack(); });
  $('#rs-alarm-reset').addEventListener('click', () => engine.trips.reset());

  // ── Nachführung ────────────────────────────────────────────────────────────
  const statusBar = $('#rs-status-alarm');
  const tabAlarm = $('#rs-tab-alarm-label');
  const promptNode = $('#rs-prompt');

  render.add('gauge', () => {
    const d = engine.derive();
    for (const x of gCore) x.g.set(x.get(d, s));
    for (const x of gPrim) x.g.set(x.get(d, s));
    for (const x of gSec) x.g.set(x.get(d, s));
    for (let i = 0; i < rodBars.length; i++) rodBars[i].set(s.rod[i], s.rodDmd[i]);
  });

  render.add('text', () => {
    const d = engine.derive();

    put('power_th_pct', num(d.power_th_pct, 1) + U('unit_percent'));
    put('power_e', num(s.P_e, 0) + U('unit_mwe'));
    put('demand', num(s.P_demand, 0) + U('unit_mwe'));
    put('deviation', (d.deviation >= 0 ? '+' : '') + num(d.deviation, 0) + U('unit_mwe'));
    put('t_avg', num(d.T_avg - 273.15, 1) + U('unit_celsius'));
    put('t_hot', num(d.T_hot - 273.15, 1) + U('unit_celsius'));
    put('t_cold', num(d.T_cold - 273.15, 1) + U('unit_celsius'));
    put('t_fuel', num(s.T_f - 273.15, 0) + U('unit_celsius'),
        s.T_f > 1973 ? 3 : (s.T_f > 1673 ? 1 : undefined));
    put('t_clad', num(s.T_cl - 273.15, 0) + U('unit_celsius'),
        s.T_cl > 1477 ? 3 : (s.T_cl > 1100 ? 1 : undefined));
    put('p_prim', num(s.p_prim, 1) + U('unit_bar'));
    put('w_core', num(s.W_core, 0) + U('unit_kgs'));
    put('n_pct', num(d.n_pct, 2) + U('unit_percent'));
    put('decay_pct', num(d.decay_pct, 2) + U('unit_percent'));
    put('period', fmtPeriod(d.period));
    put('freq', num(s.f_grid, 2) + U('unit_hz'));
    put('clock', clock(s.t_sim));
    put('subcool', num(d.subcooling, 1) + U('unit_kelvin'), d.subcooling < 8 ? 3 : (d.subcooling < 15 ? 1 : undefined));
    put('dnbr', num(d.dnbr, 2), d.dnbr < 1.3 ? 3 : (d.dnbr < 1.8 ? 1 : undefined));
    put('p_sg', num(s.p_sg, 1) + U('unit_bar'));
    put('w_steam', num(s.W_steam, 0) + U('unit_kgs'));
    put('gov', num(ctxPos(ctx.govValve) * 100, 0) + U('unit_percent'));
    put('p_cond', num(s.p_cond, 3) + U('unit_bar'));
    put('l_sg', num(s.L_sg * 100, 0) + U('unit_percent'), s.L_sg < 0.3 || s.L_sg > 0.75 ? 1 : undefined);
    put('w_fw', num(s.W_fw, 0) + U('unit_kgs'));
    put('breaker', t(s.breaker ? 'state_on' : 'state_off'));
    put('xenon', num(s.X * 100, 1) + U('unit_percent'));
    put('iodine', num(s.I * 100, 1) + U('unit_percent'));
    put('samarium', num(s.Sm * 100, 1) + U('unit_percent'));
    put('boron', num(s.C_B, 0) + U('unit_ppm'));
    put('burnup', num(s.burnup, 0) + U('unit_efpd'));
    put('sdm', num(d.shutdownMargin, 0) + U('unit_pcm'));

    rho.set(d.breakdown, d.rho);
    pumps.set(d.pumpStates);
    demand.set(Math.round(s.P_demand));
    rodAuto.set(ctx.rodCtl.auto);
    govAuto.set(ctx.govCtl.auto);
    fwAuto.set(ctx.fwCtl.auto);
    pzrAuto.set(ctx.pzrCtl.auto);
    boron.set(String(s.boronFlow));

    promptNode.hidden = !s.promptCritical;

    // Meldetafel und Protokoll
    annun.update(engine.trips.tiles());
    const entries = engine.drainLog();
    if (entries.length) annun.log(entries);

    let worst = 0, worstKey = null;
    for (const tile of engine.trips.tiles()) {
      if (tile.tile === 'new' || tile.tile === 'ack') {
        if (tile.severity > worst) { worst = tile.severity; worstKey = tile.key; }
      }
    }
    setAttr(statusBar, 'data-sev', worst);
    put('worst_alarm', worstKey ? t(worstKey) : t('status_alarm_none'));
    setAttr(tabAlarm, 'data-sev', worst);
    setAttr(tabAlarm, 'data-unack', engine.trips.horn ? '1' : '0');

    // Hupe im Takt der blinkenden Kachel.
    if (engine.trips.horn) {
      const now = performance.now();
      if (now > hornNext) { horn.beep(worst >= 3 ? 880 : 620, 110); hornNext = now + 1000; }
    }
  });

  render.add('trend', () => {
    const d = engine.derive();
    for (const r of trends) { r.sample(s, d); r.draw(); }
  });

  return { horn };
}

function ctxPos(valve) { return valve ? valve.pos : 0; }

function fmtPeriod(seconds) {
  if (!Number.isFinite(seconds)) return t('period_infinite');
  const a = Math.abs(seconds);
  if (a > 9999) return t('period_infinite');
  return (seconds > 0 ? '+' : '') + num(seconds, 0) + U('unit_seconds');
}
