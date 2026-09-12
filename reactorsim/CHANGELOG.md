# Changelog

## 0.0.61

- 🐛 **Wertung fing nach Fortsetzen eines Szenarios bei null an.** Nachtrag zu
  0.0.60: das Fortsetzen selbst war repariert, aber `RunState` (Zeit im
  Toleranzband, Abweichung, SCRAM-Zaehler, ...) hatte kein Gedaechtnis ueber
  einen Speicherpunkt hinweg -- ein gespeicherter und fortgesetzter Lauf
  wertete am Ende nur noch die Minuten nach dem Laden, nicht den ganzen Lauf.
  `RunState` hat jetzt `snapshot()`/`restore()` wie Pumpen und Regler; der
  Zwischenstand steckt mit im Speicherblock (`run`-Feld, optional -- alte
  Staende ohne das Feld laden weiter, Wertung faengt dann wie bisher bei null
  an).

## 0.0.60

Drei Funde aus einer echten Spielsitzung.

- 🐛 **Speicherstand-Kollision zwischen Szenario und freiem Spiel.** Der
  Auto-Slot hing nur am Reaktortyp (`auto-<typ>`), nicht am Szenario. Ein
  RBMK-Szenario gespeichert, danach RBMK im freien Spiel gespeichert -- beide
  landeten im selben Slot, der zweite Stand loeschte den ersten wortlos.
  Slot heisst jetzt `auto-<typ>-<szenario>` bzw. `auto-<typ>-free`, jede
  Kombination hat ihren eigenen Platz. Alte Staende im frueheren Format
  bleiben unberuehrt liegen.
- 🐛 **Fortsetzen eines Szenario-Standes wurde immer zu freiem Spiel.** Die
  Fortsetzen-Liste zeigte den richtigen Szenarionamen an, bootete beim Klick
  aber immer mit `scenarioDef = null` -- Bedarfskurve, Ereignisse und
  Erfolgsbedingung des Szenarios waren nach dem Fortsetzen weg, ohne jede
  Meldung. Laedt jetzt dieselbe Szenariodefinition nach wie beim
  Erststart. Bekannte Einschraenkung: die Punktezaehler fuer den Lauf
  beginnen dabei wieder bei null, nicht beim Stand vor dem Speichern.
- 🐛 **RBMK-Leistungsregler nicht stossfrei beim Einschalten.** Automatik
  sprang beim Einschalten auf den Sollwert von Rundenbeginn zurueck, egal wie
  weit die Ist-Leistung seither gewandert war (Handbetrieb, Xenon-Transiente)
  -- bei stark abweichender Leistung zog er dann hart in die falsche
  Richtung. Uebernimmt jetzt beim Einschalten die aktuelle Leistung als
  neuen Sollwert.

## 0.0.59

- 🐛 **Sirene lief im Hauptmenü und nach Neustart weiter.** `toMenu()` und
  `boot()` stoppten Loop und Musik, aber nie `app.horn` -- eine unquittierte
  Meldung liess die Sirene (eigene Dauerschleife, unabhaengig vom Spieltakt)
  einfach weiterlaufen, auch mit verlassener Runde. Beide Stellen rufen jetzt
  `horn.silence()`, bevor der alte Horn verworfen bzw. das Menue gezeigt wird.

## 0.0.58

- 🐛 **Lautloses Einfrieren behoben.** Warf `engine.step()` oder der
  `afterStep`-Callback (Rundenauswertung, Trips) irgendwo einen Fehler, brach
  die ganze rAF-Schleife stumm ab: die Kopfzeile blieb stehen, `running`
  meldete weiter `true`, kein Dialog, kein sichtbarer Fehler — nur ein Neuladen
  half. `app.render.tick()` war schon per try/catch abgesichert, der
  Simulationsschritt selbst nicht. Jetzt fängt `loop.js` das ganze Bild in
  einem try/catch, loggt den Fehler in die Konsole und zeigt den vorhandenen
  Störfall-Dialog mit Fehlerdetail statt eines stillen Stillstands.

## 0.0.57

Vier Dinge, die beim ersten echten Blick auf den Bildschirm auffielen — und
eines davon machte ein Szenario unspielbar.

- 🐛 **Die Borsäure gab es auf dem Desktop nicht.** In `layout.css` stand
  `#rs-p-chem { display: none; }` für alles ab 1024 px, mit der Begründung,
  die Chemie-Werte stünden ja im Kern-Panel. Das galt für die WERTE. In der
  Kachel sitzt aber auch die Bedienung. Damit war auf jedem Desktop-Browser
  **kein Bor dosierbar** — und `pwr_load_follow` dort nicht zu gewinnen, weil
  nach dem klemmenden Stab genau das der einzige verbliebene Weg ist. Die
  frisch geschriebenen Hilfetexte verwiesen auf ein Bedienelement, das der
  Spieler nicht finden konnte, weil es nicht da war.
  Die Kachel hat jetzt einen eigenen Platz im Raster. Nachgemessen mit
  Playwright: drei Reaktortypen × drei Auflösungen, keine Überlappung.
- 🐛 **Die Bedienung lag 140 px unter der Kachelkante.** Auch mit sichtbarer
  Kachel hätte man im Panel scrollen müssen, ohne jeden Hinweis darauf. Die
  Knöpfe stehen jetzt VOR den Messwerten — beim Druckwasserreaktor ist die
  Borsäure das einzige Reaktivitätsstellglied neben den Stäben.
- 🐛 **Die Einweisung war eine Textwand.** `#rs-alarm-help-text` hatte
  `white-space: pre-line`, `#rs-brief-text` nicht. Seit dort in 0.0.56 ein
  Block mit nummerierten Schritten steht, lief ausgerechnet der Teil, der die
  Handgriffe aufzählt, zu einem Absatz zusammen.
- 🐛 **Aus der Einweisung gab es keinen Weg zurück.** Wer ein Szenario
  aufschlug, um zu lesen, worum es geht, musste es anschließend spielen.
  Jetzt steht „Zurück" neben „Schicht beginnen".

### Ton

- 🔊 **Mute-Knopf**, auf dem Startbildschirm und in der Kopfzeile des
  Leitstands. Vorher lagen die drei Tonschalter ausschließlich im
  Zahnrad-Dialog INNEN — wer es still haben wollte, musste erst eine Schicht
  beginnen.
  `prefs.audio.muted` ist ein Hauptschalter über Musik, Hupe und
  Geigerzähler; die drei Einzelschalter bleiben erhalten, damit sie nach dem
  Aufdrehen wieder so stehen wie vorher. Der Zustand wird gespeichert und
  überlebt das Neuladen.
- 🧹 **`applyAudioPrefs()`** ist jetzt die einzige Stelle, die den Tonzustand
  herstellt. Dieselbe Rechnung stand vorher dreimal im Code (Laden der
  Einstellungen, Speichern im Zahnrad-Dialog, Rundenstart für die Hupe) — ein
  vierter Schalter wäre ein vierter Ort zum Vergessen gewesen.

**Warum der Ton erst nach einem Klick kommt, bleibt so:** das ist keine
Einstellung, sondern die Autoplay-Sperre der Browser. Ohne echte Nutzergeste
verweigern Chrome, Firefox und Safari jeden Ton. Das Spiel nutzt den ersten
Klick auf eine Reaktorkarte dafür — vorher *kann* nichts kommen.

Nachgeprüft mit Playwright statt behauptet: `play()`/`pause()` mitgeschrieben,
stumm läuft kein einziger Aufruf, Aufdrehen im Leitstand startet die
Hintergrundmusik sofort, beide Knöpfe bleiben synchron.


## 0.0.56

Alle 33 Hilfetexte und alle 9 Einweisungen neu geschrieben, in beiden
Sprachen, jede Aussage gegen den Code geprüft.

Der Anlass war eine einzige Frage: „Was ist hier zu tun?" Die Hilfe zu
„Frischdampf abgesperrt" nannte als einzige Handlung „Absperrung auf Offen
stellen" — und dieser Klick wirkt genau einen Rechenschritt lang. Dieselbe
Frage stellte sich bei der Einweisung zum Lastfolgebetrieb: sie sagt „ab da
bleibt nur noch Bor" und nirgends, dass das Bedienelement „Borsäure" heißt
und im Reiter Chemie sitzt.

### Was sich an jedem Text geändert hat

- 📍 **Jedes Bedienelement wird mit Kachel und Namen genannt**, so wie es auf
  dem Schirm steht. „Bor dosieren" ohne zu sagen wo, ist keine Anleitung.
- 🔢 **Wo die Reihenfolge zählt, ist nummeriert.** Beim Frischdampf etwa:
  abschalten, DANN Notkondensator — der arbeitet nur bei abgeschaltetem
  Reaktor, andersherum passiert nichts.
- 🚫 **Wo etwas NICHT wirkt, steht das jetzt da.** „Regelventil" und
  Umleitstation sitzen hinter der Absperrung; sie zu öffnen ändert nichts.
  Der alte Text zu „Domdruck hoch" empfahl genau das.
- 🔬 **Jede Zahl gegen den Code geprüft:** Ansprechpunkte der Sicherheits- und
  Abblaseventile, Umleitstation, Auslegungsdruck des Sicherheitsbehälters,
  Trommeldruck, Grenzwerte der Meldungen.

### Drei Texte, die vorher falsch waren

- **„Frischdampf abgesperrt"** verwies auf eine unmögliche Handlung und
  erwähnte weder Schnellabschaltung noch Notkondensator — also genau die
  beiden Dinge, auf die es ankommt.
- **„Domdruck hoch"** empfahl Regelventil und Umleitstation. Beide sind
  wirkungslos, wenn der Druck steigt, WEIL abgesperrt ist — dem häufigsten
  Fall, in dem diese Meldung kommt.
- **„Abblaseventil offen"** versprach, das Ventil schließe von selbst wieder.
  Bei der klemmenden Störung stimmt das nicht, und der Spieler wartete auf
  etwas, das nie kam.

### Ein Test, der diese Fehlerklasse künftig abfängt

`test_help_texts_only_name_controls_that_exist` prüft jedes in
Anführungszeichen genannte Bedienelement gegen die tatsächlichen
Beschriftungen — in Hilfetexten und Einweisungen, in beiden Sprachen, ohne
Ausnahmeliste. Er fängt nicht jede falsche Aussage (ob eine Handlung in
DIESER Lage wirkt, weiß nur der Code), aber die häufigste: ein Bedienelement
nennen, das unter diesem Namen gar nicht existiert.

Beim ersten Lauf fand er drei eigene Fehler in den frisch geschriebenen
Texten:

- `„-Heizung"` — abgekürzt statt ausgeschrieben, kein Bedienelement.
- Die englischen Texte schickten den Spieler auf einen Knopf `"closed"`. Der
  heißt dort **`shut`**.
- Der englische Text verwies auf `"SCRAM/RESA/AZ-5"`; der Glossareintrag
  heißt `SCRAM / RESA / AZ-5`, mit Leerzeichen.

Genau die Sorte Abweichung, die einen Spieler vergeblich suchen lässt.

### Die Einweisungen

Die Erzählung bleibt unangetastet — sie stellt die Lage gut dar. Jede bekommt
einen Block „Darauf kommt es an" mit drei bis fünf Punkten: welches
Bedienelement, welche Kachel, welche Reihenfolge, und worauf beim Ablesen zu
achten ist. Beim Lastfolgebetrieb steht jetzt da, dass „Borsäure" in der
Kachel Reaktorchemie sitzt, dass Verdünnen die Leistung hebt und Aufborieren
sie senkt — und dass man wegen der drei Minuten Totzeit früh und in kleinen
Schritten dosieren muss, statt zu warten, bis die Abweichung sichtbar ist.


