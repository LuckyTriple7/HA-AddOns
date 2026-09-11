// Winzige DOM-Helfer. Absichtlich kein Framework: die Leitwarte baut ihre
// Knoten einmal und schreibt danach nur noch Zahlen hinein.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/** el('div.rs-row', {title: 'x'}, [kind1, 'Text']) */
export function el(spec, attrs = null, children = null) {
  const [tag, ...classes] = String(spec).split('.');
  const node = document.createElement(tag || 'div');
  if (classes.length) node.className = classes.join(' ');
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'text') node.textContent = v;
      else if (k.startsWith('--')) node.style.setProperty(k, v);
      else node.setAttribute(k, v === true ? '' : String(v));
    }
  }
  if (children) {
    for (const c of [].concat(children)) {
      if (c === null || c === undefined) continue;
      node.append(typeof c === 'string' ? document.createTextNode(c) : c);
    }
  }
  return node;
}

/** SVG-Variante -- ohne createElementNS bleiben die Knoten stumm. */
export function svg(tag, attrs = null, children = null) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      node.setAttribute(k, String(v));
    }
  }
  if (children) for (const c of [].concat(children)) if (c) node.append(c);
  return node;
}

/** Schreibt nur, wenn sich der Text wirklich geändert hat. */
export function setText(node, text) {
  if (node && node.textContent !== text) node.textContent = text;
}

/** Dito für Attribute -- ein unveränderter Wert löst sonst Stilneuberechnung aus. */
export function setAttr(node, name, value) {
  if (!node) return;
  const v = String(value);
  if (node.getAttribute(name) !== v) node.setAttribute(name, v);
}

export function setVar(node, name, value) {
  if (node) node.style.setProperty(name, value);
}

export function clear(node) {
  while (node && node.firstChild) node.removeChild(node.firstChild);
}
