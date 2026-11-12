// Schuetzt das 'ready'-Ereignis vor kleinen Aenderungen in WhatsApp Web.
// Nach dem Login meldet whatsapp-web.js in Client.js (inject) gut ein Dutzend
// Listener an WhatsApps interne Sammlungen an (Msg.on, Chat.on, AppState.on,
// Conn.on). Wirft einer davon, weil WhatsApp ein Modul umgebaut hat, bricht der
// ganze Block ab und 'ready' wird nie gemeldet (Add-on haengt bei
// "authenticated"). Der Fork lindionez/whatsapp-web.js packt deshalb jede
// Anmeldung einzeln in try/catch ("Prevents silent errors from preventing the
// Ready event from being fired"); das offizielle Paket (1.34.8) tut das nicht.
// Dieser Patch baut dasselbe nach. Ein fehlender Listener kostet dann nur das
// eine Ereignis, nicht die ganze Verbindung.
const fs = require('fs');
const path = require('path');

const MARK = '/* ha-patch: ready-listeners */';
const file = path.join(__dirname, '..', 'node_modules', 'whatsapp-web.js', 'src', 'Client.js');
let src = fs.readFileSync(file, 'utf8');

if (src.includes(MARK)) {
  console.log('[patch] wwebjs-ready-listeners: bereits vorhanden');
  process.exit(0);
}

// Bereich: der pupPage.evaluate-Block, der die Listener anmeldet
const startAnchor = "const { Msg, Chat } = window.require('WAWebCollections');";
const endAnchor = 'window.WWebJS.injectToFunction(';
const start = src.indexOf(startAnchor);
const end = start < 0 ? -1 : src.indexOf(endAnchor, start);
if (start < 0 || end < 0) {
  console.error('[patch] wwebjs-ready-listeners: Ankerstelle nicht gefunden — whatsapp-web.js hat sich geaendert');
  process.exit(1);
}

// Ende einer Anweisung ab pos: bis zum ';' auf Klammertiefe 0.
// Strings, Template-Literale und Kommentare werden uebersprungen.
function statementEnd(text, pos) {
  let depth = 0;
  for (let i = pos; i < text.length; i++) {
    const c = text[i];
    if (c === "'" || c === '"' || c === '`') {
      for (i++; i < text.length && text[i] !== c; i++) if (text[i] === '\\') i++;
    } else if (c === '/' && text[i + 1] === '/') {
      i = text.indexOf('\n', i);
      if (i < 0) return -1;
    } else if (c === '/' && text[i + 1] === '*') {
      i = text.indexOf('*/', i + 2) + 1;
      if (i <= 0) return -1;
    } else if (c === '(' || c === '{' || c === '[') {
      depth++;
    } else if (c === ')' || c === '}' || c === ']') {
      depth--;
      if (depth < 0) return -1;
    } else if (c === ';' && depth === 0) {
      return i + 1;
    }
  }
  return -1;
}

let region = src.slice(start, end);
// Anweisungen am Zeilenanfang: Msg.on( / Chat.on( / AppState.on( sowie
// window.require('WAWebConnModel').Conn.on( (ueber mehrere Zeilen umbrochen)
const re = /\n([ \t]*)((?:Msg|Chat|AppState)\.on\(|window\s*\.require\('WAWebConnModel'\)\s*\.Conn\.on\()/g;
const hits = [];
let m;
while ((m = re.exec(region))) {
  const stmtStart = m.index + 1 + m[1].length;
  const stmtEnd = statementEnd(region, stmtStart);
  if (stmtEnd < 0) {
    console.error('[patch] wwebjs-ready-listeners: Anweisungsende nicht gefunden — nicht angewendet');
    process.exit(1);
  }
  hits.push([stmtStart, stmtEnd]);
  re.lastIndex = stmtEnd;
}
if (hits.length === 0) {
  console.error('[patch] wwebjs-ready-listeners: keine Listener gefunden — whatsapp-web.js hat sich geaendert');
  process.exit(1);
}

// Von hinten nach vorn einsetzen, damit die Positionen gueltig bleiben
for (const [a, b] of hits.reverse()) {
  region = region.slice(0, a) + 'try { ' + region.slice(a, b) + " } catch (e) { console.warn('[wwebjs] Listener-Anmeldung fehlgeschlagen:', e && e.message); }" + region.slice(b);
}
src = src.slice(0, start) + MARK + ' ' + region + src.slice(end);
fs.writeFileSync(file, src);
console.log(`[patch] wwebjs-ready-listeners: ${hits.length} Listener abgesichert`);
