// Geigerzähler-Ticken.
//
// Reines Atmosphäre-Element, keine Messgröße: eine Leitwarte hat normalerweise
// keine spürbare Strahlung. Tickt trotzdem gelegentlich im Leerlauf (ein
// Klassenraum-Dosimeter tickt schließlich auch bei Nulllast), viel schneller
// im Takt einer Störung -- je höher die schwerste anstehende Meldung, desto
// dichter die Klicks. Dasselbe Muster wie Horn in annunciator.js: eigener
// AudioContext, erst nach einer Nutzergeste (unlock), ein/ausschaltbar.

/** Klicks je Sekunde, im Mittel, nach Schwere gestaffelt. 0 = keine Meldung. */
const RATE_HZ = [0.1, 0.5, 3, 10];

export class Geiger {
  constructor() {
    this.ctx = null;
    this.enabled = true;
    this._noise = null;
    this._nextTick = 0;
  }

  _ensure() {
    if (this.ctx) return this.ctx;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try { this.ctx = new AC(); } catch { this.ctx = null; }
    return this.ctx;
  }

  /** Muss aus einer echten Nutzergeste kommen (Klickhandler) -- Browser
   *  verweigern sonst jeden Ton. */
  unlock() {
    const ctx = this._ensure();
    if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {});
  }

  _noiseBuffer(ctx) {
    if (this._noise) return this._noise;
    const len = Math.round(ctx.sampleRate * 0.02);
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    this._noise = buf;
    return buf;
  }

  /** Ein einzelner Klick: 3-4 ms gefiltertes Rauschen, kaum hörbar leise --
   *  ein Geigerzähler tickt, er piept nicht. */
  _click() {
    const ctx = this._ensure();
    if (!ctx || ctx.state === 'suspended') return;
    const t0 = ctx.currentTime;
    const src = ctx.createBufferSource();
    src.buffer = this._noiseBuffer(ctx);
    const filt = ctx.createBiquadFilter();
    filt.type = 'highpass';
    filt.frequency.value = 1800;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.14, t0);
    gain.gain.exponentialRampToValueAtTime(0.001, t0 + 0.02);
    src.connect(filt).connect(gain).connect(ctx.destination);
    src.start(t0);
    src.stop(t0 + 0.02);
  }

  /**
   * Einmal je Bild aufrufen. Entscheidet selbst, ob gerade ein Klick fällig
   * ist -- ein Poisson-Prozess mit Rate nach Schwere, kein starrer Takt
   * (echte Geigerzähler klicken unregelmäßig, nicht metronomisch).
   * @param {number} severity 0-3, die schwerste anstehende Meldung
   * @param {number} nowMs performance.now()
   */
  step(severity, nowMs) {
    if (!this.enabled) return;
    if (nowMs < this._nextTick) return;
    this._click();
    const hz = RATE_HZ[Math.max(0, Math.min(3, severity))];
    // Exponentiell verteilter Abstand -- Mittelwert 1/hz, aber nie zwei
    // Klicks im immer gleichen Rhythmus.
    const gapS = -Math.log(1 - Math.random()) / hz;
    this._nextTick = nowMs + gapS * 1000;
  }
}
