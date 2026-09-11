// Einstieg: Startbildschirm, Aufbau des Leitstands, Verdrahtung der Bedienung.

import { $, $$, el, setText, setAttr } from './ui/dom.js';
import { t, clock } from './ui/i18n.js';
import { Render } from './ui/render.js';
import { buildPanels } from './ui/panels.js';
import { Loop } from './loop.js';
import { createEngine } from './sim/engine.js';
import { getPlant, isAvailable } from './plants/index.js';
import { Session, PHASE } from './game/session.js';

const app = {
  engine: null,
  loop: null,
  render: new Render(),
  reactor: null,
  controlsReady: false,
  horn: null,
  session: null,
  scenarios: [],
  chosen: null,      // gewaehltes Szenario oder null fuer freies Spiel
};

// ── Startbildschirm ──────────────────────────────────────────────────────────

function initStart() {
  const cards = $$('.rs-card');
  const go = $('#rs-start-go');

  for (const card of cards) {
    const id = card.dataset.reactor;
    card.setAttribute('aria-pressed', 'false');
    if (!isAvailable(id)) {
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
      renderScenarios(id);
    });
  }

  go.addEventListener('click', () => {
    if (!app.reactor) return;
    if (app.chosen) loadScenario(app.chosen);
    else boot(app.reactor, null);
  });

  $('#rs-brief-go').addEventListener('click', () => {
    $('#rs-brief').hidden = true;
    boot(app.reactor, app.briefDef);
  });

  $('#rs-debrief-close').addEventListener('click', () => {
    $('#rs-debrief').hidden = true;
    toMenu();
  });

  // Szenarienliste holen. Geht das schief, bleibt das freie Spiel -- das Spiel
  // muss ohne den Server spielbar sein, er liefert hier nur eine Liste.
  fetch('/api/meta', { headers: { Accept: 'application/json' } })
    .then((r) => (r.ok ? r.json() : null))
    .then((m) => { if (m && m.scenarios) app.scenarios = m.scenarios; })
    .catch(() => {});
}

/** Szenarienkarten fuer den gewaehlten Reaktortyp. */
function renderScenarios(reactorId) {
  const list = $('#rs-scn-list');
  const headline = $('#rs-scn-headline');
  const go = $('#rs-start-go');
  const mine = app.scenarios.filter((x) => x.reactor === reactorId);

  app.chosen = null;
  setText(go, t('start_free_play'));
  list.replaceChildren();
  headline.hidden = mine.length === 0;
  if (!mine.length) return;

  const entries = [{ id: null, title_key: 'scn_free', brief_key: 'scn_free_desc' }, ...mine];
  const buttons = [];
  for (const scn of entries) {
    const meta = scn.id
      ? `${t('brief_duration')} ${Math.round(scn.duration_s / 60)} min · `
        + `${t('brief_difficulty')} ${'\u2605'.repeat(scn.difficulty)}`
      : t('scn_free_desc');
    const btn = el('button.rs-scn', { type: 'button', 'aria-pressed': String(scn.id === null) }, [
      el('span.rs-scn-name', { text: t(scn.title_key) }),
      el('span.rs-scn-meta', { text: meta }),
    ]);
    btn.addEventListener('click', () => {
      app.chosen = scn.id ? scn : null;
      for (const b of buttons) b.setAttribute('aria-pressed', String(b === btn));
      setText(go, scn.id ? t('brief_title') : t('start_free_play'));
    });
    buttons.push(btn);
    list.append(btn);
  }
}

/** Szenariodatei nachladen und die Einweisung zeigen. */
function loadScenario(scn) {
  const base = window.RS_CFG ? `/s/${window.RS_CFG.version}` : '';
  fetch(`${base}/data/scenarios/${scn.file}`)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error('scenario'))))
    .then((def) => {
      app.briefDef = def;
      setText($('#rs-brief-title'), t(def.title_key));
      setText($('#rs-brief-text'), t(def.brief_key));
      const meta = $('#rs-brief-meta');
      meta.replaceChildren(
        el('span', { text: `${t('brief_duration')}: ${Math.round(def.duration_s / 60)} min` }),
        el('span', { text: `${t('brief_difficulty')}: ${'\u2605'.repeat(def.difficulty || 1)}` }),
      );
      $('#rs-brief').hidden = false;
    })
    .catch(() => { boot(app.reactor, null); });
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
    if (app.session && app.session.phase === PHASE.RUNNING && !app.session.free) {
      app.session.abort();
      return;
    }
    toMenu();
  });

  $('#rs-fault-reload').addEventListener('click', () => window.location.reload());

  $('#rs-destroyed-close').addEventListener('click', () => {
    $('#rs-destroyed').hidden = true;
    app.loop.stop();
    $('#rs-app').hidden = true;
    $('#rs-start').hidden = false;
  });

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

