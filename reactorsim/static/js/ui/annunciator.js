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
    this.onSelect = onSelect;
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
      const li = el('li', {
        'data-sev': e.severity || 1,
        role: this.onSelect ? 'button' : null,
        tabindex: this.onSelect ? '0' : null,
      }, [
        el('time', { text: clock(e.t) }),
        el('span', {
          text: t(e.key) + (e.kind ? ' — ' + t('event_' + e.kind) : '')
                + (e.cause ? ' (' + t(e.cause === 'manual' ? 'state_manual' : e.cause) + ')' : ''),
        }),
      ]);
      // Derselbe Klick-für-Erklärung wie bei den Meldetafel-Kacheln -- ein
      // Protokolleintrag ist nur eine Zeitleiste, kein Nachschlagewerk.
      if (this.onSelect) {
        li.addEventListener('click', () => this.onSelect(e));
        li.addEventListener('keydown', (ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); this.onSelect(e); }
        });
      }
      this.logNode.prepend(li);
      this.logCount++;
    }
    while (this.logCount > 120) {
      this.logNode.removeChild(this.logNode.lastChild);
      this.logCount--;
    }
  }
}

/**
 * Anlagengeräusche über die Web Audio API -- keine Datei, kein Download.
 *
 * Kein einzelner Sinuston: eine echte Hupe schwebt, weil zwei Schwinger nie
 * exakt gleich laufen, und ein Relais klackt nicht musikalisch, sondern
 * bricht ab. Deshalb hier immer mindestens zwei Klangquellen (zwei leicht
 * verstimmte Oszillatoren, oder ein Oszillator plus gefiltertes Rauschen)
 * statt eines reinen Tons -- das ist der Unterschied zwischen einer Hupe und
 * einem Piepsen.
 */
export class Horn {
  constructor() {
    this.ctx = null;
    this.on = false;
    this.enabled = true;
    this._noise = null;
  }

  _ensure() {
    if (this.ctx) return this.ctx;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try { this.ctx = new AC(); } catch { this.ctx = null; }
    return this.ctx;
  }

  /** Weißes Rauschen, einmal erzeugt und für jeden Stoß wiederverwendet --
   *  Grundlage für Klack, Zischen und den Knall der Kernzerstörung. */
  _noiseBuffer(ctx) {
    if (this._noise) return this._noise;
    const len = ctx.sampleRate * 2;
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    this._noise = buf;
    return buf;
  }

  _noiseSource(ctx, dur) {
    const src = ctx.createBufferSource();
    src.buffer = this._noiseBuffer(ctx);
    src.loopStart = 0;
    src.loopEnd = dur;
    src.loop = true;
    return src;
  }

  /**
   * Meldehupe. Zwei leicht verstimmte Sägezähne durch ein Tiefpassfilter --
   * das Schweben zwischen ihnen ist der Unterschied zu einem reinen Piepton.
   * Wird im Takt der blinkenden Kachel gerufen, TRIP-Meldungen bekommen die
   * höhere, dringlichere Stimme.
   */
  alarm(severity = 2) {
    if (!this.enabled) return;
    const ctx = this._ensure();
    if (!ctx || ctx.state === 'suspended') return;
    const t0 = ctx.currentTime;
    const urgent = severity >= 3;
    const f0 = urgent ? 480 : 340;
    const dur = urgent ? 0.22 : 0.26;

    const gain = ctx.createGain();
    const filt = ctx.createBiquadFilter();
    filt.type = 'lowpass';
    filt.frequency.value = urgent ? 2200 : 1400;
    filt.Q.value = 1.2;
    gain.connect(filt).connect(ctx.destination);

    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(urgent ? 0.16 : 0.1, t0 + 0.012);
    gain.gain.setValueAtTime(urgent ? 0.16 : 0.1, t0 + dur - 0.05);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);

