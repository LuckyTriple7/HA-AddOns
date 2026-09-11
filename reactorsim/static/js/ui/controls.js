// Bedienelemente.
//
// Alles, was der Spieler anfassen kann: Stäbe, Bor, Lastanforderung, Pumpen,
// Betriebsartenschalter. Die Knoten werden einmal gebaut; im Renderlauf wird
// nur der angezeigte Wert nachgeführt.

import { el, setText, setAttr } from './dom.js';
import { t, num } from './i18n.js';

/**
 * Umschalter Automatik / Hand.
 *
 * Zwei Felder nebeneinander, das geltende hervorgehoben -- wie der
 * Zeitraffer-Wähler. Der erste Entwurf war EIN Knopf, der seinen Zustand als
 * Aufschrift trug. Das liest sich falsch herum: „Turbinenregler [Hand]" sieht
 * aus wie ein Angebot, auf Hand zu schalten, und nicht wie die Feststellung,
 * dass er längst auf Hand steht. In einer Leitwarte muss auf einen Blick
 * sichtbar sein, was gilt -- nicht, was passieren würde.
 */
export function autoSwitch(labelKey, initial, onChange) {
  let value = initial;
  const mk = (key, target) => {
    const b = el('button.rs-seg', { type: 'button' }, [t(key)]);
    b.addEventListener('click', () => {
      if (value === target) return;
      value = target;
      paint();
      onChange(value);
    });
    return b;
  };
  const autoBtn = mk('state_auto', true);
  const manBtn = mk('state_manual', false);
  const paint = () => {
    autoBtn.classList.toggle('rs-on', value);
    manBtn.classList.toggle('rs-on', !value);
    autoBtn.setAttribute('aria-pressed', String(value));
    manBtn.setAttribute('aria-pressed', String(!value));
  };
  paint();
  return {
    node: el('div.rs-ctl-row', null, [
      el('span.rs-ctl-k', { text: t(labelKey) }),
      el('div.rs-segs', null, [autoBtn, manBtn]),
    ]),
    set(v) { if (v !== value) { value = v; paint(); } },
  };
}

/**
 * Regelstation: Umschalter Automatik/Hand plus Stellschieber.
 *
 * So sieht jede Regelstation in einer echten Leitwarte aus, und aus gutem
 * Grund. Der Schieber ist IMMER da und zeigt IMMER den geltenden Stellwert --
 * in Automatik führt ihn der Regler und der Schieber läuft mit, in Hand führt
 * ihn der Bediener.
 *
 * Daraus folgt die stoßfreie Übernahme: wer auf Hand schaltet, übernimmt genau
 * den Wert, der gerade steht. Nichts springt. Ein Regler, bei dem das Umschalten
 * selbst eine Störung auslöst, wird nie benutzt -- und dann ist die
 * Handbedienung wertlos, obwohl sie da ist.
 *
 * @param {object} o
 * @param {string} o.labelKey    Bezeichnung der Station
 * @param {string} o.unitKey     Einheit des Stellwerts
 * @param {()=>number} o.read    aktueller Stellwert (in Anzeigeeinheiten)
 * @param {(v:number)=>void} o.write  Handsollwert setzen
 * @param {()=>boolean} o.isAuto aktueller Betriebsartenzustand
 * @param {(v:boolean)=>void} o.setAuto  umschalten; bekommt den Ist-Wert schon übernommen
 */
export function station({ labelKey, min = 0, max = 100, step = 1, digits = 0,
                          unitKey, read, write, isAuto, setAuto, hint }) {
  let auto = isAuto();
  const input = el('input.rs-slider', { type: 'range', min, max, step, value: read() });
  const readout = el('span.rs-ctl-v');

  const paint = (v) => {
    setText(readout, num(Number(v), digits) + (unitKey ? '\u2009' + t(unitKey) : ''));
  };

  const mk = (key, target) => {
    const b = el('button.rs-seg', { type: 'button' }, [t(key)]);
    b.addEventListener('click', () => {
      if (auto === target) return;
      // Stoßfreie Übernahme: erst den Ist-Wert als Sollwert setzen, dann
      // umschalten. Andersherum regelt die Station eine Sekunde lang gegen
      // den alten Handwert, und genau das ist der Stoß.
      if (!target) write(Number(input.value));
      auto = target;
      setAuto(auto);
      sync();
    });
    return b;
  };
  const autoBtn = mk('state_auto', true);
  const manBtn = mk('state_manual', false);

  const sync = () => {
    autoBtn.classList.toggle('rs-on', auto);
    manBtn.classList.toggle('rs-on', !auto);
    autoBtn.setAttribute('aria-pressed', String(auto));
    manBtn.setAttribute('aria-pressed', String(!auto));
    input.disabled = auto;
    input.classList.toggle('rs-slider-auto', auto);
  };

  input.addEventListener('input', () => {
    paint(input.value);
    if (!auto) write(Number(input.value));
  });

  paint(read());
  sync();

  const node = el('div.rs-ctl-block', null, [
    el('div.rs-ctl-row', null, [
      el('span.rs-ctl-k', { text: t(labelKey) }),
      el('div.rs-segs', null, [autoBtn, manBtn]),
    ]),
    el('div.rs-ctl-row', null, [input, readout]),
    hint ? el('p.rs-ctl-hint', { text: t(hint) }) : null,
  ]);

  return {
    node,
    /** Nachführung im Renderlauf. In Automatik läuft der Schieber mit. */
    set() {
      const a = isAuto();
      if (a !== auto) { auto = a; sync(); }
      if (auto || document.activeElement !== input) {
        const v = read();
        const sv = String(Math.round(v / step) * step);
        if (input.value !== sv) { input.value = sv; }
        paint(v);
      }
    },
  };
}

