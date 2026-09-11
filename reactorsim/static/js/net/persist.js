// Spielstände und Bestenliste aus Sicht des Browsers.
//
// Der Server behandelt den Spielstand als undurchsichtigen Block. Geprüft wird
// er deshalb HIER, beim Laden: ein kaputter oder fremder Stand darf nicht in
// die Engine, sonst rechnet sie mit NaN weiter und der Spieler sieht Striche
// statt Zahlen, ohne zu wissen warum.

import { api } from './api.js';
import { numbers } from '../sim/state.js';

const SAVE_VERSION = 1;

/** Zustand in einen Block packen, den der Server nur weiterreicht. */
export function pack(engine, scenarioId) {
  const s = engine.state;
  const out = {};
  // Nur Zahlen und einfache Felder -- Regler und Pumpen haben eigenes
  // Gedaechtnis, das beim Laden aus dem Zustand neu eingeschwungen wird.
  for (const [k, v] of Object.entries(s)) {
    if (typeof v === 'number' && Number.isFinite(v)) out[k] = v;
    else if (v instanceof Float64Array) out[k] = Array.from(v);
    else if (typeof v === 'boolean') out[k] = v;
  }
  out.scram = { ...s.scram };
  return {
    v: SAVE_VERSION,
    reactor: s.reactor,
    scenario: scenarioId || null,
    t_sim: s.t_sim,
    state: out,
  };
}

/**
 * Block prüfen und anwenden.
 * @returns {string|null} Fehlergrund, oder null bei Erfolg
 */
export function apply(blob, engine) {
  if (!blob || blob.v !== SAVE_VERSION) return 'version';
  if (blob.reactor !== engine.state.reactor) return 'reactor';
  const src = blob.state;
  if (!src || typeof src !== 'object') return 'shape';

  // Erst vollständig prüfen, dann erst schreiben. Ein halb angewandter
  // Spielstand wäre schlimmer als gar keiner.
  for (const [k, v] of Object.entries(src)) {
    if (Array.isArray(v)) {
      if (v.some((x) => typeof x !== 'number' || !Number.isFinite(x))) return `array:${k}`;
    } else if (typeof v === 'number') {
      if (!Number.isFinite(v)) return `number:${k}`;
    }
  }

  const s = engine.state;
  for (const [k, v] of Object.entries(src)) {
    const cur = s[k];
    if (cur instanceof Float64Array && Array.isArray(v) && v.length === cur.length) {
      cur.set(v);
    } else if (typeof cur === 'number' && typeof v === 'number') {
      s[k] = v;
    } else if (typeof cur === 'boolean' && typeof v === 'boolean') {
      s[k] = v;
    }
  }
  if (src.scram && typeof src.scram === 'object') {
    s.scram = { active: !!src.scram.active, t: Number(src.scram.t) || 0, cause: src.scram.cause || null };
  }
  // Zum Schluss: der Zustand muss die Grenzwächter überstehen.
  if (numbers(s).some((x) => !Number.isFinite(x))) return 'not_finite';
  return null;
}

export async function save(engine, scenarioId, slot = 'auto') {
  const r = await api.writeSave(slot, pack(engine, scenarioId));
  return r.ok;
}

export async function load(engine, slot = 'auto') {
  const r = await api.readSave(slot);
  if (!r.ok || !r.data) return 'not_found';
  return apply(r.data, engine);
}

export { api };
