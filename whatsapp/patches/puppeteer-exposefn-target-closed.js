// Behebt den Haenger bei status "authenticated" (ready kommt nie).
// Nach dem Login meldet whatsapp-web.js ueber page.exposeFunction() rund 20
// Rueckruf-Funktionen an. Puppeteer traegt jede davon per Runtime.addBinding in
// ALLE Frames ein. Schliesst sich waehrenddessen ein Neben-Frame von WhatsApp
// Web, wirft das "Protocol error (Runtime.addBinding): Target closed", die
// Anmeldung der Listener bricht ab und 'ready' wird nie gemeldet.
// Der Patch ignoriert diesen Fehler fuer Neben-Frames, genau wie Puppeteer es
// beim Frame-Aufbau selbst schon tut (FrameManager.js, "might have been closed").
const fs = require('fs');
const path = require('path');

const file = path.join(__dirname, '..', 'node_modules', 'puppeteer-core', 'lib', 'cjs', 'puppeteer', 'cdp', 'FrameManager.js');
let src = fs.readFileSync(file, 'utf8');

if (src.includes('/* ha-patch: exposefn-target-closed */')) {
  console.log('[patch] puppeteer-exposefn-target-closed: bereits vorhanden');
  process.exit(0);
}

const anchor = `        await Promise.all(this.frames().map(async (frame) => {
            return await frame.addExposedFunctionBinding(binding);
        }));`;
if (!src.includes(anchor)) {
  console.error('[patch] puppeteer-exposefn-target-closed: Ankerstelle nicht gefunden — puppeteer-core hat sich geaendert');
  process.exit(1);
}

src = src.replace(anchor, `        /* ha-patch: exposefn-target-closed */
        await Promise.all(this.frames().map(async (frame) => {
            try {
                return await frame.addExposedFunctionBinding(binding);
            }
            catch (error) {
                if (frame !== this.mainFrame() &&
                    (0, ErrorLike_js_1.isErrorLike)(error) &&
                    (0, Connection_js_1.isTargetClosedError)(error)) {
                    return;
                }
                throw error;
            }
        }));`);
fs.writeFileSync(file, src);
console.log('[patch] puppeteer-exposefn-target-closed: angewendet');
