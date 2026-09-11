// Meldetafel und Ereignisprotokoll.
//
// Die Kacheln werden einmal gebaut, danach wird nur data-st gesetzt -- Farbe,
// Blinken und Hupe entstehen daraus in CSS.

import { el, setAttr, setText } from './dom.js';
import { t, clock } from './i18n.js';

export class Annunciator {
  constructor(container, logNode, defs, onSelect) {
    this.container = container;
    this.logNode = logNode;
    this.tiles = new Map();
    container.replaceChildren();
    for (const d of defs) {
      const node = el('div.rs-tile', {
        'data-sev': d.severity,
        'data-st': 'normal',
        title: t(d.key),
        role: onSelect ? 'button' : null,
        tabindex: onSelect ? '0' : null,
      }, [t(d.key)]);
      // Eine Meldung erklärt sich nicht selbst -- Klick (oder Enter/Leertaste
      // an der Tastatur) zeigt, was sie bedeutet und was zu tun ist.
      if (onSelect) {
        node.addEventListener('click', () => onSelect(d));
        node.addEventListener('keydown', (ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onSelect(d); }
        });
      }
      this.tiles.set(d.id, node);
      container.append(node);
    }
    this.logNode.replaceChildren();
    this.logCount = 0;
  }

  update(tiles) {
    for (const tile of tiles) {
      const node = this.tiles.get(tile.id);
      if (node) setAttr(node, 'data-st', tile.tile);
    }
  }

  /** Protokolleinträge anhängen. Neueste oben, Länge begrenzt. */
  log(entries) {
    for (const e of entries) {
      const li = el('li', { 'data-sev': e.severity || 1 }, [
        el('time', { text: clock(e.t) }),
        el('span', {
          text: t(e.key) + (e.kind ? ' — ' + t('event_' + e.kind) : '')
                + (e.cause ? ' (' + t(e.cause === 'manual' ? 'state_manual' : e.cause) + ')' : ''),
        }),
      ]);
      this.logNode.prepend(li);
      this.logCount++;
    }
    while (this.logCount > 120) {
      this.logNode.removeChild(this.logNode.lastChild);
      this.logCount--;
    }
  }
}

/** Kurze Hupe über die Web Audio API -- keine Datei, kein Download. */
export class Horn {
  constructor() {
    this.ctx = null;
    this.on = false;
    this.enabled = true;
  }

  _ensure() {
    if (this.ctx) return this.ctx;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try { this.ctx = new AC(); } catch { this.ctx = null; }
    return this.ctx;
  }

  /** Einzelner kurzer Ton. Wird im Takt der blinkenden Kachel gerufen. */
  beep(freq = 660, ms = 120) {
    if (!this.enabled) return;
    const ctx = this._ensure();
    if (!ctx || ctx.state === 'suspended') return;
    const t0 = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'square';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.05, t0 + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + ms / 1000);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t0);
    osc.stop(t0 + ms / 1000 + 0.02);
  }

  /** Muss aus einer Benutzergeste heraus laufen, sonst bleibt der Ton stumm. */
  unlock() {
    const ctx = this._ensure();
    if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {});
  }
}