## 0.0.55

Ein Spieler fragte, was bei „Frischdampf abgesperrt" zu tun sei. Die Hilfe
nannte als einzige Handlung „Absperrung auf Offen stellen". Nachgemessen:
der Klick wirkt genau einen Rechenschritt lang, dann schreibt die Störung die
Stellung zurück. Beim Nachgehen stellte sich heraus, dass das Symptom war,
nicht die Krankheit.

**Sieben von neun Szenarien bestand man, indem man nichts tat.** Nachgemessen
mit `tests/tools/passive.mjs` (neu), einem Lauf ohne jede Bedienung:

- `pwr_porv_stuck`, das Three-Mile-Island-Szenario: Primärkreis läuft auf
  1 bar und 0 % Druckhalterfüllstand leer — vollständiger Kühlmittelverlust —
  und die Brennstofftemperatur steht die ganze Zeit unverändert auf 1027 °C.
  Ergebnis: „geschafft", 1750 Punkte, der höchste Wert im ganzen Spiel.
- `bwr_msiv`: Sicherheitsbehälter berstet nach zehn Minuten, Druck läuft auf
  110 bar — das Fünfundzwanzigfache des Auslegungswerts. Ergebnis: „geschafft".

Ursache war nicht Nachlässigkeit an einer Stelle, sondern eine fehlende
Kopplung: **der einzige Verlustweg war die Brennstoffenthalpie**, und die
greift nur bei einer schnellen Leistungsexkursion. Kühlmittelverlust,
geborstener Sicherheitsbehälter, überhitzte Hüllrohre — alles ohne Folgen.
Wer nichts falsch machen kann, kann auch nichts lernen.

### Die Anlage kann jetzt kaputtgehen

- ⚛️ **Der Kern dampft bei Druckverlust aus.** Der generische Kernpfad
  (`engine.js stepCore`) rechnete die Wärmeabfuhr über flüssiges Wasser, ohne
  je zu fragen, ob es bei dem herrschenden Druck noch welches gibt. Jetzt
  bricht der Wärmeübergang ein, sobald die Kühlmitteltemperatur die Sättigung
  übersteigt.
  Der erste Versuch dafür war falsch und steht als Warnung im Code: ein
  zusätzlicher Term neben der Wasserkühlung verlor gegen diese im Verhältnis
  700:1, weil deren Zeitkonstante bei 0,3 s liegt und die des Ausdampfens bei
  Minuten. Abgesenkt werden muss der Durchgang selbst.
- ⚛️ **Kavitierende Pumpen fördern Dampf, nicht Wasser.** Eine Kreiselpumpe
  fördert Volumen; bei 1 bar hat Dampf rund 1/1600 der Dichte von Wasser.
  Vorher standen im leergelaufenen Primärkreis unverändert 20 000 kg/s im
  Kern, und die Durchsatz-Auslösung meldete nichts, weil der Messwert stimmte.
- ⚛️ **Vier Verlustwege statt einem** (`engine.js checkLoss`): Brennstoff-
  enthalpie wie bisher, dazu Hüllrohrversagen (über 1204 °C für mehr als drei
  Minuten — ab da trägt sich die Zirkon-Wasser-Reaktion selbst), Kühlmittel-
  verlust (Unterkühlung über fünf Minuten unter null) und, typeigen über
  `hooks.lossCriteria`, der geborstene Sicherheitsbehälter. Beide Zeiten
  bewusst in Minuten: ein Grenzwert, der im Augenblick des Überschreitens
  zuschlägt, wäre eine Falle und kein Lernstoff.
- 🖥️ **Der Endbildschirm sagt jetzt, WORAN es lag** — einer von vier Texten
  statt immer „Kernzerstörung, Brennstoffenthalpie über 963 J/g".

### Der Füllstand des Siedewasserreaktors log

- 🐛 **Das Inventar hatte keine Obergrenze.** Bei abgesperrtem Frischdampf
  speiste der Regler mit 1724 kg/s nach, während nur 900 kg/s über das
  Sicherheitsventil abgingen — nach vierzig Minuten standen **2 056 144 kg**
  im Behälter, das Elffache des Nennwerts.
- 🐛 **Und die Anzeige zeigte dabei 11 %.** Der Schrumpf-/Quell-Term ist als
  kleine Verfälschung um den Betriebsdruck gedacht; bei 110 bar lieferte er
  −91 Prozentpunkte. Da die Speisewasserregelung auf genau diese Anzeige
  regelt, sah sie einen fast leeren Behälter und speiste noch mehr — die
  selbstverstärkende Schleife hinter den 2000 Tonnen. „Füllstand hoch" konnte
  nie ansprechen, weil die Anzeige unten klebte. Beides ist jetzt begrenzt.
- ⚖️ **Sicherheitsbehälter neu bemessen.** `capacity` stand auf 60 000 kg —
  bei voll geöffnetem Sicherheitsventil riss er nach 67 Sekunden. Solange das
  folgenlos blieb, fiel es nicht auf; als Verlustbedingung wäre es eine Falle
  gewesen. Der neue Wert (520 000 kg) ist von der Kondensationskammer her
  gerechnet und lässt gut zehn Minuten. `ventCv` war mit 9 kg/s gegen 900 kg/s
  Zustrom wirkungslos, obwohl die Hilfe Venten als die Rettung nennt; 60 kg/s
  liegt über der Nachzerfallsverdampfung, also hilft es an einem
  abgeschalteten Reaktor wirklich — und bleibt chancenlos gegen einen, der
  noch läuft. Genau die Reihenfolge, die die Hilfe beschreibt.

### Klemmende Stellglieder melden sich

- 🔔 **Drei neue Meldungen:** „Stabgruppe klemmt", „Frischdampf-Absperrung
  klemmt", „Abblaseventil klemmt offen". Vorher klickte man ins Leere: der
  Knopf ließ sich drücken, die Stellung sprang zurück, und nichts sagte warum.
  Jede der drei bringt eine Hilfe mit, die die Handlungen nennt, die
  stattdessen wirken — mit Reiter, Bedienelement und Reihenfolge.

### `pwr_porv_stuck` war nicht zu gewinnen

- 🎛️ **Blockventil ergänzt** (Reiter Primär). Das Abblaseventil klemmt offen,
  und es gab kein einziges Bedienelement dagegen — der Primärkreis lief leer,
  ganz gleich was der Spieler tat. Genau dieses Ventil hat in Three Mile
  Island das Leck schließlich gestoppt, nach zweieinhalb Stunden.

### Die Szenarien reagieren

- 🎯 **Neue Fehlbedingung `trip_ignored`:** eine Auslösemeldung steht fünf
  Minuten an, ohne dass abgeschaltet wird. Das ist die Lehre dieses Spiels in
  eine Regel gefasst — die Meldetafel schaltet nichts ab, der Bediener muss.
- 🎯 **Netzbedingungen ergänzt**, mit einer Schwelle aus der szenarioeigenen
  Toleranz (dem Dreifachen) statt geratener Zahlen. Reine Störfall-Szenarien
  bekommen keine, dort wäre der verlorene Lastabsatz Folge und nicht Fehler.
- 🐛 **`grid_deviation` feuert nicht mehr bei abgeschaltetem Reaktor.** Wer auf
  eine Auslösemeldung hin richtig abschaltet, kann danach keine Leistung
  liefern — ihn dafür den Lauf verlieren zu lassen bestrafte genau die
  Handlung, zu der jeder Hilfetext auffordert. Die Schnellabschaltung kostet
  ohnehin 500 Punkte; sie darf Geld kosten, nicht die Anlage.

### Gemessen statt geglaubt

Zwei Sonden, beide dauerhaft im Baum:

- `tests/tools/passive.mjs` — Lauf ohne jede Bedienung. **Vorher 7 von 9
  bestanden, jetzt 0 von 9.**
- `tests/tools/competent.mjs` — Gegenprobe mit schlichter, korrekter
  Betriebsweise. **8 von 9 bestanden.** Die Gegenprobe ist die wichtigere von
  beiden: Szenarien so scharf zu stellen, dass Nichtstun scheitert, ist leicht
  — man kann dabei versehentlich jeden richtigen Lauf unmöglich machen und
  hätte die Fehlerrichtung nur gedreht. (Das neunte, `rbmk_night_shift`,
  scheitert an der Sonde, nicht am Spiel: sie führt die Last des RBMK nur
  grob.)

- ✅ **`test-game.mjs` baute Kaltstart-Szenarien mit heißem Kern auf** — das
  `cold`-Flag wurde nicht durchgereicht, anders als in `main.js boot()`. Der
  Test prüfte damit eine Lage, die es im Spiel nicht gibt. Aufgefallen ist es
  erst, als die Netzabweichung zu einer Fehlbedingung wurde.


## 0.0.54

Durchsicht auf Fehler und Optimierungen -- nichts davon fiel im Spiel auf,
zwei davon hätten es früher oder später getan.

- 🔒 **Bestenliste war beliebig manipulierbar.** Der Schwierigkeitsgrad ging
  als Faktor in den Abschlussbonus ein, und zwar ohne Deckel -- aber er kam
  aus der Anfrage. `validate_summary()` prüft jede andere Kennzahl auf
  Plausibilität, diese nicht: `difficulty: 1000000` mit `completed: true`
  ergab **250 001 000 Punkte** und ging glatt durch. Der Wert kommt jetzt aus
  der Szenariodatei und wird überschrieben statt geprüft -- so kann er gar
  nicht erst falsch sein, und ein Lauf ohne das Feld bekommt trotzdem den
  richtigen Bonus.
- 🔒 **Sicherheits-Kopfzeilen ergänzt.** Es gab keine. Der Dienst hängt auf
  einem offenen LAN-Port, und ohne `frame-ancestors` ließ sich die
  Anmeldeseite in einen fremden Rahmen setzen. Jetzt CSP (streng, `'self'`
  und sonst nichts), `X-Frame-Options`, `X-Content-Type-Options`,
  `Referrer-Policy`, `Permissions-Policy`. Die zwei bewusst eingebetteten
  Blöcke -- Übersetzungstabelle in `index.html`, vollständiges CSS in
  `login.html` -- bekommen eine Nonce je Antwort statt `'unsafe-inline'`:
  mit `unsafe-inline` wäre jedes eingeschleuste `<script>` mit erlaubt, und
  die Richtlinie hätte gegen genau den Fall nichts mehr zu sagen.
- 🐛 **Vorspulen nach Kernzerstörung setzte die Anlage wieder in Gang.** Die
  Xenon-Vorausschau (`fastForwardXenon`) prüfte am Ende auf
  `destroyed && !endShown`. Die Bildschleife läuft während ihrer Pausen aber
  weiter und kann den Kernzerstörungs-Dialog selbst öffnen -- dann stand
  `endShown` schon, der Zweig fiel durch, und der Zweig für den Normalfall
  schrieb "Zeitsprung" ins Protokoll und stellte den Zeitraffer auf 1×, mit
  offenem Kernzerstörungs-Dialog davor.
- 🐛 **Netzabweichung wurde in Schritten gezählt, nicht in Sekunden.**
  `RunState.checkFail()` summierte die Dauer mit einer fest im Code stehenden
  `0.05` statt mit dem übergebenen `dt`. Heute zufällig richtig, weil
  `loop.js` mit genau dieser Schrittweite rechnet -- und in dem Augenblick
  lautlos falsch, in dem irgendwo eine andere benutzt wird. `dt` kommt jetzt
  aus dem Aufruf, ein Test hält zwei Schrittweiten gegeneinander.
