// Einstieg: Startbildschirm, Aufbau des Leitstands, Verdrahtung der Bedienung.

import { $, $$, setText, setAttr } from './ui/dom.js';
import { t } from './ui/i18n.js';
import { Render } from './ui/render.js';
import { buildPanels } from './ui/panels.js';
import { Loop } from './loop.js';
import { createEngine } from './sim/engine.js';
import { getPlant, isAvailable } from './plants/index.js';

const app = {
  engine: null,
  loop: null,
  render: new Render(),
  reactor: null,
  controlsReady: false,
  horn: null,
};

// ── Startbildschirm ──────────────────────────────────────────────────────────

function initStart() {
  const cards = $$('.rs-card');
  const go = $('#rs-start-go');
  const hint = $('.rs-start-hint');

  for (const card of cards) {
    const id = card.dataset.reactor;
    card.setAttribute('aria-pressed', 'false');
    if (!isAvailable(id)) {
      // Noch nicht gebaute Typen bleiben sichtbar -- sie sind die Ansage, wohin
      // das Spiel geht -- aber nicht wählbar.
      card.disabled = true;
      card.title = t('reactor_soon_hint');
      const badge = card.querySelector('.rs-card-badge');
      const soon = document.createElement('span');
      soon.className = 'rs-card-soon-tag';
      soon.textContent = t('reactor_soon');
      if (badge) badge.after(soon); else card.prepend(soon);
    }
    card.addEventListener('click', () => {
      if (!isAvailable(id)) return;
      for (const c of cards) c.setAttribute('aria-pressed', String(c === card));
      app.reactor = id;
      go.disabled = false;
      if (hint) setText(hint, '');
    });
  }

  go.addEventListener('click', () => {
    if (app.reactor) boot(app.reactor);
  });
}

// ── Leitstand ────────────────────────────────────────────────────────────────

function initControls() {
  // Nur einmal verdrahten: über „Menü" kommt man zurück auf den Startbildschirm
  // und von dort erneut hierher -- ein zweiter Satz Zuhörer würde jeden Klick
  // doppelt auslösen.
  if (app.controlsReady) return;
  app.controlsReady = true;

  for (const btn of $$('.rs-speed-b')) {
    btn.addEventListener('click', () => {
      setSpeed(Number(btn.dataset.speed));
    });
  }

  // Schnellabschaltung in zwei Schritten. Ein versehentlicher Fingertipper auf
  // dem Handy darf keine Anlage abwerfen.
  const scram = $('#rs-scram');
  let armed = 0;
  const disarm = () => {
    if (armed) window.clearTimeout(armed);
    armed = 0;
    scram.dataset.armed = '0';
    setText(scram, t('btn_scram'));
  };
  scram.addEventListener('click', () => {
    if (app.horn) app.horn.unlock();
    if (!armed) {
      armed = window.setTimeout(disarm, 4000);
      scram.dataset.armed = '1';
      setText(scram, t('btn_confirm'));
      return;
    }
    disarm();
    app.engine.scram('manual');
    setSpeed(1);
  });

  $('#rs-menu').addEventListener('click', () => {
    app.loop.stop();
    $('#rs-app').hidden = true;
    $('#rs-start').hidden = false;
  });

  $('#rs-fault-reload').addEventListener('click', () => window.location.reload());

  // Tastatur am Rechner: Leertaste hält an, Zahlen wählen den Zeitraffer.
  document.addEventListener('keydown', (ev) => {
    if (ev.target instanceof HTMLInputElement) return;
    if (ev.code === 'Space') { ev.preventDefault(); setSpeed(app.loop.speed > 0 ? 0 : 1); }
    else if (ev.key === '1') setSpeed(1);
    else if (ev.key === '2') setSpeed(4);
    else if (ev.key === '3') setSpeed(16);
    else if (ev.key === '4') setSpeed(60);
  });
}

function setSpeed(v) {
  app.loop.setSpeed(v);
  for (const b of $$('.rs-speed-b')) b.classList.toggle('rs-on', Number(b.dataset.speed) === v);
}

function showFault(detail) {
  if (app.loop) app.loop.stop();
  setText($('#rs-fault-detail'), detail || '');
  $('#rs-fault').hidden = false;
}

function boot(reactorId) {
  const plant = getPlant(reactorId);
  if (!plant) return;

  $('#rs-start').hidden = true;
  $('#rs-app').hidden = false;

  app.engine = createEngine(plant, { n: 1.0 });
  app.render.clear();
  const built = buildPanels(app.engine, app.render);
  app.horn = built.horn;

  app.loop = new Loop(app.engine, (state, now) => {
    try {
      app.render.tick(state, now);
    } catch (err) {
      showFault(String(err && err.message ? err.message : err));
    }
    // Die Engine hält bei einem unmöglichen Zustand von selbst an und legt den
    // Grund ab; hier wird er nur sichtbar gemacht.
    if (state.fault) showFault(state.fault);
  });
  app.loop.onSlip = (slipping) => { $('#rs-slip').hidden = !slipping; };

  initControls();
  setSpeed(1);
  app.loop.start();
}

// ── Start ────────────────────────────────────────────────────────────────────

initStart();
setAttr(document.documentElement, 'data-rs-version', window.RS_CFG ? window.RS_CFG.version : '0');
