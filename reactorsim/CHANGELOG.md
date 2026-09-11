# Changelog

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