- 🐛 **Ratenbegrenzung wuchs unbegrenzt.** Aufgeräumt wurden nur Einträge mit
  leerer Trefferliste. Ein Spieler-Token, das einmal getroffen und nie wieder
  gesehen wurde, blieb für immer stehen -- bei einem Cookie je Gerät wuchs die
  Tabelle über die Laufzeit des Containers monoton mit. Jetzt fliegt raus, was
  außerhalb seines Zeitfensters liegt.
- ✅ **CI baut nicht mehr ungeprüft.** Der Workflow schob bei jedem
  VERSION-Bump ein Image nach GHCR, ohne einen einzigen Test zu starten -- die
  75 Tests im Ordner liefen ausschließlich von Hand, darunter die komplette
  Simulationsprüfung. Jetzt laufen `pytest` und `node --test` vor dem Bau, und
  der Bau hängt am Ergebnis.
- ✅ **Die zwei dauerhaft roten Tests sind repariert**, statt weiter im Backlog
  zu stehen. `test_dockerfile.py` verglich Windows-Backslash-Pfade gegen die
  Schrägstrich-Ziele des Dockerfiles und scheiterte dort an *jedem* Modul in
  einem Unterordner -- also genau an denen, die er prüfen soll. `test_auth.py`
  prüfte POSIX-Rechtebits auf NTFS. Ein roter Test, den man zu ignorieren
  lernt, prüft nichts mehr; der Dockerfile-Test ist ausgerechnet der, der ein
  vergessenes `COPY` fangen soll. Nebenbei: `auth.py` fehlte in seiner Liste.
- ⚡ **`sanitize()` baut keine Wegwerf-Arrays mehr.** Es lief über
  `Object.entries(RANGES)` und legte damit in jedem Rechenschritt vierzehn
  frische Paar-Arrays an -- bis zu 1200-mal je Sekunde im 60-fachen
  Zeitraffer, für eine konstante Tabelle.
- ⚡ **`write_save()` zählt nur noch.** Für die Slot-Obergrenze öffnete und
  parste es über `list_saves()` bis zu zwanzig Spielstände, um nichts davon
  zu benutzen.
- 🧹 `.dockerignore` ergänzt. Ändert nichts am Image -- die Wurzeldateien
  werden ohnehin einzeln kopiert --, hält aber `dev_data/` mit `auth.json`
  und `secret.key` aus dem Build-Kontext.
- 📋 Backlog neu geschrieben: die beiden erledigten Test-Punkte raus, dafür
  die zurückgestellten Erweiterungen mit Begründung drin (serverseitige
  Nachrechnung, Wiedergabe, Web Worker, vierter Reaktortyp, CSV-Export,
  Mehrbenutzerbetrieb).

Nicht übernommen: ein Puffer für `engine.derive()`. Der Wert wird je Bild
sechsmal gebraucht und jedes Mal neu gerechnet, das sah nach einem leichten
Gewinn aus. Gemessen sind es ein paar Mikrosekunden von sechzehn
Millisekunden je Bild -- und der Puffer kostete genau die Eigenschaft, um die
es im Kopf von `sim/state.js` geht: wer den Zustand von außen anfasst und
danach `derive()` liest, bekam den Wert von vorher. Ein Test fiel sofort
darauf herein. Rückgängig gemacht, Begründung steht jetzt an `derive()`.

## 0.0.53

- 🖼️ **Beschriftungen und Messwerte lagen auf Rohrleitungen** -- über alle
  drei Fließbilder verteilt (SWR am schlimmsten: "Notkondensator"-Label
  quer über der Frischdampfleitung, Füllstand direkt drauf). Ursache: die
  Positionen waren einzeln von Hand gesetzt, ohne die tatsächliche
  Rohrgeometrie zu prüfen. Mit `getBBox()`/`isPointInStroke()` in einem
  echten Browser für alle drei Typen automatisiert nachgemessen (nicht nur
  am Bild geraten) und behoben:
  - SWR: Notkondensator-Baugruppe hochgesetzt (in den seit v0.0.51
    reservierten Raum über der viewBox), Ventil-Label jetzt links statt
    darüber, Füllstand über dem Kästchen statt daneben, Kondensatrücklauf
    zapft seitlich ab statt mittig durch die neue Beschriftung.
  - Alle drei Typen: Regelventil-Label jetzt rechts (zur Turbine) statt
    links -- links verläuft eine parallele Steigleitung zur Umleitung genau
    durch die Beschriftung. Umwälzpumpe sitzt jetzt an der unteren
    Schleifenecke statt mittig auf der Rohrleitung (wie beim DWR seit je).
  - DWR: "Dampferzeuger"-Beschriftung tiefer gesetzt -- das Speisewasserrohr
    fiel genau durch die alte Position.
  - RBMK: Leistungsanzeige tiefer im Kanalblock (Steigleitung im Weg),
    "Druckröhren"-Beschriftung linksbündig statt mittig (kollidierte sonst
    mit der verschobenen Pumpenbeschriftung).

## 0.0.52

- 🔒 **CodeQL-Alerts gefixt:** Pfad-Aufbau bei Spielstaenden/Bestenliste
  (`persist.py`) lief bisher ueber `os.path.join` nach Regex-Pruefung --
  CodeQL erkennt `re.match` nicht als Sanitizer, deshalb zusaetzlich durch
  `werkzeug.safe_join` geschickt. Uebersetzungsdatei (`app.py`) kommt jetzt
  aus einer festen `{sprache: dateiname}`-Zuordnung statt aus einem
  f-String mit der Sprachkennung. Offene Weiterleitung nach dem Login
  (`auth.safe_next`) setzt das Ziel jetzt aus den per `urlsplit` geparsten
  Bestandteilen neu zusammen (`urlunsplit`), statt den prüften Rohwert
  durchzureichen -- rein Haerten, keine Funktionsaenderung.

## 0.0.51

- 🖼️ **Sicherheitsventil-Label saß auf dem Notkondensator-Label** (SWR-
  Fließbild) -- beide quetschten sich in denselben schmalen Streifen über
  dem Frischdampf. `viewBox` um 40px nach oben erweitert, Sicherheitsventil
  dorthin verschoben, klare Trennung jetzt.
- 🏷️ **"Dampferzeugerfüllstand" hieß auch beim SWR/RBMK so**, wo es keinen
  Dampferzeuger gibt (Kernbehälter/Trommelabscheider). Label auf
  typneutrales "Füllstand" vereinfacht.

## 0.0.50

- 🐛 **Sicherheitsbehälter beim Fukushima-Szenario riss praktisch sofort.**
  `capacity: 2600` war so klein, dass schon der erste, harmlose
  Sicherheitsventil-Stoß direkt nach der Isolierung (~7.500 kg in 30
  Sekunden, Notkondensator fängt das normalerweise ab) den Grenzwert riss —
  4 Sekunden nach dem Erdbeben, lange vor dem eigentlichen Stromausfall.
  Per Engine-Simulation nachgerechnet und auf `60000` gesetzt: der harmlose
  Erststoß bleibt jetzt sicher drunter, ein unbehandelter Blackout reißt den
  Behälter nach ca. 40 Minuten statt 4 Sekunden.
- 🌊 **Füllstandsanzeige lügt beim Stromausfall mit, wie der Notkondensator.**
  2011 zeigte die Warte lange einen stabilen Füllstand, während der Kern in
  Wirklichkeit bereits freilag — die Anzeige hing an derselben Gleichstrom-
  versorgung wie der Rest der Instrumentierung. Jetzt friert `d.L_sg`
  (Kopfzeile und Fließbild) beim Stromausfall auf dem letzten echten Wert
  ein, während der Kern real weiter leerläuft.
- 🔧 **Frischdampf-Absperrung (SWR-Störfall-Szenario) blieb nicht zu.**
  `msiv_close` setzte `s.msiv` bisher nur einmalig auf 0 -- ein Klick auf
  "offen" machte die ganze Störung rückgängig. Jetzt wie ein klemmender
  Stab dauerhaft erzwungen (`ctx.msivStuck`).
- 🖼️ **Sicherheitsventil jetzt im Fließbild sichtbar** (SWR), vorher nur als
  Meldetafel-Alarm ohne jede Stelle im Bild.
- 📝 Ereignisprotokoll: "gekommen"/"gegangen" durch klareres
  "ausgelöst"/"beendet" ersetzt.

## 0.0.49

- 🟢 **Kopfzeilen-Werte jetzt durchgehend grün/gelb/rot.** Viele der 44
  wählbaren Statuszeilen-Werte (Primärdruck, Kernstrom, Periode,
  Reaktivität, SG-Füllstand, Achsversatz, Graphittemperatur, Notkondensator-
  Vorrat, Umwälzstrom, Abklingverhältnis, ...) zeigten bisher nie eine Farbe,
  selbst wenn die Anlage längst im Warnbereich stand -- nur wenige Werte
  (Brennstoff, Hülltemperatur, DNBR, ORM, ...) hatten das schon. Neue
  Schwellen sind dieselben Zahlen wie die echten Grenzwertproben je Typ
  (`plants/*.js`, `trips`), nicht frei erfunden -- wo es keine gibt (z.B.
  Anforderung, Xenon, Bor, Abbrand), bleibt der Wert bewusst ungefärbt statt
  eine Gefahr vorzutäuschen, die das Modell gar nicht kennt. Werte ohne
  Alarm zeigen jetzt zusätzlich explizit Grün statt nur neutralem Weiß.

## 0.0.48

- 🎵 **Aufgenommene Klangeffekte statt Synthese, plus Musik.** Meldehupe,
  SCRAM und Kernzerstörung liefen bisher komplett über WebAudio-Oszillatoren
  (`annunciator.js`); jetzt echte Aufnahmen (`static/audio/*.mp3`, Pixabay-
  Lizenz). Die Hupe läuft dabei als Dauerschleife, solange eine Meldung
  unquittiert ist, statt sich jede Sekunde neu anzusetzen.
- 🆕 **Intro- und Hintergrundmusik.** Startbildschirm bekommt eine eigene
  Musikschleife (ab dem ersten Klick auf eine Reaktorkarte), eine laufende
  Runde eine andere -- beide über den neuen "Musik"-Schalter im Ton-Dialog
  ab-/anschaltbar, unabhängig von Hupe und Geigerzähler.
- 🆕 **Akustische Vorwarnung vor Szenario-Ereignissen.** 2-5 Minuten bevor
  ein geplantes Ereignis (Pumpenausfall, klemmender Stab, ...) tatsächlich
  eintritt, kommt einmalig ein kurzer Warnton -- geseedet wie das Ereignis
  selbst, reproduzierbar bei gleichem Szenario-Seed.

## 0.0.47

- ❄️ **Kaltstart jetzt auch in Szenarien.** Bisher erzwang `boot()` immer ein
  warmes Anfahren, sobald ein Szenario lief -- der `cold`-Modus (alle Stäbe
  drin, Pumpen aus, `trim()` schwingt bewusst NICHT auf Kritikalität ein) war
  auf das freie Spiel beschränkt. Ein Szenario kann jetzt `"cold": true`
  setzen und startet dann wirklich kalt.
- 🆕 **Neues Szenario: "Kaltstart nach Revision" (RBMK).** Anders als
  "Nachtschicht" (steht bei Volllast, fährt runter und wieder hoch) beginnt
  dieses Szenario kalt und steigt von unten durch die 200-Megawatt-
  Gefahrenzone -- Pumpen anfahren, Stäbe behutsam ziehen, kritisch werden,
  hochfahren, während eine Stabbank klemmt und später eine Umwälzpumpe
  ausfällt.
