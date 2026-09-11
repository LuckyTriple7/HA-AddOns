// Anlagenfließbild.
//
// Das SVG wird einmal aus einer Beschreibung gebaut. Im Renderlauf werden
// ausschließlich CSS-Custom-Properties auf dem Wurzelknoten gesetzt und ein
// paar data-Attribute an Pumpen und Ventilen -- Farbe nach Temperatur,
// Fließgeschwindigkeit, Drehen der Pumpenräder macht CSS.
//
// Das ist der Grund, warum das Fließbild auf einem schwachen Handy nicht
// bremst: pro Takt sind es rund zehn Schreibvorgänge, nicht hunderte
// DOM-Zugriffe.

import { svg, setAttr, setVar, setText } from './dom.js';
import { t, num } from './i18n.js';

/** Temperatur auf 0..1 abbilden -- daraus mischt CSS die Rohrfarbe. */
const norm = (v, lo, hi) => Math.max(0, Math.min(1, (v - lo) / (hi - lo)));

/** Pumpensymbol: Kreis mit rotierendem Flügel. */
function pump(x, y, id, label) {
  const body = svg('circle', { class: 'rs-comp', cx: x, cy: y, r: 11, 'data-mimic': id });
  const vane = svg('path', {
    class: 'rs-spin',
    d: `M ${x - 7} ${y} L ${x + 7} ${y} M ${x} ${y - 7} L ${x} ${y + 7}`,
    stroke: '#7fa6c4', 'stroke-width': 1.6, fill: 'none',
  });
  return svg('g', null, [
    body, vane,
    svg('text', { class: 'rs-label', x, y: y + 22, 'text-anchor': 'middle' }, [label]),
  ]);
}

/** Ventilsymbol: zwei Dreiecke, Zustand über data-state. */
function valve(x, y, id, label, side = 'right') {
  return svg('g', null, [
    svg('path', {
      class: 'rs-comp', 'data-mimic': id,
      d: `M ${x - 9} ${y - 7} L ${x - 9} ${y + 7} L ${x} ${y} Z M ${x + 9} ${y - 7} L ${x + 9} ${y + 7} L ${x} ${y} Z`,
    }),
    // Beschriftung seitlich, nicht darueber: ueber dem Ventil laeuft die
    // Rohrleitung, und Text auf einer Leitung ist auf dem Handy unlesbar.
    svg('text', {
      class: 'rs-label',
      x: side === 'left' ? x - 14 : x + 14,
      y: y + 4,
      'text-anchor': side === 'left' ? 'end' : 'start',
    }, [label]),
  ]);
}

function pipe(d, kind, flowId) {
  const nodes = [svg('path', { class: `rs-pipe rs-pipe-${kind}`, d })];
  if (flowId) nodes.push(svg('path', { class: 'rs-flow', d, 'data-flow': flowId }));
  return svg('g', null, nodes);
}

function readout(x, y, id, anchor = 'start') {
  return svg('text', { class: 'rs-read', x, y, 'text-anchor': anchor, 'data-read': id }, ['—']);
}

/**
 * Fließbild eines Druckwasserreaktors.
 * Ein Strang stellvertretend für vier -- vier gezeichnete Schleifen wären auf
 * einem Handy im Hochformat nicht mehr lesbar, und sie zeigen ohnehin dasselbe.
 */
