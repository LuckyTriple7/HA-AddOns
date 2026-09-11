# Changelog

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