- 📖 **Alle Einweisungstexte zu echten Kurzgeschichten ausgebaut.** Die
  bisherigen zwei bis drei Sätze pro Szenario waren zu knapp, um die
  Situation wirklich zu verstehen. Jetzt: Zeit/Ort, was passiert, warum es
  gefährlich ist, was zu tun ist -- auf Deutsch und Englisch, für alle neun
  Szenarien.
- 🔁 **Einweisung während der Runde erneut aufrufbar.** Neuer Knopf in der
  Kopfzeile (nur bei Szenarien, nicht im freien Spiel) öffnet dieselbe
  Einweisung noch einmal, ohne die laufende Runde zu unterbrechen.
- ⌨️ **Tastenkürzel-Übersicht ergänzt.** Leertaste, Zeitraffer 1-4 und Esc
  standen bisher nirgends im Spiel selbst -- neues Hilfe-Fenster nach dem
  Muster des Grundlagen-Glossars.

## 0.0.46

- 💾 **Spielstand speicherte Pumpen, Ventile und Regler bisher gar nicht.** Nur Zahlen/Bool'sche Felder direkt am Zustand wurden mitgesichert -- Pumpen (Kaltstart: an/aus, Drehzahl), Regelventile (Stellung), und Regler (Automatik/Hand, Handwert, PI-Integrator) leben in eigenen Objekten daneben und kamen beim Laden IMMER frisch (= Vollast, Automatik) zurück, ganz gleich was eingestellt war.
  Jede betroffene Klasse (Pump, Valve, PI, Lag, RateLimiter, TransportDelay, RodController, PressurizerController, FeedwaterController, GovernorController, PowerController) hat jetzt `snapshot()`/`restore()`; jeder Reaktortyp meldet seine Instanzen über `ctx.saveable` (ein Objekt, keine Sonderfälle in persist.js). Alte Spielstände ohne dieses Feld laden weiter -- die Komponenten federn dann wie bisher auf ihre Anfangswerte ein, statt den Ladevorgang scheitern zu lassen.
  Per Node-Roundtrip (packen → frische Engine → laden) bei allen drei Typen bit-genau bestätigt: Pumpenzustand, Automatik/Hand-Stellung, PI-Integrator, Ventilstellung -- alles exakt wie vorher. Zusätzlich im echten Browser verifiziert: Pumpe gestartet, gespeichert, Seite komplett neu geladen, fortgesetzt -- Pumpe läuft weiter, statt wieder zu stehen.

## 0.0.45

- 📊 **Gesamtreaktivität jetzt auch als Kopfzeilen-Wert wählbar.** Bisher nur als Zeigerausschlag (Rundinstrument) und als "Gesamt"-Balken in der Reaktivitätsbilanz sichtbar, beides nur im Kern-Panel -- jetzt auch als reine Zahl mit Vorzeichen (z.B. "+120 pcm") im Katalog der Kopfzeilen-Einstellungen, genau wie die anderen 44 Werte.

## 0.0.44

- 💡 **Hinweis: thermische Leistung sagt bei Kritikalitätsannäherung nichts.** Real UND in dieser Sim bleibt sie bei 0,0 % stehen, lange bevor beim Stäbeziehen etwas ansteht -- Periode und Reaktivitätsbilanz reagieren viel früher. Neuer Hinweistext im Kern-Panel, direkt unter der Leistungsanzeige.

## 0.0.43

- 🔧 **Kaltstart: jetzt auch die Pumpen aus.** Hauptkühlmittel-/Umwälz-/Umwälzpumpen standen bisher trotz "Reaktor aus" auf voller Drehzahl -- der Kaltstart deckte nur Stäbe (und beim DWR Bor) ab. Jetzt stehen sie zu Beginn (Anzeige "stopped", nicht "tripped" -- kein Störungsauslauf, einfach nie gestartet), Naturumlauf hält den Kern trotzdem sicher. Der Spieler schaltet sie über denselben Knopf zu, mit dem er sonst eine ausgefallene Pumpe neu startet. Betrifft alle drei Typen.
  Nebenbei die Grundlage dafür geschaffen: `Pump.flow()` gab den Naturumlauf-Sockel bisher nur her, wenn die Pumpe mal lief oder ausgelöst hat (`running || tripped`) -- eine Pumpe, die einfach noch nie gestartet wurde, wäre auf echten Nullstrom gelaufen. Jetzt gilt der Sockel immer, was er physikalisch auch tut.

## 0.0.42

- ☢️ **Geigerzähler-Ticken.** Tickt gelegentlich im Leerlauf (0,1/s, reine Atmosphäre -- eine Leitwarte hat normalerweise keine spürbare Strahlung), deutlich schneller im Takt einer anstehenden Meldung, gestaffelt nach Schwere. Neue Sound-Sektion im ⚙-Menü ("Einstellungen", vorher "Kopfzeile anpassen") mit zwei Häkchen: Meldehupe und Geigerzähler, beide dauerhaft gespeichert (`/api/prefs`). Anders als die Hupe (pro Runde neu gebaut) lebt der Geigerzähler über die ganze Sitzung -- schon auf dem Startbildschirm entsperrt, tickt ab der ersten Runde, nicht erst nach dem ersten SCRAM. Per Playwright verifiziert: 2 Ticks/20s im Leerlauf (genau die konfigurierten 0,1 Hz), deutlich mehr direkt nach SCRAM, Aus-Schalter bringt es sofort auf null.

## 0.0.41

- 📱 **Kopfzeilen-Bedienung lief auf schmalen Handys über.** Xenon-Vorspulknopf (Text) plus Zeitraffer, ⚙, ?, Speichern, Menü, SCRAM passten ab 360px Breite nicht mehr in eine Zeile -- SCRAM konnte bis zu 25px hinterm sichtbaren Rand landen. Vorspulknopf jetzt Icon (⏩) statt Text wie die anderen Werkzeugknöpfe, Zeile bekommt zusätzlich `flex-wrap`, damit sie bei Bedarf sauber zweizeilig wird statt zu überlaufen. Per Playwright bei 360px verifiziert: passt jetzt exakt, SCRAM immer voll sichtbar.
- ⚗️ **Xenon-Override beim Hochfahren aus dem Kaltstart bestätigt.** Kein Code nötig, nur nachgerechnet: fährt man nach dem Kaltstart rein über Stäbe auf Vollast, drückt das nachwachsende Xenon die Leistung in den folgenden Stunden bis auf rund 12 % herunter, sobald die Stäbe ganz draußen sind und nichts mehr nachgeben -- der Kern erholt sich danach von selbst erst nach rund einem Tag. Genau das reale "Xenon-Override"-Problem; beim DWR hilft in der Praxis Verdünnen (`ctl_boron_dilute`) über die Stabreserve hinaus.
- 💾 Kaltstart-Häkchen wird jetzt gespeichert (`/api/prefs`, wie die Kopfzeilen-Auswahl) statt bei jedem Besuch neu gesetzt werden zu müssen.

## 0.0.40

- 🗑️ **Spielstände löschen.** Jeder Eintrag in der Fortsetzen-Liste hat jetzt einen Löschen-Knopf, gesichert wie SCRAM (erster Klick bewaffnet, zweiter binnen 4s löscht wirklich). Backend (`DELETE /api/saves/<slot>`) gab es schon, es fehlte nur die Oberfläche.
- ❄️ **Kaltstart: den Reaktor selbst hochfahren.** Neue Option auf dem Startbildschirm ("Kalt starten", nur freies Spiel) -- Kern steht mit allen Stabbänken voll eingefahren spürbar unterkritisch (DWR ca. −3800 pcm, SWR ca. −3100 pcm, RBMK ca. −1600 pcm), Leistung bei 0. Kritisch werden und hochfahren ist jetzt selbst zu tun: Stäbe ziehen (und beim DWR zusätzlich verdünnen), Periode beobachten, bei Erreichen der Kritikalität rechtzeitig bremsen.
  Kein Skript, echte Physik: an der Engine nachgemessen läuft der Übergang genau wie erwartet -- Periode wird mit dem Ziehen kürzer und kürzer, bei Kritikalität beginnt die Leistung zu steigen, alles ohne Fehler oder Kernschaden bei sachgemäßer Bedienung.
  Kleinere Fundsache beim Bauen: der SWR wurde mit voll eingefahrenen Stäben trotzdem leicht ÜBERkritisch, weil der Dampfblasenanteil bei Nullleistung auf null fällt und der (auf Volllast-Blasenanteil kalibrierte) Rückkopplungsterm das als kräftig positive Reaktivität liest ("Blasenkollaps") -- derselbe Effekt, den ein Kommentar im Code schon aus dem Volllast-Hochfahren kennt ("startete fast zwei Dollar überkritisch"), hier nur ohne den rettenden Leistungsanstieg direkt danach. Für den Kaltstart wird der Rückkopplungswert deshalb auf den Referenzwert zurückgesetzt.

## 0.0.39

- ⏩ **Jodgrube durchstehen, ohne 24 echte Minuten zu warten.** Neuer Knopf "Zeit vorspulen, bis Xenon abgeklungen" -- erscheint nur im freien Spiel, nur bei abgeschalteter Anlage (SCRAM) mit noch spürbar erhöhtem Xenon. Läuft dieselben Schritte wie der normale Betrieb (Engine + Sitzung je 0,05 s), nur ohne Bildaufbau dazwischen -- ein echter Störfall währenddessen bricht sofort ab und zeigt sich normal, statt still überfahren zu werden. In Blöcken mit Fortschrittsanzeige, damit der Tab nicht einfriert.
  Ziel ist die Rückkehr auf den Vollastwert (X* = 1), nicht auf nahe null -- an der echten Engine nachgemessen: Xenon steigt nach dem Abschalten erst noch rund 8h (Jodgrube), fällt dann und ist nach rund 27h wieder auf Vollastniveau. Nahe an den oft für den RBMK genannten "24 Stunden".

## 0.0.38

- 📈 **Freies Spiel: Netzanforderung wandert jetzt.** Bisher stand `P_demand` im freien Spiel fest auf dem Startwert und änderte sich nie von selbst -- "folge der Netzanforderung" war ohne Szenario nur Kosmetik in der Anleitung, es gab schlicht nichts zu folgen. Jetzt ein Zufallsspaziergang wie ein echter Netzbetreiber: alle 5–15 Minuten ein neues Ziel zwischen 50 % und 100 % Nennleistung, dahin geht es sanft (max. 0,2 %/s Nennleistung), nie sprunghaft. Neu gesät bei jedem Rundenstart -- keine feste Wiederholung wie bei einem Szenario, hier zählt keine Wertung. Die Regler-Zeile "Anforderung" zeigt weiterhin nur an, sie wird jetzt wie in Szenarien vom Spiel geführt statt vom Schieberegler.

## 0.0.37

- ⚡ **Kopfzeilen-Auswahl wirkt jetzt sofort.** Statt beim Speichern nur den Server zu aktualisieren und auf den nächsten Rundenstart zu warten, wechselt die laufende Kopfzeile sofort um -- ohne die zugrundeliegenden Knoten neu zu bauen (nur `hidden`/Reihenfolge), bleiben die Wertebindungen aus dem laufenden `buildPanels()` gültig.
- 💾 **Ein Spielstand-Slot je Reaktortyp statt einem gemeinsamen.** Vorher überschrieb "Speichern" beim SWR denselben Stand wie beim DWR (ein einziger Slot `auto`). Jetzt eigener Slot je Typ (`auto-pwr`/`auto-bwr`/`auto-rbmk`) -- ältere Stände im alten Slot `auto` sind darüber nicht mehr erreichbar. Der Startbildschirm zeigt jetzt für jeden gefundenen Stand einen eigenen "Fortsetzen"-Knopf mit Reaktortyp, Szenario (oder "Freies Spiel") und Speicherzeitpunkt im Text, statt nur einen namenlosen Knopf.

