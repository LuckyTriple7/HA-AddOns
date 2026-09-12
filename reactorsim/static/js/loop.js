// Simulationstakt, entkoppelt von der Darstellung.
//
// Der Zeitschritt ist mit 0,05 s Simulationszeit fest verdrahtet und ändert
// sich mit dem Zeitraffer NICHT. Der Faktor bestimmt allein, wie viele
// Schritte je Realsekunde laufen (20 / 80 / 320 / 1200). Damit rechnet 60×
// genauso genau wie 1×.

export const DT = 0.05;

// Obergrenze je Bild. Ohne sie entsteht auf einem langsamen Gerät die
// Todesspirale: der Rückstand wächst, die Aufholschleife wird länger, das
// nächste Bild kommt noch später. Überschuss wird verworfen und gemeldet,
// nie angesammelt.
const MAX_STEPS_PER_FRAME = 64;

export class Loop {
  /**
   * @param {{step: (dt:number)=>void}} engine
   * @param {(engineState:any, nowMs:number)=>void} render
   */
  constructor(engine, render) {
    this.engine = engine;
    this.render = render;
    this.speed = 1;          // 0 = angehalten
    this.acc = 0;
    this.last = 0;
    this.slip = false;
    this.running = false;
    this.onSlip = null;
    /** Wird nach JEDEM Simulationsschritt gerufen, nicht je Bild. Die
     *  Spielschicht muss jeden Schritt sehen: eine Stoerung, die auf Sekunde
     *  1200 faellt, darf bei 60-fachem Zeitraffer nicht zwischen zwei Bildern
     *  verschwinden. */
    this.afterStep = null;
    /** Wird gerufen, wenn engine.step()/afterStep() innerhalb eines Bildes
     *  wirft. Ohne Fang hier stirbt die ganze rAF-Kette lautlos: running
     *  bleibt true, aber requestAnimationFrame wird nie wieder aufgerufen --
     *  ein Einfrieren ohne jede sichtbare Meldung. */
    this.onCrash = null;
    this._frame = this._frame.bind(this);
    this._onVisibility = this._onVisibility.bind(this);
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.last = performance.now();
    this.acc = 0;
    document.addEventListener('visibilitychange', this._onVisibility);
    requestAnimationFrame(this._frame);
  }

  stop() {
    this.running = false;
    document.removeEventListener('visibilitychange', this._onVisibility);
  }

  setSpeed(v) {
    this.speed = v;
    // Beim Wechsel den Rückstand verwerfen: sonst schiebt ein eben noch bei
    // 60× aufgelaufener Rest nach dem Umschalten auf 1× noch minutenlang nach.
    this.acc = 0;
    this.last = performance.now();
  }

  _onVisibility() {
    // Im Hintergrund liefert der Browser keine Frames. Ohne dieses Zurücksetzen
    // stünde beim Zurückkommen ein Rückstand von Minuten an.
    if (!document.hidden) {
      this.last = performance.now();
      this.acc = 0;
    }
  }

  _frame(now) {
    if (!this.running) return;
    // Deckel gegen Ausreißer (Tabwechsel, Bildschirmsperre, Debugger-Pause).
    const dtReal = Math.min((now - this.last) / 1000, 0.25);
    this.last = now;

    // Alles Rechnende in einem Fang: fliegt irgendwo in engine.step(),
    // afterStep() oder render() ein Fehler, darf das nicht die rAF-Kette
    // abreißen (running bliebe true, aber kein Bild käme je wieder) --
    // vorher gab es genau das: ein lautloses Einfrieren ohne jede Meldung.
    try {
      if (this.speed > 0) {
        this.acc += dtReal * this.speed;
        let steps = 0;
        while (this.acc >= DT && steps < MAX_STEPS_PER_FRAME) {
          this.engine.step(DT);
          if (this.afterStep) this.afterStep(DT);
          this.acc -= DT;
          steps++;
        }
        const slipping = this.acc >= DT;
        if (slipping) this.acc = 0;
        if (slipping !== this.slip) {
          this.slip = slipping;
          if (this.onSlip) this.onSlip(slipping);
        }
      }

      this.render(this.engine.state, now);
    } catch (err) {
      console.error('[reactorsim] Simulationsschritt abgebrochen:', err);
      this.stop();
      if (this.onCrash) this.onCrash(err);
      return;
    }
    requestAnimationFrame(this._frame);
  }
}
