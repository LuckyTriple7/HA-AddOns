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
import { STATUS_STATS, sanitizeStatusKeys } from './ui/statusStats.js';
import { Geiger } from './ui/geiger.js';

const app = {
  engine: null,
  loop: null,
  render: new Render(),
  reactor: null,
  controlsReady: false,
  horn: null,
  // Anders als Horn (pro Runde neu gebaut, siehe buildPanels()) lebt der
  // Geigerzaehler ueber die ganze Sitzung: er soll schon auf dem Startbild-
  // schirm entsperrt werden koennen (erste Kartenwahl ist die erste echte
  // Nutzergeste), lange bevor eine Runde ueberhaupt eine Engine hat.
  geiger: new Geiger(),
  session: null,
  scenarios: [],
  chosen: null,      // gewaehltes Szenario oder null fuer freies Spiel
  prefs: {},         // gespeicherte Einstellungen des Spielers, siehe /api/prefs
};

// Einmal beim Laden geholt, nicht bei jedem Rundenstart neu: boot() wartet
// darauf, bevor es die Kopfzeile baut, damit die gespeicherte Auswahl schon
// beim allerersten Spiel dieser Sitzung greift. Schlaegt es fehl (kein
// Server, Sitzung abgelaufen), bleibt app.prefs leer -- dieselbe Kopfzeile
// wie eh und je, kein Absturz.
app.prefsPromise = api.readPrefs().then((r) => {
  app.prefs = (r.ok && r.data && typeof r.data === 'object') ? r.data : {};
  app.geiger.enabled = !app.prefs.audio || app.prefs.audio.geiger !== false;
  return app.prefs;
}).catch(() => app.prefs);

// ── Startbildschirm ──────────────────────────────────────────────────────────

function initStart() {
  const cards = $$('.rs-card');
  const go = $('#rs-start-go');

  // Kaltstart-Haekchen dauerhaft merken -- sonst muesste man es bei jedem
  // Besuch neu setzen, obwohl es bei jedem freien Spiel dasselbe sein soll.
  const coldBox = $('#rs-cold-start');
  app.prefsPromise.then((prefs) => { coldBox.checked = !!prefs.coldStart; });
  coldBox.addEventListener('change', () => {
    app.prefs.coldStart = coldBox.checked;
    api.writePrefs(app.prefs);
  });

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
    else boot(app.reactor, null, null, $('#rs-cold-start').checked);
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

  // Szenarienliste: einmal fuer die ganze Sitzung. Geht sie schief, bleibt
  // das freie Spiel spielbar -- das Spiel muss ohne den Server auskommen, er
  // liefert hier nur Listen.
  app.scenariosPromise = fetch('/api/meta', { headers: { Accept: 'application/json' } })
    .then((r) => (r.ok ? r.json() : null))
    .then((m) => { if (m && m.scenarios) app.scenarios = m.scenarios; })
    .catch(() => {});

  refreshResumeList();
}

/** Fortsetzen-Liste neu vom Server holen -- nicht nur beim allerersten
 *  Laden: ein Spielstand von eben (Knopf "Speichern") oder ein geloeschter
 *  muss beim naechsten Blick auf den Startbildschirm stimmen, siehe
 *  toMenu(). Der Szenariotitel braucht die einmalig geholte Szenarienliste,
 *  sonst zeigt der Hinweis nur die rohe ID. */
function refreshResumeList() {
  const list = $('#rs-resume-list');
  Promise.all([app.scenariosPromise, api.listSaves()]).then(([, r]) => {
    const saves = (r.ok && r.data && r.data.saves) || [];
    // Ein Slot je Reaktortyp ("auto-<typ>"), nicht mehr der eine gemeinsame
    // "auto"-Slot von vorher -- ein Stand beim DWR ueberschreibt seither
    // keinen beim SWR mehr. Aeltere Spielstaende aus der Zeit davor (Slot
    // "auto") tauchen hier nicht mehr auf.
    const autos = saves.filter((x) => x.slot && x.slot.startsWith('auto-'));
    list.replaceChildren(...autos.map((sv) => {
      const scn = sv.scenario && app.scenarios.find((x) => x.id === sv.scenario);
      const btn = el('button.rs-btn', { type: 'button' }, [t('btn_resume_named', {
        reactor: t('reactor_' + sv.reactor),
        scenario: sv.scenario ? t(scn ? scn.title_key : 'scn_unknown') : t('scn_free'),
        when: new Date(sv.saved_at * 1000).toLocaleString(),
      })]);
      btn.disabled = !isAvailable(sv.reactor);
      btn.addEventListener('click', () => boot(sv.reactor, null, sv.slot));
      return el('div.rs-resume-row', null, [btn, makeDeleteSaveButton(sv.slot)]);
    }));
    list.hidden = !autos.length;
  });
}