## 0.0.36

- ⚙️ **Kopfzeile frei anpassbar.** Welche Werte oben in der Statuszeile stehen, wählt man jetzt selbst (⚙-Knopf neben dem Fragezeichen) aus einem Katalog von 44 Werten -- alles, was auch in den Panels steht (Xenon, Bor, Abschaltreserve, Void-Koeffizient, …), nicht nur die bisherigen fest verdrahteten neun. Auswahl gilt je Reaktortyp getrennt und bleibt dauerhaft beim Spieler gespeichert (`/api/prefs`, eigene Datei je Spieler unter `/data/players/`), wirkt ab dem nächsten Rundenstart. Per Playwright-Livetest verifiziert: Auswahl übersteht Neustart und Menü-Rückkehr, bleibt zwischen Reaktortypen getrennt, taucht nicht in der Spielstand-Liste auf.

## 0.0.35

- 🐛 **SWR und RBMK: Dampferzeugerdruck/-füllstand zeigten dauerhaft "—".** Jeder Reaktortyp legt diese Werte intern unter eigenem Namen ab (SWR: `p_dome`/`L_rpv`, RBMK: `p_drum`/`L_drum`) und stellt sie im abgeleiteten Zustand unter dem gemeinsamen Namen `p_sg`/`L_sg` bereit — genau dafür gibt es diese Ebene. Die Anzeige (Rundinstrumente, Textzeile, Trendschreiber) griff aber direkt auf den rohen Zustand zu, wo dieser Name bei SWR und RBMK nie existiert. Nur beim DWR ging es zufällig gut, weil er selbst so heißt. Gefunden per Playwright-Livetest.

## 0.0.34

- ☢️ **Notkondensator jetzt im Fließbild.** Seit 0.0.29 real simuliert (Naturumlauf, Fukushima-Physik), stand aber nur als Textzeile im Sekundärkreis-Panel — im Anlagenfließbild fehlte er ganz. Jetzt eigene Schleife am Behälterkopf mit Isolierventil (auf/zu per Zustand) und Vorratsanzeige.
- 🔲 **Meldetafel-Kacheln überarbeitet.** Symbol lag per `position:absolute` über der Kachel und überlappte bei kurzen, einzeiligen Meldungen ("Leistung hoch") die erste Textzeile statt sauber daneben zu stehen — betraf Handy, Desktop und das neue Fenster gleichermaßen. Jetzt eigene Zeile über dem Text, dazu größere Kacheln (58px statt 46px, Schrift 11px statt 10px, breitere Spalten).

## 0.0.33

- 🖥️ **Kachel als Fenster.** Klick auf die Kopfzeile einer Kachel (Reaktorkern, Primärkreis, …) hebt sie als großes Fenster über den ganzen Leitstand — kein Freischrollen oder seitliches Scrollen in engen Spalten mehr nötig, um z.B. alle drei Rundinstrumente im Kern-Panel zu sehen. Verschiebt den echten `rs-panel-body`-Knoten (nicht geklont), daher bleiben alle Anzeigen live und alle Knöpfe bedienbar. Das gewohnte Raster samt Scrollen bleibt unverändert bestehen — das Fenster ist nur zusätzlich obendrauf. Esc, ein Klick daneben oder "Schließen" beenden es wieder. Nur auf dem Desktop-Raster aktiv (ab 1024px); auf dem Handy zeigt der Reiter das Panel schon voll, dort bleibt der Klick wirkungslos.

## 0.0.32

- 🐛 **`manifest.json`: "Syntax error" in der Konsole.** Der Browser holt eine Web-App-Manifest-Datei standardmäßig ohne Cookies — landete auf der Anmeldeseite (`/s/...` braucht eine Sitzung wie alles andere), bekam HTML statt JSON zurück und meldete einen Parsefehler beim ersten Zeichen. Rein kosmetisch (betraf nur "Zum Startbildschirm hinzufügen", nicht das Spiel selbst), aber seit 0.0.21 in der Konsole. `crossorigin="use-credentials"` am Manifest-Link behoben.

## 0.0.31

- 📊 **Sicherheitsbehälterdruck bekommt ein Rundinstrument.** Stand bisher nur als kleine Textzeile unter "Sicherheitssysteme" — jetzt ein Instrument im Sekundärkreis-Panel wie jeder andere überwachte Druck, nur beim Siedewasserreaktor (`sp.containment` existiert ausschließlich dort).
- 💡 **Ereignisprotokoll ist jetzt klickbar**, genau wie die Meldetafel-Kacheln: ein Eintrag öffnet dieselbe Erklärung, wenn eine existiert (Meldungen teilen sich die `_help`-Texte mit der Meldetafel). Für Ereignisse ohne eigene Erklärung (SCRAM ausgelöst, Frischdampf abgesperrt, …) ein Hinweistext statt eines nackten, unübersetzten Schlüsselnamens im Fenster.

## 0.0.30

- 🐛 **Rundinstrumente verdoppelten sich nach einem Neustart.** Kern-, Primär- und Sekundärkreis-Panel hängten ihre Instrumente bei jedem `buildPanels()`-Aufruf nur an, ohne den Behälter vorher zu leeren — anders als überall sonst im Leitstand. Nach "Neustart" (0.0.20) oder einer neuen Partie blieben die alten Instrumente als Leichen im DOM stehen, für immer auf "—" eingefroren, während die neuen daneben live liefen. Jetzt wird jeder der drei Behälter vor dem Befüllen geleert.

## 0.0.29

- ☢️ **Fukushima-1-Szenario, mit echter neuer Physik statt reiner Datendatei.** Bisher konnte kein Reaktortyp durch reinen Kühlungsverlust nach der Abschaltung schmelzen — Zerstörung ging immer nur über einen Leistungsausflug. Für den Siedewasserreaktor jetzt vier neue, dauerhafte Systeme:
  - **Notkondensator (Isolation Condenser).** Reiner Naturumlauf-Wärmetauscher, schaltet sich bei Isolierung (SCRAM + geschlossene Frischdampf-Absperrung) automatisch zu. Die Ventile sind fail-safe ZU ausgelegt — fehlt der Gleichstrom, fallen sie in ihre sichere Stellung, unbemerkt, weil dieselbe Störung auch die Anzeige einfrieren lässt. Genau die Fehlerkette von Fukushima-1, 2011.
  - **Kernfreilegung.** Sinkt der Füllstand unter die obere Kernkante, bricht die Kühlung ein — reine Nachzerfallswärme reicht jetzt aus, um die Hüllrohrgrenze und danach die Brennstoff-Zerstörungsgrenze zu reißen, ganz ohne Reaktivitätsausflug. Per Kopfsimulation geprüft: unbedient Kernschaden nach rund drei Stunden, Löschwassereinspeisung bis ~100 Minuten nach Stromausfall rettet den Kern noch, ab ~150 Minuten ist es zu spät.
  - **Löschwassereinspeisung.** Einziges Wasser, das auch im vollständigen Stromausfall noch fließt — kein Motor, keine Elektronik.
  - **Sicherheitsbehälter mit Venten und Wasserstoff.** Sicherheitsventil-Dampf baut Behälterdruck auf; kontrolliertes Venten verhindert ein Versagen, setzt aber radioaktives Gas frei. Oberhalb 1200 °C Hüllrohrtemperatur entsteht Wasserstoff aus der Zirkon-Wasser-Reaktion — spätes Venten bei hohem Wasserstoffstand kann zur Explosion im Reaktorgebäude führen, wie 2011.
  - `sanitize()`-Grenzen für Kühlmitteltemperatur von 1000 K auf 4000 K angehoben — die alte Grenze klemmte die neue Dampfkühlung bei Kernfreilegung fälschlich als „Rechenfehler".
  - Neues Panel „Sicherheitssysteme" mit drei neuen Reglern, drei neuen Anzeigewerten, zwei neuen Meldungen.

## 0.0.28

- 📖 **Meldetafel-Hilfe komplett neu geschrieben, alle 28 Meldungen.** Die Kurzfassung aus 0.0.17 sagte nur, was passiert — nicht mehr, was konkret zu tun ist. Jeder Text hat jetzt die genaue Auslösebedingung mit Zahlen, dann eine Schritt-für-Schritt-Liste mit den tatsächlichen Reglernamen aus dem Leitstand ("Hauptumwälzpumpen", "Druckhalter-Sprühen", "Frischdampf-Absperrung" usw.) statt allgemeiner Stichworte. Modal zeigt jetzt mehrzeilig mit Aufzählungspunkten (`white-space: pre-line`), etwas breiter für den längeren Text.

## 0.0.27

- 💡 **Fließbild zeigt jetzt, welches Bauteil eine anstehende Meldung betrifft.** Bisher stand das nur auf der Meldetafel — jetzt bekommt das betroffene Bauteil (Kern, Druckhalter/Dampferzeuger/Trommel, Hauptkühlmittelpumpe, Generator, je nach Typ) einen farbigen Rand in derselben Schwere-Farbe wie die Meldetafel, bei Auslösung zusätzlich blinkend. Neues Feld `alarmComponents` je Typdatei ordnet jede Meldung ihrem Bauteil zu.

## 0.0.26

- 🐛 **Druck-Rundinstrument stand bei Siedewasserreaktor und RBMK dauerhaft im Roten.** Die Skala war fest auf den Druckwasserreaktor zugeschnitten (100-180 bar, Normalbereich 140-168) — Siedewasserreaktor (Domdruck, Nennwert 70,7 bar) und RBMK (Trommeldruck, 69 bar) liegen mit ihrem gesamten Normalbetrieb unterhalb der Skala, die Nadel klebte deshalb immer am unteren Anschlag im roten Bereich, selbst bei sauberstem Volllastbetrieb. Skala kommt jetzt aus der Typdatei (`pressureGauge`): DWR unverändert, SWR 40-90 bar (Normalbereich 58-76), RBMK 40-85 bar (Normalbereich 55-73) — beide mit Auslösewert als Randbedingung der roten Zone.

## 0.0.25

- 🐛 **"Generator"-Beschriftung im Fließbild lief über den Bildrand.** Der Text stand seit jeher linksbündig ab x=470 in einer 520 breit angelegten Zeichenfläche — bei "Generator" reicht das bis etwa x=525, fünf Einheiten über den Rand. Solange der Anzeigebereich breiter als das Fließbild-Seitenverhältnis war, blieb das durch den Leerraum links/rechts der Zeichnung unsichtbar; passte die Fläche genau in der Breite (schmalerer Bildschirm, schmaleres Panel), schnitt die SVG selbst den Überstand ab. Jetzt rechtsbündig mit Rand vor dem Zeichenflächenrand, bei allen drei Reaktortypen — verschwindet bei keiner Fenstergröße mehr, weil nichts mehr über die deklarierte Fläche hinaus gezeichnet wird.

## 0.0.24

- 🐛 **Turbine blieb nach einem Schnellschluss für immer vom Netz.** `s.turbineTripped` und der Turbinenregler (`govCtl.trip()`) wurden nirgends zurückgesetzt — weder nach einem Turbinenschnellschluss durch SCRAM noch nach der eigenständigen Störung `turbine_trip`/`loss_of_load`. Der Generator blieb für den Rest des Laufs bei 0 MW, ganz gleich wie stabil der Reaktor stand. Neuer Knopf **"Turbine zuschalten"** im Netz-Panel (nur aktiv, wenn wirklich etwas zu tun ist) — gesperrt, solange der Reaktorschutz noch steht, genau wie beim Reaktorschutz selbst (0.0.18).

