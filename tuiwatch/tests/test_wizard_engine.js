// Reiner Node-Test ohne Dependency (kein npm/jest im Projekt) fuer die
// bedingte Folge-Schritt-Logik des TripPilot-Wizards. Seit 0.89.12 stehen die
// Fragen in trippilot_questions.json statt in static/app.js; der Test laedt
// deshalb die ausgelieferte JSON und den Bedingungs-Auswerter `advCondMet` +
// `advVisibleSteps` per vm-Modul direkt aus static/app.js — so bleibt er
// synchron zu beidem.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const jsPath = path.join(__dirname, '..', 'static', 'app.js');
const js = fs.readFileSync(jsPath, 'utf8');
const questionsPath = path.join(__dirname, '..', 'trippilot_questions.json');
const questions = JSON.parse(fs.readFileSync(questionsPath, 'utf8'));

function extractBlock(startMarker, endMarker) {
  const start = js.indexOf(startMarker);
  if (start === -1) throw new Error('Start-Marker nicht gefunden: ' + startMarker);
  const end = js.indexOf(endMarker, start);
  if (end === -1) throw new Error('End-Marker nicht gefunden: ' + endMarker);
  return js.slice(start, end + endMarker.length);
}

const condSrc = extractBlock('function advCondMet(cond, state){', '\n    }');
const fnSrc = extractBlock('function advVisibleSteps(){', '}');

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(condSrc, sandbox);
vm.runInContext('var advState = {};', sandbox);
vm.runInContext('var ADV_STEPS = ' + JSON.stringify(questions.steps) + ';', sandbox);
vm.runInContext(fnSrc, sandbox);

const DAYTRIP = questions.daytrip_value;

function setState(state) {
  vm.runInContext('advState = ' + JSON.stringify(state) + ';', sandbox);
}
function visibleKeys() {
  return vm.runInContext('advVisibleSteps().map(s => s.key)', sandbox);
}
function stepCount() {
  return questions.steps.length;
}
function conditionalCount() {
  return questions.steps.filter(s => s.show_if).length;
}
function step(key) {
  return questions.steps.find(s => s.key === key);
}

