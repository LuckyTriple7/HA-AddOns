// Einstieg: Startbildschirm, Aufbau des Leitstands, Verdrahtung der Bedienung.

import { $, $$, el, setText, setAttr } from './ui/dom.js';
import { t, clock } from './ui/i18n.js';
import { Render } from './ui/render.js';
import { buildPanels } from './ui/panels.js';
import { Loop } from './loop.js';
import { createEngine } from './sim/engine.js';
import { getPlant, isAvailable } from './plants/index.js';
import { Session, PHASE } from './game/session.js';
import { api } from './net/api.js';
import { save as saveGame, load as loadGame } from './net/persist.js';
import { GLOSSARY } from './ui/glossary.js';

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
      // Ausgrauen NUR hier, nie fest im Template: dort blieb die Klasse nach
      // dem Bau von SWR und RBMK stehen, und zwei fertige Reaktortypen sahen
      // monatelang aus wie Vorschau.
      card.disabled = true;
      card.classList.add('rs-card-soon');
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

  $('#rs-debrief-send').addEventListener('click', () => {
    const result = app.pendingResult;
    if (!result) return;
    const nameNode = $('#rs-debrief-name');
    const name = nameNode.value.trim();
    if (!name) { nameNode.focus(); return; }
    try { window.localStorage.setItem('rs-name', name); } catch { /* privates Fenster */ }
    const msg = $('#rs-debrief-msg');
    // Der Punktestand wird bewusst NICHT mitgeschickt -- der Server rechnet ihn
    // aus denselben Kennzahlen selbst nach.
    api.submitScore(name, result.summary).then((r) => {
      if (r.ok) {
        setText(msg, t('debrief_sent'));
        $('#rs-debrief-submit').hidden = true;
        loadScores(result.summary.reactor, result.summary.scenario);
      } else {
        const why = r.status === 429 ? t('debrief_rate_limited')
          : (r.status === 0 ? t('debrief_offline') : ((r.data && r.data.error) || String(r.status)));
        setText(msg, t('debrief_send_failed', { n: why }));
      }
    });
  });

  $('#rs-debrief-close').addEventListener('click', () => {
    $('#rs-debrief').hidden = true;
    toMenu();
  });

  $('#rs-debrief-restart').addEventListener('click', () => {
    $('#rs-debrief').hidden = true;
    restart();
  });

  $('#rs-destroyed-restart').addEventListener('click', () => {
    $('#rs-destroyed').hidden = true;
    restart();
  });

  // Gibt es einen Spielstand, laesst er sich von hier fortsetzen.
  api.listSaves().then((r) => {
    const auto = r.ok && r.data && (r.data.saves || []).find((x) => x.slot === 'auto');
    if (!auto) return;
    app.savedGame = auto;
    const resume = $('#rs-resume');
    resume.hidden = false;
    resume.title = t('save_slot', { n: new Date(auto.saved_at * 1000).toLocaleString() });
  });

  $('#rs-resume').addEventListener('click', () => {
    const saved = app.savedGame;
    if (!saved || !isAvailable(saved.reactor)) return;
    boot(saved.reactor, null, saved.slot);
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
    setText(scram, scramLabel());
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

  // Grundlagen-Glossar: einmal aus GLOSSARY gebaut, danach nur ein-/
  // ausgeblendet. Kein Tutorial mit Pflichtschritten -- ein Nachschlagewerk,
  // das jederzeit erreichbar ist, für wen die Meldetafel-Hilfe allein nicht
  // reicht.
  const glossaryModal = $('#rs-glossary-modal');
  $('#rs-glossary-list').replaceChildren(...GLOSSARY.flatMap((e) => [
    el('dt', { text: t(e.term) }),
    el('dd', { text: t(e.def) }),
  ]));
  $('#rs-glossary').addEventListener('click', () => { glossaryModal.hidden = false; });
  $('#rs-glossary-close').addEventListener('click', () => { glossaryModal.hidden = true; });
  glossaryModal.addEventListener('click', (ev) => { if (ev.target === glossaryModal) glossaryModal.hidden = true; });

  $('#rs-save').addEventListener('click', () => {
    const scnId = app.session && app.session.scenario ? app.session.scenario.id : null;
    saveGame(app.engine, scnId, 'auto').then((ok) => {
      flash($('#rs-save'), t(ok ? 'save_ok' : 'save_failed'));
    });
  });

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

/** Kurze Rueckmeldung auf einem Knopf, ohne Dialog. */
function flash(node, text) {
  const before = node.textContent;
  setText(node, text);
  window.setTimeout(() => setText(node, before), 2000);
}

/** Beschriftung der Schnellabschaltung -- sie gehört dem Reaktortyp.
 *  RESA im deutschen Leitstand, SCRAM im englischen, AZ-5 beim RBMK. */
function scramLabel() {
  const sp = app.engine && app.engine.spec;
  return t((sp && sp.scram && sp.scram.labelKey) || 'btn_scram');
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

/** Gleicher Reaktortyp, gleiches Szenario (oder freies Spiel), sofort von
 *  vorn -- ohne den Umweg über Menü, Typwahl und Einweisung. */
function restart() {
  if (!app.lastReactor) { toMenu(); return; }
  boot(app.lastReactor, app.lastScenarioDef);
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
  // Eintragen nur, wenn es eine Wertung gibt und es ein Szenario war.
  const submit = $('#rs-debrief-submit');
  const msg = $('#rs-debrief-msg');
  setText(msg, '');
  $('#rs-debrief-scores').replaceChildren();
  submit.hidden = !result;
  if (result) {
    app.pendingResult = result;
    const name = $('#rs-debrief-name');
    try { name.value = window.localStorage.getItem('rs-name') || ''; } catch { /* privates Fenster */ }
    loadScores(result.summary.reactor, result.summary.scenario);
  }
  $('#rs-debrief').hidden = false;
}

/** Bestenliste zum gerade gespielten Szenario nachladen. */
function loadScores(reactor, scenario) {
  api.listScores(reactor, scenario, 10).then((r) => {
    const list = $('#rs-debrief-scores');
    list.replaceChildren();
    if (!r.ok || !r.data || !r.data.scores) return;
    for (const e of r.data.scores) {
      list.append(el('li', null, [
        // textContent, nie innerHTML: der Name kommt von einem anderen Spieler.
        el('span.rs-score-name', { text: e.name }),
        el('span.rs-score-v', { text: String(e.score) }),
      ]));
    }
  });
}

function boot(reactorId, scenarioDef, loadSlot) {
  const plant = getPlant(reactorId);
  if (!plant) return;

  // Für den Neustart-Knopf in Auswertung und Kernzerstörung gemerkt -- ein
  // Spielstand zählt dabei nicht als Szenario, "Neustart" fängt dann frei an.
  app.lastReactor = reactorId;
  app.lastScenarioDef = loadSlot ? null : (scenarioDef || null);

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
  const scramBtn = $('#rs-scram');
  setText(scramBtn, scramLabel());
  setAttr(scramBtn, 'title', t((plant.spec.scram && plant.spec.scram.titleKey) || 'btn_scram'));
  setSpeed(1);
  app.loop.start();

  // Einen Spielstand erst anwenden, wenn die Anlage steht: die Regler und
  // Pumpen schwingen sich dann aus dem geladenen Zustand von selbst ein.
  if (loadSlot) {
    loadGame(app.engine, loadSlot).then((err) => {
      if (err) flash($('#rs-save'), t('load_failed'));
    });
  }
}

// ── Start ────────────────────────────────────────────────────────────────────

initStart();
setAttr(document.documentElement, 'data-rs-version', window.RS_CFG ? window.RS_CFG.version : '0');