## 0.0.23

- 🔊 **Anlagengeräusche statt Gepiepse.** Die Meldehupe war ein einzelner Rechteck-Ton auf einer Frequenz — jetzt zwei leicht verstimmte Sägezahn-Oszillatoren durchs Tiefpassfilter, die gegeneinander schweben, wie eine echte elektromagnetische Hupe. TRIP-Meldungen bekommen die höhere, dringlichere Stimme.
- 💥 **SCRAM hat jetzt ein Geräusch:** tiefer Schlag (Relais/Magnetventil), ein kurzer metallischer Klack, danach abklingendes Zischen (Dampf/Druckluft) — alles aus Oszillator und gefiltertem Rauschen, keine Datei.
- ☢️ **Kernzerstörung hat jetzt ein Geräusch:** ein Knall aus breitbandigem Rauschen, darunter mehrere Sekunden tiefes Grollen. Vorher stumm.
- Weiterhin keine Audiodatei im Spiel — alles synthetisiert über die Web Audio API, wie schon die alte Hupe.

## 0.0.22

- 🐛 **Neustart zeigte sofort wieder "Kernzerstörung".** Der Knopf aus 0.0.20 stoppte die alte Spielschleife nie -- sie lief pausiert weiter, sah beim nächsten Bild noch `destroyed` vom alten Lauf zusammen mit dem eben erst zurückgesetzten `endShown` und zeigte den Dialog erneut, jetzt mit den Werten der frischen Anlage. `boot()` stoppt jetzt zuerst jede laufende Schleife, bevor eine neue entsteht.
- 📊 **Statuszeile: Marge und Brennstofftemperatur** sind jetzt immer sichtbar, nicht nur im jeweiligen Tab -- die zwei Werte, die tatsächlich über einen Kernschaden entscheiden, standen bisher nur im Panel des laufenden Reiters.
- 🎨 **Therm. Leistung und Generator färben sich jetzt nach Zustand** statt fest verdrahtet Blau zu bleiben: Leistung ab 100 % gelb, ab 110 % rot; Generator gelb ohne Netzschalter bei anstehender Anforderung, rot bei abgeworfener Turbine.
- 🎯 **Zwei neue Extremszenarien.** *Klemmendes Abblaseventil* (DWR, Seed 1979 — Three Mile Island): Druck und Füllstand fallen langsam, die Meldetafel warnt früh, wer sie überhört verliert DNBR. *Dichtewellen-Instabilität* (SWR, Seed 1988 — LaSalle): Umwälzstrom bricht ein, wer die Leistung trotzdem mit den Stäben nachzieht statt zuerst den Durchsatz wiederherzustellen, treibt den Kern in die gesperrte Ecke des Kennfelds. Beide per Kopfsimulation geprüft: unbedient gefährlich, rechtzeitiges Eingreifen rettet den Kern.

## 0.0.21

- 🖼️ **Logo und Icons.** ReactorSim war bisher komplett unbebrandet — kein Favicon, kein Icon, ein leerer Tab. Jetzt Favicon (ICO + PNG), Apple-Touch-Icon, ein Icon-Badge auf dem Startbildschirm und ein Web-Manifest für "Zum Startbildschirm hinzufügen". Die Anmeldeseite bekommt bewusst kein Favicon — sie darf laut eigenem Kommentar keine Datei nachladen, die hinter derselben Anmeldung liegt.
- 📄 README bekommt ein Logo oben.

## 0.0.20

- ✏️ **Meldetafel-Hilfe an das manuelle SCRAM angepasst.** Alle Hilfetexte von 0.0.17 gingen noch von automatischer Abschaltung aus ("SCRAM ist bereits ausgelöst"). Seit 0.0.19 stimmt das nicht mehr — jeder betroffene Text sagt jetzt "SCRAM auslösen" statt eine bereits erledigte Sache zu behaupten.
- 🔺 **Meldetafel-Schwere jetzt auch als Form, nicht nur als Farbe.** ● Hinweis, ▲ Warnung, ■ Auslösung — für Rot-Grün-Schwäche war Warnung gegen Auslösung bisher nicht zu unterscheiden.
- ⌨️ **Steuerstäbe fahren jetzt auch über die Tastatur.** Die Halteknöpfe reagierten bisher nur auf Maus/Touch (`pointerdown`/`up`), Tab+Enter/Leertaste tat nichts. Dazu Pointer Capture, damit ein Loslassen neben dem Knopf den Fahrbefehl nicht unbemerkt weiterlaufen lässt.
- 🔁 **Neustart-Knopf** in Auswertung und Kernzerstörung — gleicher Typ, gleiches Szenario, sofort von vorn, ohne den Umweg über Menü und Einweisung.
- 📖 **Grundlagen-Glossar** über den neuen „?"-Knopf im Leitstand: 13 Begriffe kurz erklärt (Reaktivität, DNBR/CPR, Xenon, ORM, Void-Koeffizient, SCRAM/RESA/AZ-5, Meldetafel-Zustände, …) — kein Lehrgang, nur zum Nachschlagen.
- 🧹 Zwei tote Übersetzungsschlüssel entfernt (`start_scenarios_soon`, `start_difficulty`) — Reste eines nie gebauten Reglers, nirgends mehr referenziert.
- 🖼️ **RBMK-Fließbild: Abschaltreserve statt Graphittemperatur am Kern.** Die Graphittemperatur hat eine Zeitkonstante von 35 Minuten — über eine Schicht sieht sie praktisch unbewegt aus, und stand dazu direkt unter der Beschriftung "Druckröhren", als gehörte sie dazu. Am selben Fleck steht jetzt die ORM, selbst beschriftet ("ORM …") und rot/gelb bei Unterschreitung — die Zahl, die bei diesem Typ tatsächlich in Echtzeit über Gefahr entscheidet.

## 0.0.19

- ⚠️ **Schnellabschaltung löst nicht mehr von selbst aus.** Bisher schaltete jede Meldung mit `action: 'scram'` (Leistung hoch, DNBR niedrig, Kühlmittelverlust, …) den Reaktor automatisch ab — der Bediener bekam davon oft nur die Meldetafel zu sehen. Jetzt meldet das System weiterhin zuverlässig (Kachel, Hupe, Protokoll), greift aber nicht mehr ein: die Schnellabschaltung ist allein Sache des Bedieners am SCRAM/RESA/AZ-5-Knopf. Wer nicht reagiert, riskiert jetzt echten Brennstoffschaden — bei allen drei Reaktortypen.

## 0.0.18

- 🐛 **Reaktorschutz saß nach einer Schnellabschaltung für immer fest.** Einmal ausgelöst — auch automatisch, etwa durch „Leistung hoch" — fuhr die Engine die Stäbe für den Rest des Laufs zwangsweise auf „ganz eingefahren", ganz gleich was der Bediener einstellte: kein Zurück in den Normalbetrieb, alle drei Reaktortypen betroffen. „Rückstellen" gibt den Reaktorschutz jetzt frei — aber erst, wenn die auslösende Ursache tatsächlich weg ist, sonst bleibt er stehen, genau wie die Meldetafel selbst.

## 0.0.17

- 💡 **Meldetafel erklärt sich jetzt.** Eine Kachel sagte bisher nur, dass etwas ansteht — nicht, was es bedeutet oder was zu tun ist. Klick (oder Enter/Leertaste) auf eine Meldung öffnet eine kurze Erklärung mit der empfohlenen Handlung, auf Deutsch und Englisch.

## 0.0.16

- 🔧 **Generator-Beschriftung lag auf der Turbine und dem Abdampfrohr.** Text und Messwert standen zentriert über/unter dem Generatorkreis — geometrisch genau in der Spalte, in der die Turbinenkontur endet und das Abdampfrohr senkrecht nach unten läuft. Jetzt steht beides seitlich rechts vom Generator, frei von beiden.

## 0.0.15

- 🎛️ **„Hand" hat jetzt auch einen Hebel.** Bisher gab es nur den Umschalter: der Regler hörte auf zu regeln, und der Spieler hatte trotzdem nichts, womit er stellen konnte. Beim Speisewasser war es sogar schädlich — der Handwert stand auf Volllast, beim Druckhalter auf „Heizung aus". Jetzt ist jede Betriebsart eine **Regelstation**: Umschalter plus Stellschieber, der in Automatik mitläuft und in Hand dem Bediener gehört.
- 🤝 **Stoßfreie Übernahme.** Wer auf Hand schaltet, übernimmt genau den Wert, der gerade steht — nichts springt. Ein Regler, bei dem schon das Umschalten eine Störung auslöst, wird nie benutzt, und dann ist die Handbedienung wertlos, obwohl sie da ist.
- 🔧 **Stationen je Typ:** Regelventil und Speisewasser bei allen dreien, dazu Druckhalter-Heizung und -Sprühen beim Druckwasserreaktor.
- 🎚️ **Der Schalter „Stabregelung" zeigt endlich auf den Regler, der die Stäbe wirklich führt.** Beim Druckwasserreaktor die Temperaturregelung, beim RBMK der Leistungsregler — dort heißt der Schalter jetzt auch so. Beim Siedewasserreaktor führt gar keiner die Stäbe, also gibt es dort auch keinen Schalter mehr: das Stellglied ist der Umwälzstrom.
- 📝 Unter jeder Station steht in einem Satz, was Handbetrieb dort bedeutet.

## 0.0.14

- 🎚️ **Automatik/Hand als Zweifeld-Umschalter statt als Einzelknopf.** Vorher trug ein Knopf seinen eigenen Zustand als Aufschrift — „Turbinenregler [Hand]" liest sich aber wie ein Angebot, auf Hand zu schalten, und nicht wie die Feststellung, dass er längst darauf steht. Jetzt stehen beide Felder nebeneinander, das geltende ist hervorgehoben: Automatik grün, Hand bernstein. In einer Leitwarte muss auf einen Blick sichtbar sein, was gilt — nicht, was passieren würde.

## 0.0.13

- 🔐 **Anmeldung.** Die Seite stand bisher offen — wer die Adresse kannte, war drin. Jetzt ein Konto, Benutzername und Passwort aus `REACTORSIM_USER` und `REACTORSIM_PASSWORD`, also aus der Dockge-Konfiguration. Mehrbenutzerbetrieb folgt später.
- 🛡️ **Ohne gesetztes Passwort steht die Seite trotzdem nicht offen.** Fehlt `REACTORSIM_PASSWORD`, erzeugt ReactorSim beim ersten Start ein zufälliges, schreibt es **einmal** ins Protokoll und legt nur den scrypt-Hash in `./data/auth.json` ab (Rechte 0600). Ein Dienst im Internet, der auf ein gesetztes Passwort hofft, ist ein Dienst ohne Passwort.
- 🚪 **Geschützt ist alles außer zwei Pfaden.** `/health` bleibt offen, sonst meldet Docker den Container dauerhaft als krank; `/login` kann nicht hinter der Anmeldung liegen. Alles andere — Seite, Statics, gesamte JSON-Schnittstelle — braucht eine Sitzung. Ein Test geht die Liste durch, damit kein neuer Pfad versehentlich offen bleibt.
- 🍪 **Sitzung als signiertes Token** (itsdangerous) in einem HttpOnly-Cookie mit SameSite=Lax, 30 Tage gültig, `secure` sobald über HTTPS aufgerufen. Der Signierschlüssel liegt in `./data/secret.key` — dadurch überlebt die Anmeldung einen Neustart des Containers.
- 🚧 **Gegen Durchprobieren** zehn Versuche je Minute und Absenderadresse. Das Passwort wird auch bei falschem Benutzernamen geprüft, sonst verrät die Antwortzeit, welcher Name existiert. Das Anmeldeformular trägt ein CSRF-Token, und `?next=` akzeptiert nur anwendungseigene Pfade — eine Anmeldeseite, die Besucher auf fremde Seiten weiterleitet, wäre eine offene Weiterleitung.
- 🔁 **Abgelaufene Sitzung wird sichtbar.** Antwortet die Schnittstelle mit 401, springt der Browser auf die Anmeldeseite, statt still nichts mehr zu speichern.
- ✅ **88 Tests** — 74 unter `node --test`, 54 unter `pytest` (davon 14 neu für den Zugang).

