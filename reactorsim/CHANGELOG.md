# Changelog

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