/** Löschen mit Sicherung wie beim SCRAM: erster Klick bewaffnet nur, der
 *  zweite (binnen 4s) löscht wirklich -- kein Modal fuer eine Aktion, die
 *  sich durchs blosse Weiterspielen jederzeit neu erzeugen liesse. */
function makeDeleteSaveButton(slot) {
  const btn = el('button.rs-btn.rs-btn-ghost.rs-btn-sm', { type: 'button' }, [t('btn_delete')]);
  let armed = 0;
  btn.addEventListener('click', () => {
    if (!armed) {
      armed = window.setTimeout(() => { armed = 0; setText(btn, t('btn_delete')); }, 4000);
      setText(btn, t('btn_confirm_delete'));
      return;
    }
    window.clearTimeout(armed);
    api.deleteSave(slot).then(() => refreshResumeList());
  });
  return btn;
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
    if (app.horn) app.horn.scram();
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

  // Kachel als Fenster: Klick auf die Kopfzeile hebt den echten
  // rs-panel-body-Knoten ins Fenster -- verschoben, nicht geklont, also
  // bleiben data-v-Ziele, Knöpfe und IDs eindeutig. Das gewohnte Scrollen im
  // Raster bleibt unverändert, das Fenster ist nur eine zweite Sicht obendrauf.
  // Auf dem Handy zeigt der Reiter das Panel schon voll -- dort bleibt der
  // Klick wirkungslos.
  const panelWindow = $('#rs-panel-window');
  const panelWindowBox = $('.rs-modal-box', panelWindow);
  const panelWindowSlot = $('#rs-panel-window-slot');
  const panelWindowTitle = $('#rs-panel-window-title');
  const desktopMQ = matchMedia('(min-width: 1024px)');
  let openPanel = null; // { section, body, placeholder }

  const closePanelWindow = () => {
    if (!openPanel) return;
    openPanel.section.insertBefore(openPanel.body, openPanel.placeholder);
    openPanel.placeholder.remove();
    openPanel = null;
    panelWindow.hidden = true;
    panelWindowSlot.replaceChildren();
  };

  const openPanelWindow = (section) => {
    if (!desktopMQ.matches) return;
    if (openPanel) closePanelWindow();
    const body = $('.rs-panel-body', section);
    if (!body) return;
    const placeholder = document.createComment('rs-panel-window-slot');
    section.insertBefore(placeholder, body);
    panelWindowSlot.append(body);
    openPanel = { section, body, placeholder };
    // .rs-panel-flush nimmt der Kachel ihr Innenpolster -- die Klasse muss mit
    // ins Fenster wandern, sonst bekommt z.B. das Fließbild plötzlich Rand.
    panelWindowBox.classList.toggle('rs-panel-flush', section.classList.contains('rs-panel-flush'));
    let title = '';
    for (const n of $('.rs-panel-h', section).childNodes) {
      if (n.nodeType === Node.TEXT_NODE) title += n.textContent;
    }
    setText(panelWindowTitle, title.trim());
    panelWindow.hidden = false;
  };

  for (const h of $$('.rs-panel-h')) {
    h.setAttribute('title', t('hint_panel_window'));
    h.addEventListener('click', (ev) => {
      if (ev.target.closest('.rs-panel-h-actions')) return;
      openPanelWindow(h.closest('.rs-panel'));
    });
  }
  $('#rs-panel-window-close').addEventListener('click', closePanelWindow);
  panelWindow.addEventListener('click', (ev) => { if (ev.target === panelWindow) closePanelWindow(); });
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && !panelWindow.hidden) closePanelWindow();
  });

  // Kopfzeile anpassen: Checkboxen aus dem Katalog, vorbelegt mit der
  // gespeicherten (oder Standard-) Auswahl fuer den GERADE LAUFENDEN
  // Reaktortyp. Speichern schreibt die Zeile fuer diesen Typ zurueck UND
  // knipst sofort die passenden Kacheln sichtbar -- applyStatusSelection()
  // ersetzt dabei keine Knoten, nur hidden/Reihenfolge, deshalb bleibt
  // panels.js' Wertebindung gueltig und die Aenderung ist sofort sichtbar,
  // ganz ohne Rundenneustart.
  const statsModal = $('#rs-stats-modal');
  const statsList = $('#rs-stats-list');
  statsList.replaceChildren(...STATUS_STATS.map(({ key, labelKey }) => {
    const box = el('input', { type: 'checkbox', value: key });
    return el('label', null, [box, t(labelKey)]);
  }));
  const audioHornBox = $('#rs-audio-horn');
  const audioGeigerBox = $('#rs-audio-geiger');
  $('#rs-stats-cfg').addEventListener('click', () => {
    const reactorId = app.lastReactor;
    const saved = app.prefs.statusBar ? app.prefs.statusBar[reactorId] : null;
    const keys = new Set(sanitizeStatusKeys(saved));
    for (const box of $$('input', statsList)) box.checked = keys.has(box.value);
    audioHornBox.checked = !app.prefs.audio || app.prefs.audio.horn !== false;
    audioGeigerBox.checked = !app.prefs.audio || app.prefs.audio.geiger !== false;
    statsModal.hidden = false;
  });
  $('#rs-stats-save').addEventListener('click', () => {
    const reactorId = app.lastReactor;
    const chosen = $$('input', statsList).filter((b) => b.checked).map((b) => b.value);
    const keys = sanitizeStatusKeys(chosen);
    app.prefs.statusBar = { ...(app.prefs.statusBar || {}), [reactorId]: keys };
    app.prefs.audio = { horn: audioHornBox.checked, geiger: audioGeigerBox.checked };
    api.writePrefs(app.prefs);
    applyStatusSelection(keys);
    if (app.horn) app.horn.enabled = audioHornBox.checked;
    app.geiger.enabled = audioGeigerBox.checked;
    flash($('#rs-stats-save'), t('stats_cfg_saved'));
  });
  $('#rs-stats-close').addEventListener('click', () => { statsModal.hidden = true; });
  statsModal.addEventListener('click', (ev) => { if (ev.target === statsModal) statsModal.hidden = true; });

  $('#rs-save').addEventListener('click', () => {
    const scnId = app.session && app.session.scenario ? app.session.scenario.id : null;
    // Eigener Slot je Reaktortyp -- ein Stand beim SWR darf den beim DWR
    // nicht mehr ueberschreiben, wie es der eine gemeinsame Slot "auto"
    // vorher tat.
    saveGame(app.engine, scnId, 'auto-' + app.lastReactor).then((ok) => {
      flash($('#rs-save'), t(ok ? 'save_ok' : 'save_failed'));
    });
  });

  $('#rs-xenon-skip').addEventListener('click', fastForwardXenon);

  $('#rs-destroyed-close').addEventListener('click', () => {
    $('#rs-destroyed').hidden = true;
    toMenu();
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

// Sekunden Sim-Zeit je Innenschritt -- derselbe Takt wie loop.js (DT), sonst
// rechnen Trips und Session hier mit anderen Schrittweiten als im normalen
// Betrieb. In Bloecken statt einem einzigen Riesenschleifendurchlauf, damit
// der Tab zwischendurch atmen kann (Fortschrittstext, kein "eingefroren").
const XENON_SKIP_DT = 0.05;
const XENON_SKIP_CHUNK = 20000;       // ~1000 Sim-s je Block
const XENON_SKIP_CAP_S = 48 * 3600;   // Notbremse, falls X aus welchem Grund auch immer nicht sinkt
// Ziel ist NICHT "X gegen null", sondern zurueck auf den Vollastwert (X* = 1,
// per Definition der Normierung in poisons.js): X steigt nach dem Abschalten
// erst noch fuer einige Stunden (Jodgrube, das Jod zerfaellt weiter nach),
// erreicht sein Maximum, faellt dann. Nachgemessen an der echten Engine (DWR,
// SCRAM aus Vollast): Maximum ~1,9 nach rund 8h, zurueck auf 1,0 nach rund
// 26h -- nahe an der oft genannten "24 Stunden" fuer den RBMK. Ein Ziel von
// nahe null braeuchte dagegen ueber 80h.
const XENON_SKIP_TARGET = 1.0;

/** Zeit im Zeitraffer aller Zeitraffer: fuer die Jodgrube muesste ein Spieler
 *  sonst 24 echte Minuten bei 60x abwarten. Nur im freien Spiel (siehe
 *  Sichtbarkeit des Knopfs) -- ein Szenario hat feste Ereigniszeiten und eine
 *  feste Dauer, die ein Tagessprung sinnlos machen wuerde. Laeuft dieselben
 *  Schritte wie der normale Betrieb (engine.step + session.step, siehe
 *  loop.afterStep), nur ohne Bildaufbau dazwischen -- ein echter Stoerfall
 *  waehrenddessen bricht sofort ab und zeigt sich normal, statt stillschweigend
 *  ueberfahren zu werden. */
async function fastForwardXenon() {
  const s = app.engine.state;
  const btn = $('#rs-xenon-skip');
  const before = btn.textContent;
  app.xenonSkipping = true;
  app.loop.setSpeed(0);
  btn.disabled = true;
  let elapsed = 0;
  while (elapsed < XENON_SKIP_CAP_S && s.X > XENON_SKIP_TARGET && !s.destroyed && !s.fault) {
    for (let i = 0; i < XENON_SKIP_CHUNK; i++) {
      app.engine.step(XENON_SKIP_DT);
      let worst = 0;
      for (const tile of app.engine.trips.tiles()) {
        if ((tile.tile === 'new' || tile.tile === 'ack') && tile.severity > worst) worst = tile.severity;
      }
      app.session.step(XENON_SKIP_DT, worst, app.engine.trips.unacknowledgedSeconds());
      elapsed += XENON_SKIP_DT;
      if (s.destroyed || s.fault) break;
    }
    setText(btn, t('btn_xenon_skip_progress', { h: (elapsed / 3600).toFixed(1) }));
    // Dem Tab eine Gelegenheit geben, das Bild und Eingaben zu bedienen --
    // sonst haengt der Browser bei 72h Notbremse mehrere Sekunden am Stueck.
    await new Promise((resolve) => { window.setTimeout(resolve, 0); });
  }
  btn.disabled = false;
  setText(btn, before);
  app.xenonSkipping = false;
  app.render.tick(s, performance.now());
  // Genau einer der drei Ausgaenge -- ein Stoerfall waehrend des Vorspulens
  // darf nie zugleich als "Xenon abgeklungen, weiter geht's" im Protokoll
  // landen.
  if (s.fault) {
    showFault(s.fault);
  } else if (s.destroyed && !app.endShown) {
    showDestroyed();
  } else {
    app.engine.ctx.log.push({ t: s.t_sim, key: 'event_time_skip', severity: 1 });
    setSpeed(1);
  }
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
  if (app.horn) app.horn.meltdown();
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
  boot(app.lastReactor, app.lastScenarioDef, null, app.lastCold);
}

function toMenu() {
  if (app.loop) app.loop.stop();
  $('#rs-app').hidden = true;
  $('#rs-start').hidden = false;
  refreshResumeList();
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

// Kachel je Katalogeintrag, ueber Rundenstarts hinweg gemerkt: applyStatus-
// Selection() knipst nur hidden um, baut aber nichts neu. Das ist der Grund,
// warum die Einstellungen-Kachel sofort wirkt, ganz ohne Rundenneustart --
// panels.js sammelt seine data-v-Bindungen einmal beim Rundenstart aus dem
// DOM und haette bei neu gebauten Knoten nur die alten weiterbeschrieben,
// unsichtbar, waehrend die neuen fuer immer auf "—" stehen (dieselbe Klasse
// Fehler wie die doppelten Rundinstrumente aus 0.0.30).
let statusTiles = null;

/** Alle 44 moeglichen Kacheln einmal bauen (verdeckt) -- einmal je
 *  Rundenstart, weil buildPanels() gleich danach seine Wertebindungen aus
 *  genau diesem DOM einsammelt. */
function buildStatusBar() {
  statusTiles = new Map(STATUS_STATS.map(({ key, labelKey }) => [key, el('div.rs-stat', { hidden: true }, [
    el('span.rs-stat-k', { text: t(labelKey) }),
    el('span.rs-stat-v', { 'data-v': key, text: '—' }),
  ])]));
  $('#rs-status-scroll').replaceChildren(...statusTiles.values());
}

/** Auswahl anzeigen: nur hidden/Reihenfolge aendern, nie Knoten ersetzen --
 *  wirkt deshalb auch mitten in einer laufenden Runde sofort. */
function applyStatusSelection(keys) {
  if (!statusTiles) return;
  for (const node of statusTiles.values()) node.hidden = true;
  const scroll = $('#rs-status-scroll');
  keys.forEach((key, i) => {
    const node = statusTiles.get(key);
    if (!node) return;
    node.hidden = false;
    node.classList.toggle('rs-stat-lead', i < 2);
    scroll.append(node); // an den Schluss, in Auswahlreihenfolge
  });
}

async function boot(reactorId, scenarioDef, loadSlot, cold) {
  const plant = getPlant(reactorId);
  if (!plant) return;

  // boot() laeuft immer synchron aus einem echten Klick heraus (Los,
  // Fortsetzen, Einweisung akzeptieren) -- die einzige verlaessliche Stelle
  // fuer eine Nutzergeste, die der Browser fuer Audio verlangt. Vor dem
  // ersten await, damit sie noch als "waehrend der Geste" zaehlt.
  app.geiger.unlock();

  // Kaltstart gilt nur fuer ein echtes freies Spiel: ein Szenario bringt
  // seine eigenen Startwerte (start_overrides) mit, ein Spielstand ueber-
  // schreibt den Zustand ohnehin gleich wieder -- trim() liefe in beiden
  // Faellen nur fuer einen Wimpernschlag unbeobachtet mit.
  const isColdStart = !!cold && !scenarioDef && !loadSlot;

  // Für den Neustart-Knopf in Auswertung und Kernzerstörung gemerkt -- ein
  // Spielstand zählt dabei nicht als Szenario, "Neustart" fängt dann frei an.
  app.lastReactor = reactorId;
  app.lastScenarioDef = loadSlot ? null : (scenarioDef || null);
  app.lastCold = isColdStart;

  // Eine laufende Schleife MUSS stehen, bevor eine neue entsteht. app.loop
  // zeigt danach auf ein neues Objekt, aber die alte Schleife lief bis dahin
  // mit setSpeed(0) weiter (Kernzerstörung pausiert nur, sie stoppt nicht) --
  // ihr rAF-Takt hätte sonst beim nächsten Bild noch einmal
  // state.destroyed && !app.endShown gesehen und die eben erst zurückgesetzte
  // Anzeige sofort wieder auf "Kernzerstörung" gestellt, mit dem neuen Motor.
  if (app.loop) app.loop.stop();

  $('#rs-start').hidden = true;
  $('#rs-app').hidden = false;

  // Wartet auf die einmal beim Laden gestartete Abfrage (siehe oben) --
  // praktisch immer schon fertig, sobald der Spieler bis hierher geklickt
  // hat. buildStatusBar() MUSS vor buildPanels() laufen: dessen
  // Wertebindungen sammelt es per querySelectorAll('[data-v]') genau einmal,
  // aus dem, was zu dem Zeitpunkt im DOM steht.
  const prefs = await app.prefsPromise;
  buildStatusBar();
  applyStatusSelection(sanitizeStatusKeys(prefs.statusBar && prefs.statusBar[reactorId]));

  app.endShown = false;
  app.engine = createEngine(plant, {
    n: isColdStart ? 1e-6 : 1.0, cold: isColdStart, seed: scenarioDef ? scenarioDef.seed : 1,
  });
  app.session = new Session(app.engine, scenarioDef);
  app.session.onEnd = (result, failed) => showDebrief(result, failed);
  app.session.start();
  app.render.clear();
  const built = buildPanels(app.engine, app.render, app.geiger);
  app.horn = built.horn;
  // Anders als der Geigerzaehler wird die Hupe bei jeder Runde neu gebaut
  // (buildPanels()), die Einstellung muss also jedes Mal neu uebertragen
  // werden.
  app.horn.enabled = !prefs.audio || prefs.audio.horn !== false;

  const xenonSkipBtn = $('#rs-xenon-skip');
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

    // Nur im freien Spiel: ein Szenario hat eine feste Dauer und Ereignisse
    // zu festen Zeiten, ein Tagessprung wuerde beides aushebeln. X > 0,05
    // heisst noch spuerbar ueber dem Vollastwert, keine willkuerliche Zahl --
    // dieselbe Grenze, die die Vorspul-Schleife selbst als Ziel nimmt.
    if (!app.xenonSkipping) {
      xenonSkipBtn.hidden = !(app.session && app.session.free
        && state.scram.active && state.X > XENON_SKIP_TARGET);
    }
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
