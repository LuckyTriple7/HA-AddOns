// Einstieg: Startbildschirm, Aufbau des Leitstands, Verdrahtung der Bedienung.

import { $, $$, setText, setAttr } from './ui/dom.js';
import { t, num, clock } from './ui/i18n.js';
import { Render } from './ui/render.js';
import { Loop } from './loop.js';
import { createEngine, derive } from './sim/engine.js';

const app = {
  engine: null,
  loop: null,
  render: new Render(),
  reactor: null,
  controlsReady: false,
  binds: new Map(),   // data-v -> Knotenliste
};

// ── Startbildschirm ──────────────────────────────────────────────────────────

function initStart() {
  const cards = $$('.rs-card');
  const go = $('#rs-start-go');

  for (const card of cards) {
    card.setAttribute('aria-pressed', 'false');
    card.addEventListener('click', () => {
      for (const c of cards) c.setAttribute('aria-pressed', String(c === card));
      app.reactor = card.dataset.reactor;
      go.disabled = false;
    });
  }

  go.addEventListener('click', () => {
    if (app.reactor) boot(app.reactor);
  });
}

// ── Leitstand ────────────────────────────────────────────────────────────────

function collectBinds() {
  app.binds.clear();
  for (const node of $$('[data-v]')) {
    const key = node.dataset.v;
    const list = app.binds.get(key);
    if (list) list.push(node);
    else app.binds.set(key, [node]);
  }
}

function put(key, text) {
  const list = app.binds.get(key);
  if (!list) return;
  for (const node of list) setText(node, text);
}

const U = (unitKey) => ' ' + t(unitKey);

function fmtPeriod(seconds) {
  if (!Number.isFinite(seconds)) return t('period_infinite');
  const a = Math.abs(seconds);
  if (a > 9999) return t('period_infinite');
  return (seconds > 0 ? '+' : '') + num(seconds, 0) + U('unit_seconds');
}

function paintText(s) {
  const d = derive(s);
  put('power_th_pct', num(d.power_th_pct, 1) + U('unit_percent'));
  put('power_e', num(d.power_e, 0) + U('unit_mwe'));
  put('demand', num(d.demand_e, 0) + U('unit_mwe'));
  put('deviation', (d.deviation >= 0 ? '+' : '') + num(d.deviation, 0) + U('unit_mwe'));
  put('t_avg', num(d.t_avg, 1) + U('unit_celsius'));
  put('t_hot', num(d.t_hot, 1) + U('unit_celsius'));
  put('t_cold', num(d.t_cold, 1) + U('unit_celsius'));
  put('t_fuel', num(d.t_fuel, 0) + U('unit_celsius'));
  put('t_clad', num(d.t_clad, 0) + U('unit_celsius'));
  put('p_prim', num(d.p_prim, 1) + U('unit_bar'));
  put('w_core', num(d.w_core, 0) + U('unit_kgs'));
  put('n_pct', num(d.n_pct, 1) + U('unit_percent'));
  put('decay_pct', num(d.decay_pct, 2) + U('unit_percent'));
  put('period', fmtPeriod(d.period));
  put('freq', num(d.freq, 2) + U('unit_hz'));
  put('clock', clock(s.t_sim));
}

function initControls() {
  // Nur einmal verdrahten: über „Menü" kommt man zurück auf den Startbildschirm
  // und von dort erneut hierher -- ein zweiter Satz Zuhörer würde jeden Klick
  // doppelt auslösen.
  if (app.controlsReady) return;
  app.controlsReady = true;

  // Zeitraffer
  for (const btn of $$('.rs-speed-b')) {
    btn.addEventListener('click', () => {
      const v = Number(btn.dataset.speed);
      app.loop.setSpeed(v);
      for (const b of $$('.rs-speed-b')) b.classList.toggle('rs-on', b === btn);
    });
  }

  // Schnellabschaltung: zwei Schritte. Ein versehentlicher Fingertipper auf
  // dem Handy darf keine Anlage abwerfen.
  const scram = $('#rs-scram');
  let armed = 0;
  scram.addEventListener('click', () => {
    if (!armed) {
      armed = window.setTimeout(() => { armed = 0; scram.dataset.armed = '0'; scram.textContent = t('btn_scram'); }, 4000);
      scram.dataset.armed = '1';
      scram.textContent = t('btn_confirm');
      return;
    }
    window.clearTimeout(armed);
    armed = 0;
    scram.dataset.armed = '0';
    scram.textContent = t('btn_scram');
    app.engine.state.scram = true;
    app.loop.setSpeed(1);
    for (const b of $$('.rs-speed-b')) b.classList.toggle('rs-on', b.dataset.speed === '1');
  });

  $('#rs-menu').addEventListener('click', () => {
    app.loop.stop();
    $('#rs-app').hidden = true;
    $('#rs-start').hidden = false;
  });

  $('#rs-fault-reload').addEventListener('click', () => window.location.reload());
}

function showFault(detail) {
  if (app.loop) app.loop.stop();
  setText($('#rs-fault-detail'), detail || '');
  $('#rs-fault').hidden = false;
}

function boot(reactorId) {
  $('#rs-start').hidden = true;
  $('#rs-app').hidden = false;

  collectBinds();

  app.engine = createEngine(reactorId);
  app.render.clear();
  app.render.add('text', paintText);

  app.loop = new Loop(app.engine, (state, now) => {
    try {
      app.render.tick(state, now);
    } catch (err) {
      showFault(String(err && err.message ? err.message : err));
    }
  });
  app.loop.onSlip = (slipping) => { $('#rs-slip').hidden = !slipping; };

  initControls();
  app.loop.setSpeed(1);
  app.loop.start();
}

// ── Start ────────────────────────────────────────────────────────────────────

initStart();
setAttr(document.documentElement, 'data-rs-version', window.RS_CFG ? window.RS_CFG.version : '0');