## 0.0.12

- 🔤 **Beschriftung der Rundinstrumente steht jetzt über dem Zifferblatt statt darauf.** Vorher lief der Schriftzug mitten durch den oberen Bogen, und lange Bezeichnungen wurden abgeschnitten — „Unterkühlungsspanne" passt bei 108 Pixeln Instrumentenbreite in keine Zeile. Sie darf nun zweizeilig umbrechen, und alle Instrumente einer Reihe beginnen trotzdem auf gleicher Höhe.
- 🧹 **Jeder Reaktortyp zeigt nur noch seine eigenen Messwerte.** Die Panels tragen die Zeilen aller drei Typen, weil sie fest im Template stehen — ein Druckwasserreaktor zeigte deshalb Abschaltreserve, Void-Koeffizient und Graphittemperatur als Striche. Sieben leere Zeilen sehen nach kaputter Anzeige aus, nicht nach „gibt es hier nicht".
- 📏 **CPR statt DNBR bei den siedenden Kernen.** Der Abstand zur Siedekrise heißt beim Druckwasserreaktor DNBR, bei Siedewasserreaktor und RBMK aber CPR — im Kern siedet es dort ohnehin überall, gefragt ist, wie viel Leistung bis zur Austrocknung fehlt. Wie schon bei RESA/SCRAM/AZ-5 steht der Name in der Typdatei.

## 0.0.11

- 🐛 **Siedewasserreaktor und RBMK sahen aus wie Vorschau, obwohl sie fertig sind.** Die Klasse zum Ausgrauen stand fest im Template — aus der Zeit, als nur der Druckwasserreaktor gebaut war. Beide waren tatsächlich anklickbar und voll spielbar, sie sahen nur nicht so aus. Das Ausgrauen entscheidet jetzt dieselbe Stelle, die auch prüft, ob ein Typ überhaupt spielbar ist.

## 0.0.10

- 🔴 **Die Schnellabschaltung heißt jetzt, wie sie im jeweiligen Leitstand heißt.** Im deutschen **RESA**, im englischen **SCRAM**, beim RBMK in beiden Sprachen **AZ-5** — Notschutz fünfter Kategorie. „SCRAM" pauschal über alle drei Typen zu schreiben war amerikanisch für zwei Anlagen, die es nie so genannt hätten, und schlicht falsch für die dritte. Der Name gehört zum Reaktortyp, nicht zum Knopf: er steht in der Typdatei und wird von dort gezogen.
- 💬 Dazu ein Hinweistext beim Überfahren, der sagt, was passiert — inklusive der achtzehn Sekunden und der Graphitspitzen beim RBMK.

## 0.0.9

- 💾 **Speichern und Fortsetzen.** Ein Knopf in der Statuszeile legt den Stand ab, der Startbildschirm bietet ihn beim nächsten Mal zum Fortsetzen an. Der Stand wird erst angewandt, wenn die Anlage steht — Regler und Pumpen schwingen sich dann aus dem geladenen Zustand von selbst ein, statt mit fremden Integralständen weiterzulaufen.

## 0.0.8

- 💾 **Spielstände und Bestenliste.** Ablage unter `./data`, ohne Anmeldung: ein zufälliges Token im Cookie erkennt das Gerät wieder, mehr wird nicht gespeichert. Nach jeder Schicht lässt sich das Ergebnis mit einem Namen eintragen; die Bestenliste zum Szenario steht direkt darunter.
- 🔒 **Der Server glaubt dem Browser den Punktestand nicht.** Der Client meldet Kennzahlen, der Server rechnet daraus mit derselben Formel neu. Ein mitgeschicktes `score`-Feld wird gar nicht gelesen. Die Formel steht deshalb zweimal — in JavaScript und in Python — und eine gemeinsame Fixture-Datei hält beide Seiten zusammen.
- 🧱 **Plausibilitätsprüfung statt blindem Vertrauen.** Mehr Energie, als die Anlage in der Zeit liefern kann, eine längere Schicht als das Szenario dauert, negative Abweichungen, Überschreitungszeiten länger als der Lauf — alles abgewiesen. Reaktortyp und Szenario müssen zueinander passen und beide aus der serverseitigen Liste stammen.
- 🚧 **Ratenbegrenzung in zwei Stufen.** Oben eine weite Grenze gegen das bloße Fluten, die enge Grenze (ein Eintrag je Minute) erst kurz vor dem Schreiben. Stünde sie oben, würde eine einzige fehlerhafte Anfrage den nächsten gültigen Eintrag für eine Minute blockieren. Gezählt wird je Spieler **und** je Absenderadresse — ProxyFix ist aktiv, sonst teilen sich hinter einem Reverse Proxy alle dieselbe Grenze.
- 📦 **Der Spielstand ist für den Server undurchsichtig.** Er speichert ihn und gibt ihn zurück, ohne hineinzusehen: die Struktur gehört der Simulation, und eine Prüfung im Server wäre eine zweite, stets veraltete Kopie davon. Geprüft wird beim Laden im Browser — ein kaputter Stand wird verweigert, statt NaN in die Engine zu füttern.
- 🧪 **Struktur- und Sprachtests.** Ein Test läuft den ES-Modul-Importgraph ab `main.js` ab und prüft jede erreichte Datei gegen die COPY-Zeilen des Dockerfiles: ein vergessenes Modul stürzt nicht ab, es liefert still 404 und eine halbtote Oberfläche. Ein zweiter prüft Schlüsselgleichheit und Platzhalter beider Sprachdateien und sucht nach fest verdrahtetem deutschem Text außerhalb von Kommentaren.
- ✅ **104 Tests** — 74 unter `node --test`, 30 unter `pytest`.

## 0.0.7

- 📋 **Szenarien statt nur freiem Spiel.** Fünf Schichten zur Auswahl: Lastfolge und Turbinenschnellschluss am Druckwasserreaktor, Lastfolge über den Umwälzstrom und Frischdampf-Absperrung am Siedewasserreaktor, Nachtschicht am RBMK. Jedes Szenario bringt eine Bedarfskurve, geplante Störungen, Ziele und Fehlbedingungen mit — als Datendatei, nicht als Code.
- 🎲 **Störungszeitpunkte sind gesät, nicht zufällig.** `"rand(6000,8400)"` wird über den Startwert des Szenarios aufgelöst. Derselbe Startwert ergibt dieselbe Schicht — sonst gäbe es keine Wiederholbarkeit und keinen Regressionstest.
- 💣 **Störungsbibliothek.** Eine Störung fasst den Zustand an und sonst nichts: eine ausgefallene Pumpe ist eine ausgefallene Pumpe, der Rest folgt aus der Physik. Klemmende Stabgruppe, klemmendes Abblaseventil, Dampferzeuger-Rohrleck, Speisewasserausfall, unkontrollierte Bor-Verdünnung, Frischdampf-Absperrung, Pumpenausfälle, abgeschalteter Leistungsregler, Turbinenschnellschluss, Netzabwurf.
- 🏁 **Einweisung und Auswertung.** Vor der Schicht steht, worum es geht; danach die Punkte mit ihrer Aufschlüsselung. Gewertet werden gelieferte Energie, Abweichung vom Bedarf, unquittierte Alarmsekunden, Grenzwertüberschreitungen nach Schwere, Schnellabschaltungen und Brennstoffschaden.
- ⏱️ **Die Spielschicht sieht jeden Rechenschritt, nicht jedes Bild.** Eine Störung, die auf Sekunde 1200 fällt, darf bei 60-fachem Zeitraffer nicht zwischen zwei Bildern verschwinden.
- ✅ **74 Tests.** Darunter: jedes Szenario läuft unbedient bis zum Ende durch, ohne Ausnahme und ohne ungültigen Zustand; jeder Szenariotext existiert in beiden Sprachen; die Wertungsformel liegt als Fixture-Datei fest, die später auch die Python-Seite prüft.

## 0.0.6

- ☢️ **Der RBMK-1000 ist spielbar.** Graphitmoderiert, Druckröhren, Trommelabscheider, acht Hauptumwälzpumpen. Alle drei Reaktortypen sind damit verfügbar.
- ➕ **Positiver Dampfblasenkoeffizient, abhängig von der Abschaltreserve.** Bei nominal 46 eingefahrenen Stäben sind es +20 pcm je Prozentpunkt Blasenanteil, bei leerem Kern über +60. Die Abschaltreserve ist damit kein Anzeigewert, sondern der Parameter, der den gefährlichsten Kennwert der Anlage einstellt.
- 🔻 **Die Vorgeschichte fährt sich von selbst.** Leistung absenken, warten: Xenon baut auf, der Leistungsregler zieht die Stäbe, die Abschaltreserve schmilzt von 58 auf unter 15 — in gut vierzig Minuten. Nichts daran ist gescriptet; es fällt aus denselben Gleichungen wie der Normalbetrieb.
- 💥 **AZ-5 mit Graphitspitzen, in beide Richtungen.** Bei niedriger Abschaltreserve fügt die Schnellabschaltung **positive** Reaktivität ein: die Einfuhr erreicht 1,7 β, die Leistung steigt in zweieinhalb Sekunden auf das Achthundertfache, der Brennstoff zerlegt sich. Aus dem Nennbetrieb dagegen ist dieselbe Schnellabschaltung durchweg negativ und schaltet sauber ab. Beides muss stimmen — sonst wäre es ein Zwischenfilm mit Physik-Anstrich, und ein Test hält genau das fest.
- 🧮 **Der Absorber wird während des Verdrängerwegs herausgerechnet.** Der allgemeine Stabbeitrag zählt ihn vom ersten Zentimeter an mit, weil er nichts von Graphitverdrängern weiß. Ohne diese Verrechnung standen +350 pcm Graphit gegen −830 pcm Absorber, und die Eigenheit, um die es bei diesem Reaktortyp geht, hätte es im Spiel nicht gegeben.
- 🔁 **Axiale Xenon-Schwingung** aus zwei Zonen mit eigener Vergiftung. Sie wandert über gut einen Tag hin und her, statt wegzulaufen — die erste Auslegung der Steifigkeit hatte eine Schleifenverstärkung über eins, und das Flussprofil kippte binnen zwei Stunden ganz nach unten.
- ⚙️ **Leistungsregler auf die Stäbe.** Wo der Kern selbst die Leistung macht, braucht es einen Regler, der direkt darauf geht. Ohne ihn trieb allein der Xenon-Abbrand die Anlage in drei Stunden über die Leistungsauslösung — ein Reaktor mit schwachem Leistungskoeffizienten hat keinen Grund, von selbst auf seinem Arbeitspunkt zu bleiben.
- 🔧 **Ein Fehler, der alle drei Typen betraf:** der Druckregler des Turbinenventils konnte nie unter 30 % schließen, weil er sich dieselbe schmale Stellgrenze mit dem Lastregler teilte. Bei kleiner Leistung lief die Anlage dadurch leer — der Trommeldruck fiel von 69 auf 12 bar, und der Blasenanteil im Kern stieg, obwohl die Leistung sank.
- 🩹 **Zweites Versagenskriterium für den Brennstoff.** 963 J/g gilt für die heißeste Tablette; unser Modell führt einen Knoten für den ganzen Kern. Dazu kommt deshalb der Enthalpie-Zuwachs gegenüber dem Betriebszustand — das Kriterium, das bei einer schnellen Exkursion tatsächlich zuerst greift.
- 🖼️ **Eigenes Fließbild** mit Graphitblock, Druckröhren, Trommelabscheider und innerer Umwälzschleife. Der Block glüht mit der Graphittemperatur, die ihrer eigenen halben Stunde Zeitkonstante folgt.
- ✅ **65 Tests.**

