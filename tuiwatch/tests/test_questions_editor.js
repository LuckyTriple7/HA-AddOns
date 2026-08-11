// Reiner Node-Test ohne Dependency (kein npm/jest im Projekt) fuer den
// Fragebogen-Editor (Rechtsklick auf den TripPilot-Knopf, ab 0.90.1).
//
// Getestet wird nur das, was den Editor gegenueber einem Texteditor
// rechtfertigt: beim Umbenennen/Loeschen einer Option muessen ALLE Nennungen
// des Wertes mitgezogen werden — in `options`, `exclusive`, `show_if`,
// `semantics` und `daytrip_value`. Genau das von Hand zu vergessen hat in
// 0.90.0 vier Kopplungen stillgelegt.
//
// Die Funktionen werden per vm-Modul direkt aus static/app.js geladen, damit
// der Test nicht neben einer Kopie herlaeuft.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const jsPath = path.join(__dirname, '..', 'static', 'app.js');
const js = fs.readFileSync(jsPath, 'utf8');
const questionsPath = path.join(__dirname, '..', 'trippilot_questions.json');
const bundled = JSON.parse(fs.readFileSync(questionsPath, 'utf8'));

function extractBlock(startMarker, endMarker) {
  const start = js.indexOf(startMarker);
  if (start === -1) throw new Error('Start-Marker nicht gefunden: ' + startMarker);
  const end = js.indexOf(endMarker, start);
  if (end === -1) throw new Error('End-Marker nicht gefunden: ' + endMarker);
  return js.slice(start, end);
}

const src = extractBlock('function tpCondWalk(cond, fn){',
                         '\n    // Der semantics-Block wird als Text bearbeitet');

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext('var tpDoc = null;', sandbox);
vm.runInContext(src, sandbox);

