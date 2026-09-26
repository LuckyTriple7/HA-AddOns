// Behebt "Data passed to getter must include an id property (it's how we
// memoize) but got undefined" beim Senden von Bildern/Dateien.
// Seit den WhatsApp-Web-Builds vom 17.09.2026 traegt MediaData ein privates
// __x_id; beim Spread von mediaOptions in die ausgehende Nachricht ueberschreibt
// es die echte Msg-ID. Uebernommen aus wwebjs/whatsapp-web.js PR #201923.
// Faellt der Patch weg (Upstream hat ihn uebernommen), laeuft das Skript leer durch.
const fs = require('fs');
const path = require('path');

const file = path.join(__dirname, '..', 'node_modules', 'whatsapp-web.js', 'src', 'util', 'Injected', 'Utils.js');
let src = fs.readFileSync(file, 'utf8');

if (/delete message\.__x_id/.test(src)) {
  console.log('[patch] wwebjs-media-id: bereits vorhanden');
  process.exit(0);
}

const anchor = "// Bot's won't reply if canonicalUrl is set (linking)";
if (!src.includes(anchor)) {
  console.error('[patch] wwebjs-media-id: Ankerzeile nicht gefunden — whatsapp-web.js hat sich geaendert');
  process.exit(1);
}

src = src.replace(anchor, `if (message.__x_id) {
            delete message.__x_id;
        }

        ${anchor}`);
fs.writeFileSync(file, src);
console.log('[patch] wwebjs-media-id: angewendet');