## 0.0.5

- ⚛️ **Der Siedewasserreaktor ist spielbar.** 3840 MWth / 1344 MWe, ein Kreislauf, Dampf direkt zur Turbine. Das Regelventil hält den Domdruck, die Leistung macht der Kern — über den Umwälzstrom. Zwischen 100 und 80 % Durchsatz liegen 11 % Leistung, ohne dass ein Stab sich bewegt.
- 🌀 **Dichtewelleninstabilität.** Bei viel Leistung und wenig Durchsatz koppeln Dampfgehalt, Druckverlust und Durchsatz zu einer Schwingung, die sich aufschaukelt statt abzuklingen. Der Grenzzyklus begrenzt sich zwar selbst, aber erst bei knapp 30 % Ausschlag — die Schwingungsüberwachung löst vorher aus.
- 💨 **Frischdampf-Absperrung mit dem richtigen Vorzeichen.** Druck steigt, Dampfblasen fallen zusammen, mehr Moderator, **positive** Reaktivität, Leistungsspitze. Die erste Fassung ließ die Leistung dabei zurückgehen: die quasistationäre Dampfbilanz sieht nur das Gleichgewicht und kann nicht sehen, dass ein schneller Druckanstieg den vorhandenen Dampf zusammendrückt. Ohne diesen Term hätte sich der Reaktor genau bei der Störung falsch herum verhalten, für die dieser Typ bekannt ist.
- 🔬 **Ein Fehler im Blasenmodell, der das Regelorgan lahmgelegt hätte.** Der Anteil der siedenden Kanalhöhe hing zuerst nur an der Unterkühlung. Damit hob sich bei sinkendem Durchsatz der steigende Dampfgehalt gegen die schrumpfende Siedezone auf — der Blasenanteil bewegte sich um 0,4 Prozentpunkte und die Leistung um 1,9 % statt um 11 %. Richtig ist das Verhältnis der Enthalpien: was zum Aufheizen bis zur Sättigung draufgeht, siedet nicht.
- 🧩 **Die Abstraktion hat gehalten.** Der zweite Reaktortyp brauchte genau eine Erweiterung der Engine: einen Haken für den siedenden Kern, weil dort die Austrittstemperatur festliegt und die Wärme in den Dampfgehalt geht. Alles Weitere — Kinetik, Rückkopplungen, Vergiftung, Nachzerfallswärme, Meldetafel — lief unverändert. Ein Test hält das fest: der Rechenkern darf keinen Reaktortyp beim Namen nennen.
- 🎛️ **Die Oberfläche fragt den Typ nach seiner Bedienung.** Bor und Druckhalter beim Druckwasserreaktor, Umwälzstrom und Frischdampf-Absperrung beim Siedewasserreaktor. Dazu ein eigenes Fließbild mit Druckbehälter, Abscheider und innerer Umwälzschleife.
- ✅ **56 Tests,** darunter ein Nachweis, dass zwei Reaktoren gleichzeitig laufen können, ohne sich über gemeinsam genutzte Typdaten zu stören.

## 0.0.4

- 🖼️ **Anlagenfließbild.** Reaktor, Druckhalter, Hauptkühlmittelpumpe, Dampferzeuger, Regelventil, Umleitstation, Turbine, Generator und Kondensator als Schema, mit fließendem Medium in den Leitungen, Rohrfarbe nach Temperatur, glühendem Kern nach Leistung, mitlaufenden Füllständen in Dampferzeuger und Druckhalter sowie Zustandsfarbe an Pumpe, Ventilen und Generator.
- ⚡ **Bewegung ohne Rechenlast.** Der Renderlauf schreibt nur eine Handvoll CSS-Custom-Properties auf den SVG-Wurzelknoten; Fluss, Drehzahl und Farbmischung entstehen daraus in CSS. Das sind rund zehn Schreibvorgänge je Takt statt hunderter DOM-Zugriffe — der Unterschied zwischen flüssig und ruckelig auf einem älteren Handy.
- 🔇 Bei `prefers-reduced-motion` stehen Fluss und Pumpenrad still, die Zustandsfarben bleiben.

## 0.0.3

- 🏭 **Der Druckwasserreaktor ist spielbar.** Vollständiger Kreislauf: Kern, vier Hauptkühlmittelpumpen mit Auslauf, heißer und kalter Strang als echte Laufzeit, Dampferzeuger mit Rohrmetallknoten, Druckhalter mit Heizstäben, Sprühwasser und Abblaseventil, Frischdampfschiene, Turbine, Kondensator, Speisewasser-Dreikomponentenregelung und Netzanbindung. Stabregelung, Turbinenregler, Speisewasser und Druckhalter lassen sich einzeln auf Hand umschalten.
- 🎛️ **Leitwarte mit Instrumenten statt Zahlenlisten.** Neun Rundinstrumente mit farbigen Betriebsbereichen, Stabbalken mit Sollwertmarke, die Reaktivitätsbilanz als Balken um die Nulllinie, vier Trendschreiber mit umschaltbarem Zeitbereich und eine Meldetafel mit Ringback-Folge und Hupe.
- 🧪 **Drei Fehler, die der Beharrungstest gefunden hat.** Der Dampferzeuger rechnete mit der Eintritts- statt der mittleren Rohrbündeltemperatur und entzog damit die doppelte Leistung — der Reaktor lief binnen Sekunden über die Leistungsauslösung. Das Temperaturprogramm der Stabregelung stand 1,7 K über der Mitteltemperatur, die sich aus der Wärmebilanz ergibt, und zog die Stäbe bis zum Anschlag. Und die 2,6 % Spaltenergie, die als Gammastrahlung direkt an Moderator und Einbauten gehen, fehlten in der Bilanz: 100 MW verschwanden, der Kern lief auf 104,6 %, um die Turbine trotzdem zu bedienen.
- 🎚️ **Turbinenregler mit Vorsteuerung.** Ein reiner PI auf die Leistungsabweichung scheiterte in beide Richtungen: vorsichtig ausgelegt blieb bei 60 % Last eine Dauerabweichung von 5 % stehen, kräftig ausgelegt entstand ein Grenzzyklus mit 94 MW Ausschlag im Sekundentakt. Ursache ist die kleine Streckenverstärkung — mehr Ventilöffnung senkt den Frischdampfdruck und damit die Arbeit je Kilogramm. Jetzt folgt die grobe Ventilstellung direkt der Lastanforderung, der Regler trimmt nur noch nach.
- ✅ **47 Tests.** Neu dabei: Beharrungszustand über eine Stunde, Energiebilanz über alle Kreisläufe, Schnellabschaltung, Jod-Grube mit Nachweis der fehlenden Stabwirksamkeit, Turbinenschnellschluss, Pumpenausfall, Selbstbegrenzung durch die Temperaturrückkopplungen, 4000 zufällige Bedieneingriffe ohne NaN und ein Determinismusnachweis über den Zustandshash.

## 0.0.2

- ⚛️ **Physik-Kern: Punktkinetik mit sechs Gruppen verzögerter Neutronen.** Gelöst mit einem exponentiellen Integrator — über einen Teilschritt werden die Vorläufer als Quelle festgehalten und die dann lineare Leistungsgleichung exakt gelöst. Rückwärts-Euler war der erste Ansatz und fiel durch: er ersetzt e^(a·h) durch 1/(1−a·h), und der Ratenfehler von rund a·h/2 multipliziert sich über eine prompt-kritische Exkursion auf. Zwischen dt = 0,05 s und dt = 0,0125 s lagen die Spitzenwerte 47 % auseinander. Mit der Exponentialform ist das Ergebnis praktisch unabhängig vom Zeitschritt.
- 🔥 **Reaktivitätsbilanz als Registry.** Jeder Beitrag — Stäbe, Doppler, Moderator, Dampfblasen, Xenon, Samarium, Bor, Graphit — ist ein eigener Eintrag statt einer Zeile in einer langen Formel. Die Engine verzweigt dadurch nie nach Reaktortyp, und die Oberfläche kann später ohne Zusatzarbeit zeigen, welcher Effekt gerade wie viele pcm liefert.
- ☢️ **Xenon-135 und Jod-135, in Vielfachen des Volllast-Gleichgewichts gerechnet.** Das kürzt Spaltquerschnitt und Fluss aus den Gleichungen und lässt genau das Verhältnis stehen, das die Jod-Grube bestimmt. Nach einer Abschaltung aus Volllast steigt die Xenon-Vergiftung auf das 1,9-Fache und erreicht ihr Maximum nach 8,5 Stunden — geprüft gegen die analytische Lösung, nicht gegen eine erinnerte Zahl.
- 🌡️ **Nachzerfallswärme in vier exponentiellen Gruppen** statt der bei t = 0 singulären Way-Wigner-Form. Trifft die ANS-5.1-Referenzpunkte über fünf Zehnerpotenzen: 4,2 % nach 10 s, 2,7 % nach 100 s, 0,89 % nach einer Stunde.
- 🎲 **Gesäter Zufall (xoshiro128+) statt Math.random.** Ohne reproduzierbare Folge gäbe es keine Wiedergabe eines Laufs und keine Regressionstests gegen einen festen Startwert.
- ✅ **33 Tests unter `node --test`,** darunter die Inhour-Gleichung als kanonische Prüfung des Kinetiklösers — sie wird im Test selbst numerisch gelöst, nicht als Zahl hinterlegt.

## 0.0.1

- 🏗️ **Erste Fassung: Gerüst und Leitstands-Oberfläche.** ReactorSim startet als eigenständiger Container (Port 17779, `docker-compose.yml` für Dockge) und liefert den kompletten Aufbau der Leitwarte: Startbildschirm mit den drei Reaktortypen, Statuszeile, acht Panels, Meldetafel und Trendbereich. Die Simulation dahinter ist noch ein Platzhalter — sie bewegt die Anzeigen, rechnet aber noch keine Physik. Der echte Kern folgt in 0.0.2.
- 📱 **Hochformat und Desktop aus demselben DOM.** Schmale Bildschirme bekommen Reiter, breite ein festes Raster mit dem Fließbild in der Mitte. Umgeschaltet wird ausschließlich per CSS — kein Layout-JavaScript, kein Resize-Handler.
- ⏱️ **Zeitraffer ohne Genauigkeitsverlust.** Der Simulationsschritt liegt fest bei 0,05 s; 1×, 4×, 16× und 60× ändern nur die Anzahl Schritte je Sekunde. Bei Rechenrückstand wird der Überschuss verworfen und gemeldet, statt sich zur Todesspirale aufzustauen.
- 🌍 **Deutsch und Englisch von Anfang an.** Kein Text steht fest im Code; die Übersetzungstabelle wird als Ganzes ins Skript gereicht.
- 🧠 **ES-Module statt Einzeldatei, mit versionierten Pfaden.** Ein `?v=`-Anhang bustet die Unterimporte eines Moduls nicht — der Browser würde nach einem Versionssprung eine neue `main.js` gegen veraltete Module laufen lassen. Die Statics liegen deshalb unter `/s/<version>/`, damit jede relative Einbindung die Version erbt.
