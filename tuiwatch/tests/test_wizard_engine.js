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

const daytripSrc = extractBlock("const DAYTRIP = '", "';");
const stepsSrc = extractBlock('const ADV_STEPS = [', '\n    ];');
const fnSrc = extractBlock('function advVisibleSteps(){', '}');

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(daytripSrc, sandbox);
vm.runInContext(stepsSrc, sandbox);
vm.runInContext('var advState = {};', sandbox);
vm.runInContext(fnSrc, sandbox);

const DAYTRIP = vm.runInContext('DAYTRIP', sandbox);

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

// Kein Interesse gesetzt, kein Tagesausflug -> beach_detail/berge_detail/home_location/
// max_distance/duration_daytrip versteckt (5), Flugzeit/Abflughafen weiterhin sichtbar
setState({});
check('leerer Status: beach_detail versteckt', visibleKeys().includes('beach_detail'), false);
check('leerer Status: berge_detail versteckt', visibleKeys().includes('berge_detail'), false);
check('leerer Status: duration_daytrip versteckt', visibleKeys().includes('duration_daytrip'), false);
check('leerer Status: duration sichtbar', visibleKeys().includes('duration'), true);
check('leerer Status: sichtbare Anzahl = Gesamt - 5 versteckte bedingte Schritte',
  visibleKeys().length, stepCount() - 5);
check('leerer Status: genau 19 bedingte Schritte insgesamt definiert', conditionalCount(), 19);

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

// Kein interests-Key im Status (undefined statt leerem Array) darf nicht crashen
setState({ region: 'Europa' });
check('interests fehlt: kein Crash, beach_detail versteckt', visibleKeys().includes('beach_detail'), false);

// Anreise: ohne arrival_mode oder mit Flugzeug/Ist mir egal -> Flugzeit/Abflughafen
// sichtbar, Startort/Entfernung versteckt
for (const mode of [undefined, 'Flugzeug', 'Ist mir egal']) {
  setState(mode === undefined ? {} : { arrival_mode: mode });
  check(`Anreise ${mode}: flight_time sichtbar`, visibleKeys().includes('flight_time'), true);
  check(`Anreise ${mode}: airports sichtbar`, visibleKeys().includes('airports'), true);
  check(`Anreise ${mode}: home_location versteckt`, visibleKeys().includes('home_location'), false);
  check(`Anreise ${mode}: max_distance versteckt`, visibleKeys().includes('max_distance'), false);
}

// Anreise: Auto/Bus/Bahn -> Startort/Entfernung sichtbar, Flugzeit/Abflughafen versteckt
for (const mode of ['Auto', 'Bus', 'Bahn']) {
  setState({ arrival_mode: mode });
  check(`Anreise ${mode}: home_location sichtbar`, visibleKeys().includes('home_location'), true);
  check(`Anreise ${mode}: max_distance sichtbar`, visibleKeys().includes('max_distance'), true);
  check(`Anreise ${mode}: flight_time versteckt`, visibleKeys().includes('flight_time'), false);
  check(`Anreise ${mode}: airports versteckt`, visibleKeys().includes('airports'), false);
}

// Tagesausflug gewaehlt -> Laender/Reiseart/Mitreisende/Budget/Unterkunft/Anreise/
// Flug/Freitext versteckt, dafuer Startort/Entfernung/Zeit-Frage sichtbar
setState({ region: DAYTRIP });
const hiddenForDaytrip = ['excluded_countries', 'excluded_countries_other', 'travel_type',
  'companions', 'budget', 'duration', 'accommodation', 'accommodation_size', 'hotel_wishes',
  'arrival_mode', 'flight_time', 'airports', 'perfect_holiday', 'past_trips'];
for (const key of hiddenForDaytrip) {
  check(`Tagesausflug: ${key} versteckt`, visibleKeys().includes(key), false);
}
const shownForDaytrip = ['region', 'interests', 'duration_daytrip', 'home_location',
  'max_distance', 'month', 'temp', 'sea', 'rain', 'activities', 'dislikes'];
for (const key of shownForDaytrip) {
  check(`Tagesausflug: ${key} sichtbar`, visibleKeys().includes(key), true);
}

// Normaler Urlaubsmodus bleibt von der Tagesausflug-Erweiterung unberuehrt (Regression)
setState({ region: 'Europa' });
check('Urlaubsmodus: duration sichtbar', visibleKeys().includes('duration'), true);
check('Urlaubsmodus: duration_daytrip versteckt', visibleKeys().includes('duration_daytrip'), false);
check('Urlaubsmodus: home_location versteckt (kein arrival_mode)',
  visibleKeys().includes('home_location'), false);
check('Urlaubsmodus: travel_type sichtbar', visibleKeys().includes('travel_type'), true);

if (failures > 0) {
  console.error(`\n${failures} Test(s) fehlgeschlagen.`);
  process.exit(1);
}
console.log('\nAlle Wizard-Engine-Tests bestanden.');
