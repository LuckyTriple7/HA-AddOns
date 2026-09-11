// Bedienelemente.
//
// Alles, was der Spieler anfassen kann: Stäbe, Bor, Lastanforderung, Pumpen,
// Betriebsartenschalter. Die Knoten werden einmal gebaut; im Renderlauf wird
// nur der angezeigte Wert nachgeführt.

import { el, setText, setAttr } from './dom.js';
import { t, num } from './i18n.js';

/** Umschalter Automatik / Hand. */
export function autoSwitch(labelKey, initial, onChange) {
  const btn = el('button.rs-switch', { type: 'button' });
  let value = initial;
  const paint = () => {
    setText(btn, value ? t('state_auto') : t('state_manual'));
    setAttr(btn, 'data-on', value ? '1' : '0');
  };
  btn.addEventListener('click', () => { value = !value; paint(); onChange(value); });
  paint();
  return {
    node: el('div.rs-ctl-row', null, [el('span.rs-ctl-k', { text: t(labelKey) }), btn]),
    set(v) { if (v !== value) { value = v; paint(); } },
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