    for (const detune of [-5, 5]) {
      const osc = ctx.createOscillator();
      osc.type = 'sawtooth';
      osc.frequency.value = f0;
      osc.detune.value = detune;
      osc.connect(gain);
      osc.start(t0);
      osc.stop(t0 + dur + 0.02);
    }
  }

  /**
   * Schnellabschaltung: ein Schlag (Relais/Magnetventil), dazu ein kurzer
   * metallischer Klack aus gefiltertem Rauschen, danach Zischen, das
   * abklingt -- Druckluft oder Dampf, der sich Bahn bricht.
   */
  scram() {
    const ctx = this._ensure();
    if (!ctx) return;
    if (ctx.state === 'suspended') { ctx.resume().catch(() => {}); }
    const t0 = ctx.currentTime;

    // Schlag: tiefer Sinus, hart an- und wieder abklingend.
    const thump = ctx.createOscillator();
    const thumpGain = ctx.createGain();
    thump.type = 'sine';
    thump.frequency.setValueAtTime(90, t0);
    thump.frequency.exponentialRampToValueAtTime(40, t0 + 0.15);
    thumpGain.gain.setValueAtTime(0.5, t0);
    thumpGain.gain.exponentialRampToValueAtTime(0.001, t0 + 0.22);
    thump.connect(thumpGain).connect(ctx.destination);
    thump.start(t0);
    thump.stop(t0 + 0.25);

    // Klack: kurzer, hoch gefilterter Rauschimpuls.
    const clack = this._noiseSource(ctx, 0.03);
    const clackFilt = ctx.createBiquadFilter();
    clackFilt.type = 'bandpass';
    clackFilt.frequency.value = 2200;
    clackFilt.Q.value = 0.7;
    const clackGain = ctx.createGain();
    clackGain.gain.setValueAtTime(0.35, t0);
    clackGain.gain.exponentialRampToValueAtTime(0.001, t0 + 0.05);
    clack.connect(clackFilt).connect(clackGain).connect(ctx.destination);
    clack.start(t0);
    clack.stop(t0 + 0.05);

    // Zischen: tiefpassgefiltertes Rauschen, das über gut eine Sekunde abklingt.
    const hiss = this._noiseSource(ctx, 1.2);
    const hissFilt = ctx.createBiquadFilter();
    hissFilt.type = 'lowpass';
    hissFilt.frequency.setValueAtTime(3500, t0 + 0.03);
    hissFilt.frequency.exponentialRampToValueAtTime(500, t0 + 1.2);
    const hissGain = ctx.createGain();
    hissGain.gain.setValueAtTime(0.0001, t0 + 0.03);
    hissGain.gain.exponentialRampToValueAtTime(0.12, t0 + 0.08);
    hissGain.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.2);
    hiss.connect(hissFilt).connect(hissGain).connect(ctx.destination);
    hiss.start(t0 + 0.03);
    hiss.stop(t0 + 1.25);
  }

  /**
   * Kernzerstörung: ein Knall aus gefiltertem Rauschen, darunter ein tiefes,
   * lang ausklingendes Grollen aus Oszillator plus Rauschen.
   */
  meltdown() {
    const ctx = this._ensure();
    if (!ctx) return;
    if (ctx.state === 'suspended') { ctx.resume().catch(() => {}); }
    const t0 = ctx.currentTime;

    // Knall: breitbandiges Rauschen, kurz und laut.
    const bang = this._noiseSource(ctx, 0.4);
    const bangFilt = ctx.createBiquadFilter();
    bangFilt.type = 'bandpass';
    bangFilt.frequency.value = 260;
    bangFilt.Q.value = 0.5;
    const bangGain = ctx.createGain();
    bangGain.gain.setValueAtTime(0.6, t0);
    bangGain.gain.exponentialRampToValueAtTime(0.001, t0 + 0.4);
    bang.connect(bangFilt).connect(bangGain).connect(ctx.destination);
    bang.start(t0);
    bang.stop(t0 + 0.4);

    // Grollen: tiefer Oszillator plus gefiltertes Rauschen, mehrere Sekunden.
    const rumble = ctx.createOscillator();
    const rumbleGain = ctx.createGain();
    rumble.type = 'triangle';
    rumble.frequency.setValueAtTime(70, t0);
    rumble.frequency.exponentialRampToValueAtTime(32, t0 + 3.5);
    rumbleGain.gain.setValueAtTime(0.0001, t0);
    rumbleGain.gain.exponentialRampToValueAtTime(0.28, t0 + 0.2);
    rumbleGain.gain.exponentialRampToValueAtTime(0.0001, t0 + 3.5);
    rumble.connect(rumbleGain).connect(ctx.destination);
    rumble.start(t0);
    rumble.stop(t0 + 3.6);

    const rNoise = this._noiseSource(ctx, 3.2);
    const rNoiseFilt = ctx.createBiquadFilter();
    rNoiseFilt.type = 'lowpass';
    rNoiseFilt.frequency.value = 220;
    const rNoiseGain = ctx.createGain();
    rNoiseGain.gain.setValueAtTime(0.0001, t0 + 0.1);
    rNoiseGain.gain.exponentialRampToValueAtTime(0.15, t0 + 0.3);
    rNoiseGain.gain.exponentialRampToValueAtTime(0.0001, t0 + 3.3);
    rNoise.connect(rNoiseFilt).connect(rNoiseGain).connect(ctx.destination);
    rNoise.start(t0 + 0.1);
    rNoise.stop(t0 + 3.4);
  }

  /** Muss aus einer Benutzergeste heraus laufen, sonst bleibt der Ton stumm. */
  unlock() {
    const ctx = this._ensure();
    if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {});
  }
}
