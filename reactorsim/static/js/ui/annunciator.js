// Meldetafel und Ereignisprotokoll.
//
// Die Kacheln werden einmal gebaut, danach wird nur data-st gesetzt -- Farbe,
// Blinken und Hupe entstehen daraus in CSS.

import { el, setAttr, setText } from './dom.js';
import { t, clock } from './i18n.js';
import { playClip, MusicLoop } from './music.js';

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
 * Anlagengeräusche über feste Aufnahmen (static/audio/*.mp3, siehe music.js).
 * Bis Version 0.0.47 synthetisiert über die Web Audio API -- jetzt echte
 * Klangeffekte, weil ein Spieler welche gefunden hat, die besser klingen.
 */
export class Horn {
  constructor() {
    this._enabled = true;
    // Sirene läuft als Dauerschleife, solange eine Meldung unquittiert ist
    // (siehe alarm()/silence() unten) -- ein einzelner Clip würde sich bei
    // jedem Taktschlag der blinkenden Kachel selbst überlagern.
    this._siren = new MusicLoop('alarm_sirene.mp3', 0.35);
  }

  // main.js weist `app.horn.enabled = ...` direkt zu (Stats-Dialog) -- der
  // Setter muss deshalb die laufende Sirene mit abstellen, nicht nur das
  // Flag umlegen, sonst spielt sie nach dem Abschalten einfach weiter.
  get enabled() { return this._enabled; }
  set enabled(v) {
    this._enabled = v;
    this._siren.setEnabled(v);
  }

  /**
   * Meldehupe. Wird im Takt der blinkenden Kachel gerufen (siehe panels.js);
   * start() ist idempotent, läuft also einfach weiter, statt neu anzusetzen.
   * TRIP-Meldungen (severity >= 3) bekommen eine dringlichere, leicht
   * höhere Stimme -- ohne zweite Datei über die Wiedergabegeschwindigkeit.
   */
  alarm(severity = 2) {
    if (!this.enabled) return;
    this._siren.audio.playbackRate = severity >= 3 ? 1.15 : 1.0;
    this._siren.start();
  }

  /** Sirene abstellen, sobald keine Meldung mehr unquittiert ist. */
  silence() {
    this._siren.stop();
  }

  /** Schnellabschaltung -- einmaliger Clip, kein Loop. */
  scram() {
    if (this.enabled) playClip('game_scram.mp3');
  }

  /** Kernzerstörung -- einmaliger Clip, kein Loop. */
  meltdown() {
    if (this.enabled) playClip('game_over.mp3');
  }

  /** Muss aus einer Benutzergeste heraus laufen, sonst bleibt der Ton stumm. */
  unlock() {
    this._siren.audio.play().then(() => this._siren.stop()).catch(() => {});
  }
}
