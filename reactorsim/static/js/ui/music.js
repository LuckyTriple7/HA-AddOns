// Musik & aufgenommene Klangeffekte.
//
// Anders als Horn (annunciator.js) und Geiger (geiger.js) -- die Klaenge dort
// synthetisiert der Browser selbst per WebAudio-Oszillatoren -- sind das hier
// echte Aufnahmen (static/audio/*.mp3, Pixabay-Lizenz, siehe LICENSE.md).
// Einfaches <audio>-Element statt AudioContext/decodeAudioData: fuer feste
// Dateien reicht das, und Lautstaerke/Loop/Pause kommen dann geschenkt.
//
// Wie bei Horn/Geiger gilt: der erste play()-Aufruf muss aus einer echten
// Nutzergeste kommen, sonst verweigert der Browser jeden Ton.

const BASE = (window.RS_CFG ? `/s/${window.RS_CFG.version}` : '') + '/audio/';

/**
 * Einmaliger Clip, feuert und vergisst -- fuer SCRAM, Kernschmelze und die
 * Geigerzaehler-Vorwarnung. Eigenes Audio-Objekt je Aufruf: zwei schnell
 * hintereinander kommende Klaenge sollen sich nicht gegenseitig abschneiden.
 */
export function playClip(name, volume = 1) {
  try {
    const a = new Audio(BASE + name);
    a.volume = volume;
    a.play().catch(() => { /* kein Autoplay-Recht -- naechstes Mal vielleicht */ });
  } catch { /* kein Audio in dieser Umgebung, kein Absturz deshalb */ }
}

/**
 * Eine Dauerschleife -- Intro- oder Hintergrundmusik, oder (bei der Hupe)
 * die Sirene, die laeuft, solange eine Meldung unquittiert ist. start() ist
 * idempotent: erneuter Aufruf waehrend sie schon laeuft, tut nichts.
 */
export class MusicLoop {
  constructor(name, volume = 0.5) {
    this.audio = new Audio(BASE + name);
    this.audio.loop = true;
    this.audio.volume = volume;
    this.enabled = true;
  }

  start() {
    if (!this.enabled || !this.audio.paused) return;
    this.audio.play().catch(() => {
      // Browser verweigert Autoplay ohne Geste -- beim naechsten Klick
      // irgendwo auf der Seite einmalig nachholen.
      const retry = () => { this.audio.play().catch(() => {}); };
      document.addEventListener('click', retry, { once: true });
    });
  }

  stop() {
    this.audio.pause();
    this.audio.currentTime = 0;
  }

  setEnabled(v) {
    this.enabled = v;
    if (!v) this.stop();
  }
}
