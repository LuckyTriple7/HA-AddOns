// Rundinstrument.
//
// Die SVG-Knoten werden einmal gebaut. Im Betrieb wird genau eine Custom
// Property (--rs-a, Zeigerwinkel) und ein Textknoten geschrieben -- kein
// Layout, kein innerHTML, keine neuen Knoten.

import { el, svg, setText, setVar } from './dom.js';
import { num, t } from './i18n.js';

const A0 = -120;   // Winkel bei Skalenanfang
const A1 = 120;    // Winkel bei Skalenende

/**
 * @param {object} o
 * @param {string} o.label      Beschriftung (bereits übersetzt)
 * @param {number} o.min,max    Skalenbereich
 * @param {number} [o.digits]   Nachkommastellen der Ziffernanzeige
 * @param {string} [o.unitKey]  Übersetzungsschlüssel der Einheit
 * @param {Array}  [o.bands]    [[von, bis, 'ok'|'warn'|'danger'], ...]
 */
export function gauge({ label, min, max, digits = 1, unitKey = null, bands = [] }) {
  const frac = (v) => Math.max(0, Math.min(1, (v - min) / (max - min)));
  const ang = (v) => A0 + (A1 - A0) * frac(v);
  const R = 38;
  const polar = (a, r) => {
    const rad = ((a - 90) * Math.PI) / 180;
    return [50 + r * Math.cos(rad), 50 + r * Math.sin(rad)];
  };
  const arc = (a0, a1, r) => {
    const [x0, y0] = polar(a0, r);
    const [x1, y1] = polar(a1, r);
    const large = a1 - a0 > 180 ? 1 : 0;
    return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  };

  const children = [svg('path', { class: 'rs-gauge-face', d: arc(A0, A1, R) })];
  for (const [from, to, kind] of bands) {
    children.push(svg('path', {
      class: `rs-gauge-${kind}`,
      d: arc(ang(from), ang(to), R),
    }));
  }
  for (let i = 0; i <= 10; i++) {
    const a = A0 + ((A1 - A0) * i) / 10;
    const major = i % 5 === 0;
    const [x0, y0] = polar(a, R - 6);
    const [x1, y1] = polar(a, R - (major ? 12 : 9));
    children.push(svg('line', {
      class: major ? 'rs-gauge-tick-major' : 'rs-gauge-tick',
      x1: x0.toFixed(2), y1: y0.toFixed(2), x2: x1.toFixed(2), y2: y1.toFixed(2),
    }));
  }
  const needle = svg('line', { class: 'rs-gauge-needle', x1: 50, y1: 50, x2: 50, y2: 18 });
  children.push(needle, svg('circle', { class: 'rs-gauge-hub', cx: 50, cy: 50, r: 4 }));

  const read = el('div.rs-gauge-read');
  const node = el('div.rs-gauge', null, [
    svg('svg', { viewBox: '0 0 100 86', 'aria-hidden': 'true' }, children),
    el('div.rs-gauge-label', { text: label, title: label }),
    read,
  ]);

  const unit = unitKey ? el('span.rs-u', { text: ' ' + t(unitKey) }) : null;
  const numNode = document.createTextNode('—');
  read.append(numNode);
  if (unit) read.append(unit);

  return {
    node,
    set(value) {
      if (!Number.isFinite(value)) {
        setVar(node, '--rs-a', A0);
        if (numNode.nodeValue !== '—') numNode.nodeValue = '—';
        return;
      }
      setVar(node, '--rs-a', ang(value).toFixed(2));
      const txt = num(value, digits);
      if (numNode.nodeValue !== txt) numNode.nodeValue = txt;
    },
  };
}

/** Senkrechter Balken -- für Stabstellungen und Füllstände. */
export function bar({ label, invert = false }) {
  const fill = el('div.rs-bar-fill');
  const demand = el('div.rs-bar-demand');
  const value = el('div.rs-bar-v', { text: '—' });
  const node = el('div.rs-bar', null, [
    el('div.rs-bar-track', null, [fill, demand]),
    el('div.rs-bar-k', { text: label }),
    value,
  ]);
  return {
    node,
    /** @param {number} f 0..1 @param {number|null} d Sollwert 0..1 */
    set(f, d = null) {
      const v = Math.max(0, Math.min(1, invert ? 1 - f : f));
      setVar(fill, '--rs-f', v);
      if (d === null) demand.hidden = true;
      else {
        demand.hidden = false;
        setVar(demand, '--rs-d', Math.max(0, Math.min(1, invert ? 1 - d : d)));
      }
      setText(value, num(f * 100, 0) + ' %');
    },
  };
}

/** Reaktivitätsbilanz: je Beitrag ein Balken um die Nulllinie. */
export function reactivityBars(ids) {
  const rows = new Map();
  const node = el('div.rs-rho');
  for (const id of ids) {
    const fill = el('div.rs-rho-fill');
    const val = el('div.rs-rho-v', { text: '—' });
    const row = el(id === 'total' ? 'div.rs-rho-row.rs-rho-row-total' : 'div.rs-rho-row', null, [
      el('div.rs-rho-k', { text: t('rho_' + id) }),
      el('div.rs-rho-track', null, [fill]),
      val,
    ]);
    rows.set(id, { fill, val });
    node.append(row);
  }
  return {
    node,
    /** @param {object} breakdown in Δk/k @param {number} scalePcm Vollausschlag */
    set(breakdown, total, scalePcm = 3000) {
      for (const [id, r] of rows) {
        const pcm = (id === 'total' ? total : (breakdown[id] || 0)) * 1e5;
        const f = Math.max(-1, Math.min(1, pcm / scalePcm));
        // Links und Breite fertig ausrechnen: CSS-abs() ist für ältere
        // Handy-Browser zu jung.
        const half = Math.abs(f) * 50;
        setVar(r.fill, '--rs-l', (f < 0 ? 50 - half : 50) + '%');
        setVar(r.fill, '--rs-w', half + '%');
        r.fill.dataset.neg = f < 0 ? '1' : '0';
        setText(r.val, num(pcm, 0));
      }
    },
  };
}
