// Verzeichnis der Reaktortypen.
//
// Ein Typ ist ein Datenobjekt plus ein Hook-Modul -- mehr braucht die Engine
// nicht. Kommt ein Typ dazu, steht er hier und sonst nirgends im Rechenpfad.

import * as pwr from './pwr.js';

export const PLANTS = {
  pwr,
};

export const PLANT_IDS = Object.keys(PLANTS);

export function getPlant(id) {
  return PLANTS[id] || null;
}

/** Ist der Typ schon gebaut? Die Oberfläche zeigt die anderen als Vorschau. */
export function isAvailable(id) {
  return Object.prototype.hasOwnProperty.call(PLANTS, id);
}