// Antwortwerte NIE im Test abtippen: sie stehen in der JSON und aendern sich
// dort (Emoji-Praefixe, Umformulierungen). Der Test holt sie ueber einen
// eindeutigen Teilstring — mehrdeutig/unbekannt bricht sofort ab.
function opt(key, needle) {
  const hits = (step(key).options || []).filter(o => o.includes(needle));
  if (hits.length !== 1) {
    throw new Error(`${key}: "${needle}" -> ${hits.length} Treffer: ${JSON.stringify(hits)}`);
  }
  return hits[0];
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

// ── Schema der ausgelieferten Datei ───────────────────────────────────────────
check('daytrip_value gesetzt', typeof DAYTRIP === 'string' && DAYTRIP.length > 0, true);
check('daytrip_value ist eine Option der region-Frage',
  step('region').options.includes(DAYTRIP), true);
check('jede Frage hat key/title/label/type', questions.steps.every(
  s => s.key && s.title && s.label && ['multi', 'single', 'text'].includes(s.type)), true);
check('keine doppelten Keys',
  new Set(questions.steps.map(s => s.key)).size, stepCount());
check('multi/single haben Optionen', questions.steps.every(
  s => s.type === 'text' || (Array.isArray(s.options) && s.options.length > 0)), true);
check('show_if verweist nur auf existierende Keys', (() => {
  const keys = new Set(questions.steps.map(s => s.key));
  const walk = c => {
    if (Array.isArray(c.all)) return c.all.every(walk);
    if (Array.isArray(c.any)) return c.any.every(walk);
    if (c.not) return walk(c.not);
    return keys.has(c.key);
  };
  return questions.steps.filter(s => s.show_if).every(s => walk(s.show_if));
})(), true);

// ── Auswerter: jeder Operator einzeln ─────────────────────────────────────────
function cond(c, state) {
  vm.runInContext('advState = ' + JSON.stringify(state) + ';', sandbox);
  return vm.runInContext('advCondMet(' + JSON.stringify(c) + ', advState)', sandbox);
}
check('contains trifft auf Listenantwort',
  cond({ key: 'a', contains: 'x' }, { a: ['x', 'y'] }), true);
check('contains trifft auf Einzelantwort',
  cond({ key: 'a', contains: 'x' }, { a: 'x' }), true);
check('contains trifft nicht bei fehlender Antwort',
  cond({ key: 'a', contains: 'x' }, {}), false);
check('contains_any trifft bei einem Treffer',
  cond({ key: 'a', contains_any: ['x', 'z'] }, { a: ['y', 'z'] }), true);
check('contains_any trifft nicht ohne Treffer',
  cond({ key: 'a', contains_any: ['x', 'z'] }, { a: ['y'] }), false);
check('equals trifft exakt', cond({ key: 'a', equals: 'x' }, { a: 'x' }), true);
check('equals trifft nicht auf Liste', cond({ key: 'a', equals: 'x' }, { a: ['x'] }), false);
check('in trifft', cond({ key: 'a', in: ['x', 'y'] }, { a: 'y' }), true);
check('in trifft nicht', cond({ key: 'a', in: ['x', 'y'] }, { a: 'z' }), false);
check('answered:true bei Antwort', cond({ key: 'a', answered: true }, { a: ['x'] }), true);
check('answered:true bei leerer Liste', cond({ key: 'a', answered: true }, { a: [] }), false);
check('answered:true bei leerem Text', cond({ key: 'a', answered: true }, { a: '' }), false);
check('answered:false ohne Antwort', cond({ key: 'a', answered: false }, {}), true);
check('all verlangt alle', cond({ all: [{ key: 'a', contains: 'x' },
  { key: 'b', contains: 'y' }] }, { a: ['x'] }), false);
check('any reicht eine', cond({ any: [{ key: 'a', contains: 'x' },
  { key: 'b', contains: 'y' }] }, { a: ['x'] }), true);
check('not kehrt um', cond({ not: { key: 'a', contains: 'x' } }, { a: ['x'] }), false);
check('unbekannter Operator gilt als nicht erfuellt',
  cond({ key: 'a', bogus: 'x' }, { a: ['x'] }), false);
check('fehlendes show_if bedeutet immer sichtbar', cond(undefined, {}), true);

// ── Sichtbarkeitslogik der ausgelieferten Fragen ──────────────────────────────
// Antwortwerte kommen aus der Datei, nie aus dem Testcode — sonst bricht der
// Test bei jeder Umbenennung/Emoji-Aenderung, ohne dass wirklich etwas kaputt ist.
const WELTWEIT = opt('region', 'Weltweit');
const REGION_EGAL = opt('region', 'Keine Präferenz');
const EUROPA = opt('region', 'Europa');
const BALEAREN = opt('region', 'Balearen');
const ITALIEN = opt('region', 'Italien');
const KEIN_GEWAESSER = opt('water_type', 'Kein Gewässer');
const MEER = opt('water_type', 'Meer');
const SEE = opt('water_type', 'See');
const HOTEL = opt('accommodation', 'Hotel');
const STRAND = opt('interests', 'Strand');
const BERGE = opt('interests', 'Berge');
const FLUGZEUG = opt('arrival_mode', 'Flugzeug');
const ARRIVAL_EGAL = opt('arrival_mode', 'Keine Präferenz');
const AUTO = opt('arrival_mode', 'Auto');
const BUS = opt('arrival_mode', 'Bus');
const BAHN = opt('arrival_mode', 'Bahn');

// Ohne jede Antwort sind genau die Fragen versteckt, die auf einer noch nicht
// gegebenen Antwort aufbauen.
setState({});
const hiddenWhenEmpty = ['excluded_countries', 'excluded_countries_other', 'beach_detail',
  'berge_detail', 'duration_daytrip', 'sea', 'accommodation_size', 'home_location',
  'max_distance', 'perfect_daytrip'];
for (const key of hiddenWhenEmpty) {
  check(`leerer Status: ${key} versteckt`, visibleKeys().includes(key), false);
}
check('leerer Status: duration sichtbar', visibleKeys().includes('duration'), true);
check('leerer Status: alle uebrigen Fragen sind sichtbar',
  visibleKeys(), questions.steps.map(s => s.key).filter(k => !hiddenWhenEmpty.includes(k)));
check('bedingte Schritte = Gesamt minus die 4 unbedingten',
  conditionalCount(), stepCount() - 4);

// excluded_countries nur sinnvoll ohne festgelegte Zielregion
setState({ region: [EUROPA] });
check('Region Europa: excluded_countries versteckt', visibleKeys().includes('excluded_countries'), false);
setState({ region: [WELTWEIT] });
check('Region Weltweit: excluded_countries sichtbar', visibleKeys().includes('excluded_countries'), true);
setState({ region: [REGION_EGAL] });
check('Region ohne Praeferenz: excluded_countries sichtbar',
  visibleKeys().includes('excluded_countries'), true);
setState({ region: [BALEAREN, ITALIEN] });
check('Region Balearen+Italien (Mehrfachauswahl): excluded_countries versteckt',
  visibleKeys().includes('excluded_countries'), false);
setState({ region: [WELTWEIT, EUROPA] });
check('Region Weltweit+Europa: excluded_countries sichtbar (mind. eine Bedingung erfuellt)',
  visibleKeys().includes('excluded_countries'), true);

// region + exclusive: Tagesausflug-Wert steuert die Sichtbarkeit, auch als Teil
// eines Arrays
check('region-Step ist Mehrfachauswahl', step('region').type, 'multi');
check('region-Step hat Tagesausflug als exklusive Option',
  (step('region').exclusive || []).includes(DAYTRIP), true);
check('water_type-Step hat "Kein Gewaesser noetig" als exklusive Option',
  step('water_type').exclusive, [KEIN_GEWAESSER]);

// water_type steuert sea-Sichtbarkeit
setState({ water_type: [KEIN_GEWAESSER] });
check('water_type Kein Gewaesser: sea versteckt', visibleKeys().includes('sea'), false);
setState({ water_type: [MEER] });
check('water_type Meer: sea sichtbar', visibleKeys().includes('sea'), true);
setState({ water_type: [MEER, SEE] });
check('water_type Meer+See: sea sichtbar', visibleKeys().includes('sea'), true);

// Unterkunftsart != Hotel -> Hotelgroesse-Frage bleibt versteckt
for (const acc of (step('accommodation').options || []).filter(o => o !== HOTEL)) {
  setState({ accommodation: acc });
  check(`Unterkunftsart ${acc}: accommodation_size versteckt`,
    visibleKeys().includes('accommodation_size'), false);
}
setState({ accommodation: HOTEL });
check('Unterkunftsart Hotel: accommodation_size sichtbar',
  visibleKeys().includes('accommodation_size'), true);

// Nur Strand gewaehlt -> nur beach_detail sichtbar
setState({ interests: [STRAND] });
check('Strand gewaehlt: beach_detail sichtbar', visibleKeys().includes('beach_detail'), true);
check('Strand gewaehlt: berge_detail weiterhin versteckt', visibleKeys().includes('berge_detail'), false);

// Nur Berge gewaehlt -> nur berge_detail sichtbar
setState({ interests: [BERGE] });
check('Berge gewaehlt: berge_detail sichtbar', visibleKeys().includes('berge_detail'), true);
check('Berge gewaehlt: beach_detail weiterhin versteckt', visibleKeys().includes('beach_detail'), false);

// Beides gewaehlt -> beide sichtbar, keine Duplikate/Fehler
setState({ interests: [STRAND, BERGE] });
check('Beide gewaehlt: beach_detail sichtbar', visibleKeys().includes('beach_detail'), true);
check('Beide gewaehlt: berge_detail sichtbar', visibleKeys().includes('berge_detail'), true);

// Kein interests-Key im Status (undefined statt leerem Array) darf nicht crashen
setState({ region: [EUROPA] });
check('interests fehlt: kein Crash, beach_detail versteckt', visibleKeys().includes('beach_detail'), false);

// Anreise: ohne arrival_mode oder mit Flugzeug/keine Praeferenz -> Flugzeit/
// Abflughafen/Transferdauer sichtbar, Startort/Entfernung versteckt
for (const mode of [undefined, FLUGZEUG, ARRIVAL_EGAL]) {
  setState(mode === undefined ? {} : { arrival_mode: mode });
  check(`Anreise ${mode}: flight_time sichtbar`, visibleKeys().includes('flight_time'), true);
  check(`Anreise ${mode}: airports sichtbar`, visibleKeys().includes('airports'), true);
  check(`Anreise ${mode}: transfer_time sichtbar`, visibleKeys().includes('transfer_time'), true);
  check(`Anreise ${mode}: home_location versteckt`, visibleKeys().includes('home_location'), false);
  check(`Anreise ${mode}: max_distance versteckt`, visibleKeys().includes('max_distance'), false);
}

// Anreise: Auto/Bus/Bahn -> Startort/Entfernung sichtbar, Flug-Fragen versteckt
for (const mode of [AUTO, BUS, BAHN]) {
  setState({ arrival_mode: mode });
  check(`Anreise ${mode}: home_location sichtbar`, visibleKeys().includes('home_location'), true);
  check(`Anreise ${mode}: max_distance sichtbar`, visibleKeys().includes('max_distance'), true);
  check(`Anreise ${mode}: flight_time versteckt`, visibleKeys().includes('flight_time'), false);
  check(`Anreise ${mode}: airports versteckt`, visibleKeys().includes('airports'), false);
  check(`Anreise ${mode}: transfer_time versteckt`, visibleKeys().includes('transfer_time'), false);
}

// Tagesausflug gewaehlt -> Laender/Reiseart/Mitreisende/Budget/Unterkunft/Anreise/
// Flug/Freitext versteckt, dafuer Startort/Entfernung/Zeit-Frage sichtbar
setState({ region: [DAYTRIP], water_type: [MEER] });
const hiddenForDaytrip = ['excluded_countries', 'excluded_countries_other', 'interests',
  'travel_type', 'companions', 'budget', 'duration', 'temp', 'accommodation',
  'accommodation_size', 'hotel_wishes', 'travel_pace', 'arrival_mode', 'flight_time',
  'airports', 'transfer_time', 'dislikes', 'perfect_holiday', 'past_trips'];
for (const key of hiddenForDaytrip) {
  check(`Tagesausflug: ${key} versteckt`, visibleKeys().includes(key), false);
}
const shownForDaytrip = ['region', 'duration_daytrip', 'home_location',
  'max_distance', 'month', 'water_type', 'sea', 'activities', 'perfect_daytrip'];
for (const key of shownForDaytrip) {
  check(`Tagesausflug: ${key} sichtbar`, visibleKeys().includes(key), true);
}

// Normaler Urlaubsmodus bleibt von der Tagesausflug-Erweiterung unberuehrt (Regression)
setState({ region: [EUROPA] });
check('Urlaubsmodus: duration sichtbar', visibleKeys().includes('duration'), true);
check('Urlaubsmodus: duration_daytrip versteckt', visibleKeys().includes('duration_daytrip'), false);
check('Urlaubsmodus: dislikes sichtbar', visibleKeys().includes('dislikes'), true);
check('Urlaubsmodus: perfect_daytrip versteckt', visibleKeys().includes('perfect_daytrip'), false);
check('Urlaubsmodus: home_location versteckt (kein arrival_mode)',
  visibleKeys().includes('home_location'), false);
check('Urlaubsmodus: travel_type sichtbar', visibleKeys().includes('travel_type'), true);

if (failures > 0) {
  console.error(`\n${failures} Test(s) fehlgeschlagen.`);
  process.exit(1);
}
console.log('\nAlle Wizard-Engine-Tests bestanden.');
