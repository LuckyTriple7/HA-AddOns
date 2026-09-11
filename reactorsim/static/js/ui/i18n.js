// Übersetzungen und Zahlenformate.
//
// Die Tabelle kommt als Ganzes aus dem Template (window.RS_I18N). Fehlt ein
// Schlüssel, steht der Schlüsselname da -- sichtbar, aber nicht kaputt.

const TABLE = (typeof window !== 'undefined' && window.RS_I18N) || {};
export const LANG = (typeof window !== 'undefined' && window.RS_CFG && window.RS_CFG.lang) || 'en';

/** t('key') oder t('key', {n: 3}) für Platzhalter der Form {n}. */
export function t(key, vars) {
  let s = TABLE[key];
  if (s === undefined) return key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) s = s.split('{' + k + '}').join(String(v));
  }
  return s;
}

const _fmt = new Map();

/** Zahl mit fester Nachkommastelle in der Sprache des Spielers. */
export function num(value, digits = 1) {
  if (!Number.isFinite(value)) return '—';
  let f = _fmt.get(digits);
  if (!f) {
    f = new Intl.NumberFormat(LANG, { minimumFractionDigits: digits, maximumFractionDigits: digits });
    _fmt.set(digits, f);
  }
  return f.format(value);
}

/** Zahl plus Einheit; die Einheit bekommt eine eigene, kleinere Auszeichnung. */
export function val(node, value, digits, unitKey) {
  const text = num(value, digits);
  if (!unitKey) return text;
  return text + ' ' + t(unitKey);
}

/** Sekunden als hh:mm:ss -- die Betriebszeit läuft über viele Stunden. */
export function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const p = (n) => String(n).padStart(2, '0');
  return `${p(h)}:${p(m)}:${p(r)}`;
}
