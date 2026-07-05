// Reiner Node-Test ohne Dependency (kein npm/jest im Projekt) fuer die
// bedingte Folge-Schritt-Logik (`showIf`/`advVisibleSteps`) des
// Reiseberater-Wizards. Extrahiert `ADV_STEPS` + `advVisibleSteps` per
// vm-Modul direkt aus templates/index.html (gleiche Extraktions-Idee wie
// der bestehende Python-Syntax-Check fuer den <script>-Block), damit der
// Test nie von der HTML-Datei abweicht.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, '..', 'templates', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

function extractBlock(startMarker, endMarker) {
  const start = html.indexOf(startMarker);
  if (start === -1) throw new Error('Start-Marker nicht gefunden: ' + startMarker);
  const end = html.indexOf(endMarker, start);
  if (end === -1) throw new Error('End-Marker nicht gefunden: ' + endMarker);
  return html.slice(start, end + endMarker.length);
}

const stepsSrc = extractBlock('const ADV_STEPS = [', '\n    ];');
const fnSrc = extractBlock('function advVisibleSteps(){', '}');

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(stepsSrc, sandbox);
vm.runInContext('var advState = {};', sandbox);
vm.runInContext(fnSrc, sandbox);

function setState(state) {
  vm.runInContext('advState = ' + JSON.stringify(state) + ';', sandbox);
}
function visibleKeys() {
  return vm.runInContext('advVisibleSteps().map(s => s.key)', sandbox);
}
function stepCount() {
  return vm.runInContext('ADV_STEPS.length', sandbox);
}
function conditionalCount() {
  return vm.runInContext('ADV_STEPS.filter(s => s.showIf).length', sandbox);
}

let failures = 0;
function check(name, actual, expected) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) {
    failures++;
    console.error(`FAIL ${name}: erwartet ${e}, bekommen ${a}`);
  } else {
    console.log(`ok   ${name}`);
  }
}

// Kein Interesse gesetzt -> beide bedingten Schritte (Strand/Berge-Details) versteckt
setState({});
check('leerer Status: beach_detail versteckt', visibleKeys().includes('beach_detail'), false);
check('leerer Status: berge_detail versteckt', visibleKeys().includes('berge_detail'), false);
check('leerer Status: sichtbare Anzahl = Gesamt - bedingte Schritte',
  visibleKeys().length, stepCount() - conditionalCount());

// Nur Strand gewaehlt -> nur beach_detail sichtbar
setState({ interests: ['🌴 Strand'] });
check('Strand gewaehlt: beach_detail sichtbar', visibleKeys().includes('beach_detail'), true);
check('Strand gewaehlt: berge_detail weiterhin versteckt', visibleKeys().includes('berge_detail'), false);

// Nur Berge gewaehlt -> nur berge_detail sichtbar
setState({ interests: ['⛰️ Berge'] });
check('Berge gewaehlt: berge_detail sichtbar', visibleKeys().includes('berge_detail'), true);
check('Berge gewaehlt: beach_detail weiterhin versteckt', visibleKeys().includes('beach_detail'), false);

// Beides gewaehlt -> beide sichtbar, keine Duplikate/Fehler
setState({ interests: ['🌴 Strand', '⛰️ Berge'] });
check('Beide gewaehlt: beach_detail sichtbar', visibleKeys().includes('beach_detail'), true);
check('Beide gewaehlt: berge_detail sichtbar', visibleKeys().includes('berge_detail'), true);
check('Beide gewaehlt: sichtbare Anzahl = Gesamt (kein Schritt versteckt)',
  visibleKeys().length, stepCount());

// Kein interests-Key im Status (undefined statt leerem Array) darf nicht crashen
setState({ region: 'Europa' });
check('interests fehlt: kein Crash, beach_detail versteckt', visibleKeys().includes('beach_detail'), false);

if (failures > 0) {
  console.error(`\n${failures} Test(s) fehlgeschlagen.`);
  process.exit(1);
}
console.log('\nAlle Wizard-Engine-Tests bestanden.');