/**
 * Schwerer Störfall. Der Lauf endet hier -- mit der Zeitleiste der Meldungen,
 * die dorthin geführt haben. Das ist der Punkt des Spiels: nicht das Ende zu
 * zeigen, sondern den Weg.
 */
function showDestroyed() {
  app.endShown = true;
  app.loop.setSpeed(0);
  const s = app.engine.state;
  setText($('#rs-destroyed-detail'),
    `${t('val_fuel_temp')}: ${Math.round(s.T_f - 273.15)} °C · `
    + `${Math.round(s.enthalpy)} J/g · ${clock(s.t_sim)}`);
  const list = $('#rs-destroyed-log');
  list.replaceChildren();
  // Die letzten Einträge der Meldetafel, neueste zuerst.
  const log = $('#rs-log');
  for (let i = 0; i < Math.min(log.children.length, 8); i++) {
    list.append(log.children[i].cloneNode(true));
  }
  $('#rs-destroyed').hidden = false;
}

function toMenu() {
  if (app.loop) app.loop.stop();
  $('#rs-app').hidden = true;
  $('#rs-start').hidden = false;
}

/** Auswertung am Ende eines Szenarios. */
function showDebrief(result, failed) {
  app.loop.setSpeed(0);
  const verdict = $('#rs-debrief-verdict');
  const ok = !failed;
  setAttr(verdict, 'data-ok', ok ? '1' : '0');
  setText(verdict, ok ? t('debrief_completed') : `${t('debrief_failed')} — ${t(failed)}`);
  setText($('#rs-debrief-score'), result ? String(result.score) : '—');

  const parts = $('#rs-debrief-parts');
  parts.replaceChildren();
  if (result) {
    const sum = result.summary;
    const rows = [
      ['debrief_energy', `${Math.round(sum.energy_mwh_delivered)} / ${Math.round(sum.energy_mwh_demanded)} ${t('unit_mwh')}`],
      ['debrief_deviation', `${sum.deviation_mwh.toFixed(1)} ${t('unit_mwh')}`],
      ['debrief_alarms', `${sum.alarm_seconds_unacked} ${t('unit_seconds')}`],
      ['debrief_scram', String(sum.scram_count)],
      ['debrief_fuel', sum.fuel_damage ? t('state_on') : t('state_off')],
    ];
    for (const [key, value] of rows) {
      parts.append(el('div.rs-row', null, [
        el('span', { text: t(key) }), el('b', { text: value }),
      ]));
    }
  }
  $('#rs-debrief').hidden = false;
}

function boot(reactorId, scenarioDef) {
  const plant = getPlant(reactorId);
  if (!plant) return;

  $('#rs-start').hidden = true;
  $('#rs-app').hidden = false;

  app.endShown = false;
  app.engine = createEngine(plant, { n: 1.0, seed: scenarioDef ? scenarioDef.seed : 1 });
  app.session = new Session(app.engine, scenarioDef);
  app.session.onEnd = (result, failed) => showDebrief(result, failed);
  app.session.start();
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
    if (state.destroyed && !app.endShown) showDestroyed();
  });
  app.loop.onSlip = (slipping) => { $('#rs-slip').hidden = !slipping; };
  // Die Spielschicht sieht jeden Simulationsschritt, nicht jedes Bild.
  app.loop.afterStep = (dt) => {
    let worst = 0;
    for (const tile of app.engine.trips.tiles()) {
      if ((tile.tile === 'new' || tile.tile === 'ack') && tile.severity > worst) worst = tile.severity;
    }
    app.session.step(dt, worst, app.engine.trips.unacknowledgedSeconds());
  };

  initControls();
  setSpeed(1);
  app.loop.start();
}

// ── Start ────────────────────────────────────────────────────────────────────

initStart();
setAttr(document.documentElement, 'data-rs-version', window.RS_CFG ? window.RS_CFG.version : '0');
