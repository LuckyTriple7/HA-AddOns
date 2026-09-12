// Katalog der Statuszeile: welche Werte oben in der Kopfzeile stehen koennen.
//
// Jeder Schluessel ist ein data-v-Bindungsname, wie ihn panels.js beim
// Renderlauf ueber document.querySelectorAll('[data-v]') fuellt -- die
// Statuszeile ist also nur eine weitere Ansicht auf dieselben Werte wie die
// Panels, keine eigene Datenquelle. labelKey zeigt auf denselben
// Uebersetzungsschluessel, den das jeweilige Panel fuer diesen Wert schon
// benutzt (status_* fuer die alten neun, sonst val_*) -- eine zweite
// Beschriftung fuer denselben Wert waere nur eine zweite Fehlerquelle.
//
// Nicht jeder Schluessel gilt fuer jeden Reaktortyp (z.B. orm nur RBMK,
// pzr_l nur DWR) -- irrelevante Werte zeigen einfach "—", genau wie in den
// Panels selbst. Die Auswahl bleibt trotzdem frei: wer einen Wert fuer einen
// Typ waehlt, bei dem er nicht existiert, sieht das sofort am Strich.

export const STATUS_STATS = [
  { key: 'power_th_pct', labelKey: 'status_power_th' },
  { key: 'power_e', labelKey: 'status_power_e' },
  { key: 'demand', labelKey: 'status_demand' },
  { key: 'rho_pcm', labelKey: 'val_reactivity' },
  { key: 'deviation', labelKey: 'val_deviation' },
  { key: 't_avg', labelKey: 'status_tavg' },
  { key: 't_hot', labelKey: 'val_t_hot' },
  { key: 't_cold', labelKey: 'val_t_cold' },
  { key: 't_fuel', labelKey: 'status_fuel' },
  { key: 't_clad', labelKey: 'val_clad_temp' },
  { key: 'p_prim', labelKey: 'status_pressure' },
  { key: 'pzr_p', labelKey: 'val_pzr_press' },
  { key: 'pzr_l', labelKey: 'val_pzr_level' },
  { key: 'w_core', labelKey: 'val_flow_core' },
  { key: 'n_pct', labelKey: 'val_power_neutronic' },
  { key: 'decay_pct', labelKey: 'val_power_decay' },
  { key: 'period', labelKey: 'status_period' },
  { key: 'freq', labelKey: 'val_frequency' },
  { key: 'clock', labelKey: 'status_clock' },
  { key: 'subcool', labelKey: 'val_subcooling' },
  { key: 'dnbr', labelKey: 'status_margin' },
  { key: 'p_sg', labelKey: 'val_sg_press' },
  { key: 'w_steam', labelKey: 'val_steam_flow' },
  { key: 'gov', labelKey: 'val_gov' },
  { key: 'p_cond', labelKey: 'val_cond_press' },
  { key: 'l_sg', labelKey: 'val_sg_level' },
  { key: 'w_fw', labelKey: 'val_feed_flow' },
  { key: 'breaker', labelKey: 'val_breaker' },
  { key: 'xenon', labelKey: 'val_xenon' },
  { key: 'iodine', labelKey: 'val_iodine' },
  { key: 'samarium', labelKey: 'val_samarium' },
  { key: 'boron', labelKey: 'val_boron' },
  { key: 'burnup', labelKey: 'val_burnup' },
  { key: 'sdm', labelKey: 'val_shutdown_margin' },
  { key: 'voidfrac', labelKey: 'val_void' },
  { key: 'recirc', labelKey: 'val_recirc' },
  { key: 'quality', labelKey: 'val_quality' },
  { key: 'decay_ratio', labelKey: 'val_decay_ratio' },
  { key: 'orm', labelKey: 'val_orm' },
  { key: 'void_coeff', labelKey: 'val_void_coeff' },
  { key: 'axial', labelKey: 'val_axial' },
  { key: 't_graphite', labelKey: 'val_graphite_temp' },
  { key: 'ic_water', labelKey: 'val_ic_water' },
  { key: 'cont_press', labelKey: 'val_cont_press' },
  { key: 'h2_mass', labelKey: 'val_h2_mass' },
];

export const STATUS_STATS_BY_KEY = new Map(STATUS_STATS.map((s) => [s.key, s]));

// Die klassische Zeile, wie sie vor dieser Einstellung fest verdrahtet war --
// Rueckfallwert fuer jeden Reaktortyp, der noch keine eigene Auswahl hat.
export const DEFAULT_STATUS_KEYS = [
  'power_th_pct', 'power_e', 'demand', 't_avg', 'p_prim', 't_fuel', 'dnbr', 'period', 'clock',
];

const MAX_STATUS_STATS = 16;

/** Eine gespeicherte Liste gegen den Katalog pruefen: nur bekannte Schluessel,
 *  keine Duplikate, sinnvoll begrenzt. Faellt sie leer aus, gilt der
 *  Standard -- ein Spieler soll die Zeile nie leerraeumen koennen. */
export function sanitizeStatusKeys(list) {
  if (!Array.isArray(list)) return DEFAULT_STATUS_KEYS;
  const seen = new Set();
  const out = [];
  for (const key of list) {
    if (typeof key !== 'string' || seen.has(key) || !STATUS_STATS_BY_KEY.has(key)) continue;
    seen.add(key);
    out.push(key);
    if (out.length >= MAX_STATUS_STATS) break;
  }
  return out.length ? out : DEFAULT_STATUS_KEYS;
}