/** Schieber mit Zahlenanzeige. */
export function slider({ labelKey, min, max, step, value, digits = 0, unitKey, onInput }) {
  const input = el('input.rs-slider', {
    type: 'range', min, max, step, value,
  });
  const read = el('span.rs-ctl-v');
  const paint = (v) => setText(read, num(Number(v), digits) + (unitKey ? ' ' + t(unitKey) : ''));
  input.addEventListener('input', () => { paint(input.value); onInput(Number(input.value)); });
  paint(value);
  return {
    node: el('div.rs-ctl-block', null, [
      el('div.rs-ctl-row', null, [el('span.rs-ctl-k', { text: t(labelKey) }), read]),
      input,
    ]),
    set(v) {
      // Nur nachführen, wenn der Benutzer gerade nicht selbst schiebt.
      if (document.activeElement === input) return;
      const s = String(v);
      if (input.value !== s) { input.value = s; paint(v); }
    },
  };
}

/** Tastengruppe -- genau eine Taste ist aktiv. */
export function buttonGroup(labelKey, options, initial, onChange) {
  const btns = options.map((o) => el('button.rs-gbtn', { type: 'button', 'data-v': o.value },
    [t(o.key)]));
  let value = initial;
  const paint = () => {
    for (const b of btns) b.classList.toggle('rs-on', b.dataset.v === String(value));
  };
  for (const b of btns) {
    b.addEventListener('click', () => { value = b.dataset.v; paint(); onChange(value); });
  }
  paint();
  return {
    node: el('div.rs-ctl-block', null, [
      el('div.rs-ctl-row', null, [el('span.rs-ctl-k', { text: t(labelKey) })]),
      el('div.rs-gbtns', null, btns),
    ]),
    set(v) { if (String(v) !== String(value)) { value = String(v); paint(); } },
  };
}

/** Halteknöpfe für die Stabfahrt -- gedrückt halten heißt fahren. */
export function jogButtons(labelKey, onJog) {
  const mk = (key, dir) => {
    const b = el('button.rs-gbtn', { type: 'button' }, [t(key)]);
    let timer = 0;
    const start = (ev) => {
      ev.preventDefault();
      // Capture: sonst bekommt der Knopf kein pointerup, wenn der Zeiger beim
      // Loslassen schon daneben steht -- der Timer liefe sonst unbemerkt
      // weiter und führe, egal was der nächste Klick will.
      if (b.setPointerCapture) { try { b.setPointerCapture(ev.pointerId); } catch { /* egal */ } }
      onJog(dir);
      // Wiederholung: der Stabantrieb faehrt, solange die Taste gehalten wird.
      timer = window.setInterval(() => onJog(dir), 100);
      b.classList.add('rs-on');
    };
    const stop = () => {
      if (timer) window.clearInterval(timer);
      timer = 0;
      b.classList.remove('rs-on');
    };
    b.addEventListener('pointerdown', start);
    b.addEventListener('pointerup', stop);
    b.addEventListener('pointerleave', stop);
    b.addEventListener('pointercancel', stop);
    // Tastatur: ein <button> nimmt Fokus von selbst, aber pointerdown/up
    // bleibt für Enter/Leertaste stumm -- ohne das hier war der Knopf nur per
    // Maus/Touch fahrbar. Der Browser wiederholt keydown von selbst, solange
    // die Taste unten bleibt, also reicht das ohne eigenen Timer.
    b.addEventListener('keydown', (ev) => {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      ev.preventDefault();
      onJog(dir);
      b.classList.add('rs-on');
    });
    b.addEventListener('keyup', (ev) => {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      b.classList.remove('rs-on');
    });
    return b;
  };
  return {
    node: el('div.rs-ctl-block', null, [
      el('div.rs-ctl-row', null, [el('span.rs-ctl-k', { text: t(labelKey) })]),
      el('div.rs-gbtns', null, [mk('ctl_rod_out', -1), mk('ctl_rod_in', 1)]),
    ]),
  };
}

/** Pumpenreihe: Zustand anzeigen, per Klick ein- und ausschalten. */
export function pumpRow(count, onToggle) {
  const btns = [];
  for (let i = 0; i < count; i++) {
    const b = el('button.rs-pump', { type: 'button', 'data-state': 'run' },
      [t('ctl_pump', { n: i + 1 })]);
    b.addEventListener('click', () => onToggle(i));
    btns.push(b);
  }
  return {
    node: el('div.rs-pumps', null, btns),
    set(states) {
      for (let i = 0; i < btns.length; i++) setAttr(btns[i], 'data-state', states[i] || 'stopped');
    },
  };
}