function setDoc(doc) {
  vm.runInContext('tpDoc = ' + JSON.stringify(doc) + ';', sandbox);
}
function getDoc() {
  return JSON.parse(vm.runInContext('JSON.stringify(tpDoc)', sandbox));
}
function call(expr) {
  return vm.runInContext(expr, sandbox);
}
function rename(key, oldVal, newVal) {
  call(`tpRenameValue(${JSON.stringify(key)}, ${JSON.stringify(oldVal)}, ${JSON.stringify(newVal)})`);
  return getDoc();
}
function drop(key, val) {
  call(`tpDropValue(${JSON.stringify(key)}, ${JSON.stringify(val)})`);
  return getDoc();
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

// ── Testdokument: ein Miniatur-Fragebogen mit jeder Art von Nennung ───────────
function fixture() {
  return {
    daytrip_value: 'Tagesausflug',
    semantics: {
      package_tour: ['Pauschal'],
      self_arrival: ['Auto', 'Bahn'],
      dna: {
        Strand: { interests: ['Strand', 'Sonne'], region: ['Balearen'] },
        Aktiv: { interests: ['Berge'] }
      }
    },
    steps: [
      { key: 'region', title: 'Wohin?', label: 'Region', type: 'multi',
        options: ['Balearen', 'Weltweit', 'Tagesausflug', 'Egal'],
        exclusive: ['Tagesausflug'] },
      { key: 'interests', title: 'Interessen?', label: 'Interessen', type: 'multi',
        options: ['Strand', 'Sonne', 'Berge'] },
      { key: 'travel_type', title: 'Reiseart?', label: 'Reiseart', type: 'single',
        options: ['Pauschal', 'Nur Hotel'] },
      { key: 'arrival_mode', title: 'Anreise?', label: 'Anreise', type: 'single',
        options: ['Flugzeug', 'Auto', 'Bahn', 'Egal'] },
      { key: 'beach_detail', title: 'Strand wie?', label: 'Strand', type: 'multi',
        options: ['Sand', 'Kies'],
        show_if: { all: [{ key: 'interests', contains: 'Strand' },
                         { not: { key: 'region', contains: 'Tagesausflug' } }] } },
      { key: 'home_location', title: 'Startort?', label: 'Startort', type: 'text',
        show_if: { any: [{ key: 'arrival_mode', in: ['Auto', 'Bahn'] },
                         { key: 'region', contains_any: ['Tagesausflug', 'Weltweit'] }] } },
      { key: 'excluded', title: 'Ausschluss?', label: 'Ausschluss', type: 'text',
        show_if: { key: 'region', equals: 'Weltweit' } }
    ]
  };
}
function stepOf(doc, key) { return doc.steps.find(s => s.key === key); }

// ── Umbenennen einer Option ──────────────────────────────────────────────────
setDoc(fixture());
let d = rename('interests', 'Strand', '🌴 Strand und Meer');
check('Umbenennen: Option selbst geaendert',
  stepOf(d, 'interests').options, ['🌴 Strand und Meer', 'Sonne', 'Berge']);
check('Umbenennen: show_if (contains) gezogen',
  stepOf(d, 'beach_detail').show_if.all[0].contains, '🌴 Strand und Meer');
check('Umbenennen: semantics.dna gezogen',
  d.semantics.dna.Strand.interests, ['🌴 Strand und Meer', 'Sonne']);
check('Umbenennen: fremde dna-Kategorie unberuehrt',
  d.semantics.dna.Aktiv.interests, ['Berge']);
check('Umbenennen: andere Frage unberuehrt',
  stepOf(d, 'region').options, ['Balearen', 'Weltweit', 'Tagesausflug', 'Egal']);

setDoc(fixture());
d = rename('region', 'Tagesausflug', '🚗 Tagesausflug in der Naehe');
check('Umbenennen: exclusive gezogen',
  stepOf(d, 'region').exclusive, ['🚗 Tagesausflug in der Naehe']);
check('Umbenennen: daytrip_value gezogen',
  d.daytrip_value, '🚗 Tagesausflug in der Naehe');
check('Umbenennen: show_if in not{} gezogen',
  stepOf(d, 'beach_detail').show_if.all[1].not.contains, '🚗 Tagesausflug in der Naehe');
check('Umbenennen: show_if contains_any-Liste gezogen',
  stepOf(d, 'home_location').show_if.any[1].contains_any,
  ['🚗 Tagesausflug in der Naehe', 'Weltweit']);

setDoc(fixture());
d = rename('region', 'Weltweit', '🌍 Weltweit');
check('Umbenennen: show_if equals gezogen', stepOf(d, 'excluded').show_if.equals, '🌍 Weltweit');

setDoc(fixture());
d = rename('arrival_mode', 'Auto', '🚗 Auto');
check('Umbenennen: semantics.self_arrival gezogen', d.semantics.self_arrival, ['🚗 Auto', 'Bahn']);
check('Umbenennen: show_if in-Liste gezogen',
  stepOf(d, 'home_location').show_if.any[0].in, ['🚗 Auto', 'Bahn']);
check('Umbenennen: package_tour unberuehrt', d.semantics.package_tour, ['Pauschal']);

setDoc(fixture());
d = rename('travel_type', 'Pauschal', '✈️ Pauschalreise');
check('Umbenennen: semantics.package_tour gezogen', d.semantics.package_tour, ['✈️ Pauschalreise']);

// Ein Wert ohne Fragen-Bezug (package_tour/self_arrival/daytrip_value) darf nur
// mitgezogen werden, wenn es ihn danach nirgends mehr gibt — "Egal" steht bei
// region UND arrival_mode.
setDoc((() => {
  const f = fixture();
  f.semantics.self_arrival = ['Egal'];
  return f;
})());
d = rename('region', 'Egal', 'Keine Praeferenz');
check('Mehrdeutiger Wert: region-Option umbenannt',
  stepOf(d, 'region').options.includes('Keine Praeferenz'), true);
check('Mehrdeutiger Wert: semantics NICHT blind mitgezogen',
  d.semantics.self_arrival, ['Egal']);
check('Mehrdeutiger Wert: arrival_mode unberuehrt',
  stepOf(d, 'arrival_mode').options.includes('Egal'), true);

// Umbenennen auf sich selbst / mit leerem Alt-Wert aendert nichts
setDoc(fixture());
check('Umbenennen ohne Aenderung ist ein No-op',
  rename('region', 'Balearen', 'Balearen'), fixture());

// ── Loeschen einer Option ────────────────────────────────────────────────────
setDoc(fixture());
d = drop('region', 'Tagesausflug');
check('Loeschen: aus exclusive entfernt', stepOf(d, 'region').exclusive, undefined);
check('Loeschen: daytrip_value entfernt', d.daytrip_value, undefined);
check('Loeschen: aus contains_any entfernt',
  stepOf(d, 'home_location').show_if.any[1].contains_any, ['Weltweit']);

setDoc(fixture());
d = drop('interests', 'Sonne');
check('Loeschen: aus semantics.dna entfernt', d.semantics.dna.Strand.interests, ['Strand']);
setDoc(fixture());
d = drop('interests', 'Berge');
check('Loeschen: leer gewordene dna-Gruppe entfaellt', d.semantics.dna.Aktiv, {});

setDoc(fixture());
d = drop('arrival_mode', 'Bahn');
check('Loeschen: aus semantics.self_arrival entfernt', d.semantics.self_arrival, ['Auto']);
check('Loeschen: aus show_if in-Liste entfernt',
  stepOf(d, 'home_location').show_if.any[0].in, ['Auto']);

// ── Umbenennen eines Fragen-Keys ─────────────────────────────────────────────
setDoc(fixture());
call('tpRenameKey("interests", "themen")');
d = getDoc();
check('Key-Umbenennung: show_if verweist auf den neuen Key',
  stepOf(d, 'beach_detail').show_if.all[0].key, 'themen');
check('Key-Umbenennung: dna-Gruppe umgehaengt',
  Object.keys(d.semantics.dna.Strand), ['themen', 'region']);
check('Key-Umbenennung: fremde Bedingung unberuehrt',
  stepOf(d, 'home_location').show_if.any[0].key, 'arrival_mode');

// ── Verweise auf einen Key finden (Warnung vorm Loeschen einer Frage) ────────
setDoc(fixture());
check('Verweise: interests wird von beach_detail und der DNA genutzt',
  call('tpKeyRefs("interests")'), ['„Strand wie?"', 'semantics.dna.Strand', 'semantics.dna.Aktiv']);
check('Verweise: unbenutzter Key hat keine', call('tpKeyRefs("travel_type")'), []);

// ── Gegen die echte Auslieferungsdatei ───────────────────────────────────────
// Kein kuenstliches Dokument: das hier ist der Stand, den ein Nutzer im Editor
// oeffnet. Nach dem Umbenennen des Tagesausflug-Wertes darf keine Nennung des
// alten Wertes uebrig bleiben — sonst meldet die Validierung beim Speichern
// einen Fehler, den der Editor haette vermeiden sollen.
setDoc(bundled);
const oldDaytrip = bundled.daytrip_value;
d = rename('region', oldDaytrip, 'AUSFLUG-NEU');
check('Auslieferungsdatei: daytrip_value gezogen', d.daytrip_value, 'AUSFLUG-NEU');
check('Auslieferungsdatei: alter Wert kommt nirgends mehr vor',
  JSON.stringify(d).includes(JSON.stringify(oldDaytrip).slice(1, -1)), false);
check('Auslieferungsdatei: neuer Wert ist Option der region-Frage',
  stepOf(d, 'region').options.includes('AUSFLUG-NEU'), true);
check('Auslieferungsdatei: Anzahl Fragen unveraendert', d.steps.length, bundled.steps.length);

if (failures > 0) {
  console.error(`\n${failures} Test(s) fehlgeschlagen.`);
  process.exit(1);
}
console.log('\nAlle Fragebogen-Editor-Tests bestanden.');