export function buildPwrMimic(container) {
  const root = svg('svg', {
    viewBox: '0 0 520 268',
    preserveAspectRatio: 'xMidYMid meet',
    role: 'img',
    'aria-label': t('panel_mimic'),
  });

  const g = [];

  // Rohrleitungen zuerst, damit die Bauteile darüber liegen.
  // Heißer Strang: Reaktor oben raus zum Dampferzeuger.
  g.push(pipe('M 92 92 L 92 62 L 224 62', 'hot', 'prim'));
  // Kalter Strang: Dampferzeuger unten zurück über die Pumpe in den Reaktor.
  g.push(pipe('M 224 168 L 172 168 L 172 208 L 92 208 L 92 188', 'cold', 'prim'));
  // Druckhalter am heißen Strang.
  g.push(pipe('M 150 62 L 150 40', 'hot', null));
  // Frischdampf zum Regelventil und zur Turbine.
  g.push(pipe('M 246 52 L 330 52 L 330 76', 'steam', 'steam'));
  g.push(pipe('M 330 100 L 330 118 L 372 118', 'steam', 'steam'));
  // Umleitstation zum Kondensator.
  g.push(pipe('M 300 52 L 300 214 L 372 214', 'steam', 'bypass'));
  // Abdampf zur Kondensation.
  g.push(pipe('M 432 140 L 452 140 L 452 196 L 432 196', 'steam', 'steam'));
  // Speisewasser zurück zum Dampferzeuger.
  g.push(pipe('M 372 232 L 268 232 L 268 168', 'feed', 'feed'));

  // Reaktordruckbehälter.
  g.push(svg('rect', { class: 'rs-vessel', x: 64, y: 92, width: 56, height: 96, rx: 22 }));
  g.push(svg('rect', { class: 'rs-core', x: 76, y: 112, width: 32, height: 56, rx: 4 }));
  g.push(svg('text', { class: 'rs-label', x: 92, y: 252, 'text-anchor': 'middle' },
    [t('mimic_core')]));
  g.push(readout(92, 106, 'power', 'middle'));

  // Druckhalter.
  g.push(svg('rect', { class: 'rs-vessel', x: 136, y: 8, width: 28, height: 34, rx: 12 }));
  g.push(svg('rect', { class: 'rs-pzr-level', x: 138, y: 10, width: 24, height: 30, rx: 10 }));
  g.push(svg('text', { class: 'rs-label', x: 180, y: 14, 'text-anchor': 'start' },
    [t('mimic_pzr')]));
  g.push(readout(170, 26, 'pzr'));

  // Hauptkühlmittelpumpe.
  g.push(pump(172, 208, 'rcp', t('mimic_rcp')));

  // Dampferzeuger.
  g.push(svg('rect', { class: 'rs-vessel', x: 218, y: 46, width: 56, height: 130, rx: 22 }));
  g.push(svg('text', { class: 'rs-label', x: 246, y: 192, 'text-anchor': 'middle' },
    [t('mimic_sg')]));
  g.push(readout(246, 120, 'sg', 'middle'));
  // Füllstandsbalken im Dampferzeuger.
  g.push(svg('rect', { class: 'rs-sg-level', x: 222, y: 60, width: 48, height: 112, rx: 16 }));

  // Regelventil und Umleitstation.
  g.push(valve(330, 88, 'gov', t('mimic_gov'), 'left'));
  g.push(valve(300, 140, 'bypass', t('mimic_bypass')));

  // Turbine und Generator.
  g.push(svg('path', { class: 'rs-vessel', d: 'M 372 100 L 432 84 L 432 156 L 372 136 Z' }));
  g.push(svg('circle', { class: 'rs-comp', cx: 452, cy: 118, r: 14, 'data-mimic': 'gen' }));
  g.push(svg('text', { class: 'rs-label', x: 452, y: 96, 'text-anchor': 'middle' },
    [t('mimic_gen')]));
  g.push(readout(452, 142, 'gen', 'middle'));

  // Kondensator.
  g.push(svg('rect', { class: 'rs-vessel', x: 372, y: 196, width: 60, height: 36, rx: 8 }));
  g.push(svg('text', { class: 'rs-label', x: 402, y: 248, 'text-anchor': 'middle' },
    [t('mimic_cond')]));
  g.push(readout(402, 218, 'cond', 'middle'));

  // Temperaturen an den Strängen.
  g.push(readout(100, 54, 'thot'));
  g.push(readout(100, 202, 'tcold'));

  for (const node of g) root.append(node);
  container.replaceChildren(root);

  const reads = new Map();
  for (const node of root.querySelectorAll('[data-read]')) reads.set(node.dataset.read, node);
  const comps = new Map();
  for (const node of root.querySelectorAll('[data-mimic]')) comps.set(node.dataset.mimic, node);
  const flows = new Map();
  for (const node of root.querySelectorAll('[data-flow]')) {
    const id = node.dataset.flow;
    const list = flows.get(id);
    if (list) list.push(node); else flows.set(id, [node]);
  }
  const sgLevel = root.querySelector('.rs-sg-level');
  const pzrLevel = root.querySelector('.rs-pzr-level');

  return {
    root,
    update(s, d, sp) {
      // Farben: kalt 250 °C, heiß 340 °C.
      setVar(root, '--rs-t-hot', norm(s.T_co - 273.15, 250, 340).toFixed(3));
      setVar(root, '--rs-t-cold', norm(s.T_ci - 273.15, 250, 340).toFixed(3));
      setVar(root, '--rs-n', Math.max(0, Math.min(1, s.n)).toFixed(3));
      setVar(root, '--rs-steam-l', norm(s.p_sg, 20, 80).toFixed(3));

      const fPrim = Math.max(0, Math.min(1.1, s.W_core / sp.coolant.W0));
      for (const n of flows.get('prim') || []) setVar(n, '--rs-w', fPrim.toFixed(3));
      const fSteam = Math.max(0, Math.min(1.2, s.W_steam / sp.sg.W_steam0));
      for (const n of flows.get('steam') || []) setVar(n, '--rs-w', fSteam.toFixed(3));
      for (const n of flows.get('feed') || []) {
        setVar(n, '--rs-w', Math.max(0, Math.min(1.2, s.W_fw / sp.sg.W_steam0)).toFixed(3));
      }
      for (const n of flows.get('bypass') || []) setVar(n, '--rs-w', (s.bypass || 0).toFixed(3));

      const rcp = comps.get('rcp');
      if (rcp) {
        const anyTripped = (d.pumpStates || []).some((x) => x === 'tripped');
        setAttr(rcp, 'data-state', fPrim > 0.2 ? 'run' : (anyTripped ? 'tripped' : 'stopped'));
        setVar(rcp.parentNode, '--rs-w', fPrim.toFixed(3));
      }
      setAttr(comps.get('gov'), 'data-state', s.gov > 0.02 ? 'run' : 'stopped');
      setAttr(comps.get('bypass'), 'data-state', s.bypass > 0.02 ? 'run' : 'stopped');
      setAttr(comps.get('gen'), 'data-state',
        s.turbineTripped ? 'tripped' : (s.breaker ? 'run' : 'stopped'));

      // Füllstände als Höhe des gefüllten Teils.
      if (sgLevel) {
        const h = Math.max(2, 112 * Math.max(0, Math.min(1, s.L_sg)));
        setAttr(sgLevel, 'y', String(60 + 112 - h));
        setAttr(sgLevel, 'height', String(h));
      }
      if (pzrLevel) {
        const h = Math.max(2, 30 * Math.max(0, Math.min(1, s.pzr_L)));
        setAttr(pzrLevel, 'y', String(10 + 30 - h));
        setAttr(pzrLevel, 'height', String(h));
      }

      setText(reads.get('power'), num(d.power_th_pct, 0) + ' %');
      setText(reads.get('thot'), num(s.T_co - 273.15, 1) + ' °C');
      setText(reads.get('tcold'), num(s.T_ci - 273.15, 1) + ' °C');
      setText(reads.get('pzr'), num(s.pzr_p, 1) + ' bar');
      setText(reads.get('sg'), num(s.p_sg, 1) + ' bar');
      setText(reads.get('gen'), num(s.P_e, 0) + ' MW');
      setText(reads.get('cond'), num(s.p_cond, 3) + ' bar');
    },
  };
}

export const MIMICS = {
  'mimic-pwr': buildPwrMimic,
};
