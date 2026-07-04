// Dev-Tool, nicht Teil des Laufzeit-Images: prüft den in server.js eingebetteten
// Frontend-<script>-Block auf echte Syntaxfehler. `node --check server.js` allein
// sieht den Inhalt des Template-Strings nicht (ist für Node nur ein String) — hier
// wird der äußere Template-Literal tatsächlich durch V8 ausgewertet (inkl. dessen
// Escaping, z.B. \' wird von der äußeren Ebene verschluckt), erst danach wird der
// resultierende <script>-Inhalt separat mit `node --check` geprüft.
// Aufruf: node whatsapp/check-frontend-syntax.js
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');

const serverPath = process.argv[2] || path.join(__dirname, 'server.js');
const src = fs.readFileSync(serverPath, 'utf8');

const startMarker = "res.send(`<!DOCTYPE html>";
const startIdx = src.indexOf(startMarker);
if (startIdx < 0) { console.error('start marker not found'); process.exit(1); }
const bodyStart = startIdx + "res.send(".length + 1;
const endMarker = "</html>`);";
const endIdx = src.indexOf(endMarker, bodyStart);
if (endIdx < 0) { console.error('end marker not found'); process.exit(1); }
const body = src.slice(bodyStart, endIdx);

// Stub für jede server-seitige Interpolation, die im Template verwendet wird.
const DARK_MODE = true;
const DOWNLOAD_MEDIA = true;
const VIDEO_MAX_MB = 64;
const svgKeys = ['moon','sun','disk','imageOn','imageOff','trash','chevUp','chevDown','chevLeft','download','x','smile','paperclip','pin','doc'];
const _SVG = Object.fromEntries(svgKeys.map(k => [k, '<svg-' + k + '/>']));

let html;
try {
  const fn = new Function('DARK_MODE', 'DOWNLOAD_MEDIA', 'VIDEO_MAX_MB', '_SVG', 'return `' + body + '`;');
  html = fn(DARK_MODE, DOWNLOAD_MEDIA, VIDEO_MAX_MB, _SVG);
} catch (e) {
  console.error('FEHLER beim Auswerten des äußeren Template-Literals:', e.message);
  process.exit(1);
}

const scriptRe = /<script>([\s\S]*?)<\/script>/g;
let m, idx = 0, anyFail = false;
while ((m = scriptRe.exec(html))) {
  idx++;
  const code = m[1];
  const tmpFile = path.join(os.tmpdir(), `_wa_frontend_script_${idx}.js`);
  fs.writeFileSync(tmpFile, code);
  try {
    execFileSync(process.execPath, ['--check', tmpFile], { stdio: 'pipe' });
    console.log(`script #${idx}: OK (${code.length} Zeichen)`);
  } catch (e) {
    anyFail = true;
    console.log(`script #${idx}: SYNTAXFEHLER`);
    console.log(e.stderr.toString());
    const errMatch = e.stderr.toString().match(/_wa_frontend_script_\d+\.js:(\d+)/);
    if (errMatch) {
      const lineNo = parseInt(errMatch[1], 10);
      const lines = code.split('\n');
      const from = Math.max(0, lineNo - 4), to = Math.min(lines.length, lineNo + 3);
      for (let i = from; i < to; i++) {
        console.log((i + 1 === lineNo ? '>> ' : '   ') + (i + 1) + ': ' + lines[i]);
      }
    }
  } finally {
    try { fs.unlinkSync(tmpFile); } catch(e) {}
  }
}
process.exit(anyFail ? 1 : 0);
