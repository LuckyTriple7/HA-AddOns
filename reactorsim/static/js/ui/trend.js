// Trendschreiber auf Canvas.
//
// Ringpuffer je Kanal, abgetastet in Simulationszeit (1 Hz), nicht in
// Realzeit -- sonst hätte der Zeitraffer eine gestauchte Kurve zur Folge.
//
// Gezeichnet wird mit Min/Max-Dezimierung je Bildspalte: bei 8 Stunden auf
// 400 Pixeln fielen sonst genau die Spitzen heraus, die interessant sind.
// Kein Blit-Scrolling -- das bricht bei Geräteskalierung und bei jedem
// Größenwechsel.

import { el } from './dom.js';
import { t, num } from './i18n.js';

const CAPACITY = 3600 * 8;   // acht Stunden bei einer Abtastung je Sekunde

export class TrendRecorder {
  /** @param {{id:string, key:string, color:string, get:(s,d)=>number}[]} channels */
  constructor(channels, { titleKey, fmt = 1 }) {
    this.channels = channels;
    this.fmt = fmt;
    this.data = channels.map(() => new Float32Array(CAPACITY));
    this.time = new Float64Array(CAPACITY);
    this.count = 0;
    this.head = 0;
    this.rangeS = 600;
    this.nextSample = 0;

    this.canvas = el('canvas.rs-trend-canvas');
    this.legend = el('div.rs-trend-legend');
    for (const c of channels) {
      this.legend.append(el('span.rs-trend-key', { '--rs-c': c.color }, [
        el('i'), document.createTextNode(t(c.key)),
      ]));
    }
    this.node = el('div.rs-trend', null, [
      el('div.rs-trend-head', null, [
        el('span.rs-trend-title', { text: t(titleKey) }),
        this.legend,
      ]),
      this.canvas,
    ]);
    this.ctx = this.canvas.getContext('2d');
  }

  setRange(seconds) { this.rangeS = seconds; }

  /** Abtasten -- in Simulationssekunden, nicht in Bildern. */
  sample(s, d) {
    if (s.t_sim < this.nextSample) return;
    this.nextSample = s.t_sim + 1;
    const i = this.head;
    this.time[i] = s.t_sim;
    for (let c = 0; c < this.channels.length; c++) {
      const v = this.channels[c].get(s, d);
      this.data[c][i] = Number.isFinite(v) ? v : NaN;
    }
    this.head = (i + 1) % CAPACITY;
    if (this.count < CAPACITY) this.count++;
  }

  draw() {
    const cv = this.canvas;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = cv.clientWidth, h = cv.clientHeight;
    if (w === 0 || h === 0) return;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
    }
    const g = this.ctx;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    if (this.count < 2) return;

    const tNow = this.time[(this.head - 1 + CAPACITY) % CAPACITY];
    const tMin = tNow - this.rangeS;

    // Wertebereich über alle Kanäle im Fenster.
    let lo = Infinity, hi = -Infinity;
    const idx = [];
    for (let k = 0; k < this.count; k++) {
      const i = (this.head - 1 - k + CAPACITY * 2) % CAPACITY;
      if (this.time[i] < tMin) break;
      idx.push(i);
      for (let c = 0; c < this.channels.length; c++) {
        const v = this.data[c][i];
        if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
      }
    }
    if (!Number.isFinite(lo) || idx.length < 2) return;
    if (hi - lo < 1e-6) { hi = lo + 1; lo -= 1; }
    const pad = (hi - lo) * 0.12;
    lo -= pad; hi += pad;

    const x = (tt) => ((tt - tMin) / this.rangeS) * (w - 34) + 2;
    const y = (v) => h - 14 - ((v - lo) / (hi - lo)) * (h - 20);

    // Gitter
    g.strokeStyle = '#1b2430';
    g.lineWidth = 1;
    g.beginPath();
    for (let i = 0; i <= 4; i++) {
      const yy = Math.round(y(lo + ((hi - lo) * i) / 4)) + 0.5;
      g.moveTo(2, yy); g.lineTo(w - 32, yy);
    }
    g.stroke();

    g.fillStyle = '#56656f';
    g.font = '9px ui-monospace, monospace';
    g.textAlign = 'left';
    g.fillText(num(hi, this.fmt), w - 30, y(hi) + 8);
    g.fillText(num(lo, this.fmt), w - 30, y(lo) - 2);

    // Min/Max je Bildspalte: bei acht Stunden auf 400 Pixeln kommen 28 800
    // Abtastungen auf 400 Spalten. Wer da jeden Punkt zeichnet, malt siebzig
    // Linien uebereinander und verliert trotzdem die Spitzen -- die letzte
    // gezeichnete Linie gewinnt. Mit Min und Max je Spalte bleibt jeder
    // Ausschlag sichtbar, und es sind zwei Werte statt siebzig.
    const cols = Math.max(1, Math.floor(w - 34));
    const mins = new Float64Array(cols);
    const maxs = new Float64Array(cols);

    for (let c = 0; c < this.channels.length; c++) {
      mins.fill(Infinity);
      maxs.fill(-Infinity);
      for (let k = 0; k < idx.length; k++) {
        const i = idx[k];
        const v = this.data[c][i];
        if (!Number.isFinite(v)) continue;
        let col = Math.floor(x(this.time[i]) - 2);
        if (col < 0) col = 0; else if (col >= cols) col = cols - 1;
        if (v < mins[col]) mins[col] = v;
        if (v > maxs[col]) maxs[col] = v;
      }

      g.strokeStyle = this.channels[c].color;
      g.lineWidth = 1.4;
      g.beginPath();
      let started = false;
      for (let col = 0; col < cols; col++) {
        if (mins[col] === Infinity) { continue; }
        const px = col + 2.5;
        const yTop = y(maxs[col]);
        const yBot = y(mins[col]);
        if (!started) { g.moveTo(px, yBot); started = true; } else g.lineTo(px, yBot);
        if (yTop !== yBot) g.lineTo(px, yTop);
      }
      g.stroke();
    }
  }
}
