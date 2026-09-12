# Backlog

Offene, bewusst zurückgestellte Punkte -- kein Anspruch auf Vollständigkeit,
nur was beim Arbeiten aufgefallen ist und noch nicht dran war.

## Erweiterungen

### Serverseitige Nachrechnung statt Plausibilitätsprüfung

Der Punktestand wird schon heute auf dem Server gerechnet und nie vom Client
übernommen (`scoring.py`), und seit 0.0.54 kommt auch der Schwierigkeitsgrad
aus der Szenariodatei statt aus der Anfrage. Die **Kennzahlen** selbst bleiben
aber fälschbar, solange die Simulation im Browser läuft --
`scoring.validate_summary()` prüft nur, ob sie aus *irgendeinem* Lauf stammen
könnten, nicht ob aus *diesem*.

Die Bausteine für die echte Antwort liegen schon da:

* `sim/state.js` `hash()` -- bitgenauer Zustandshash, FNV-1a über die Doubles
* `rng.js` -- gesäter Zufall, kein `Math.random` in der ganzen Simulation
* fester Zeitschritt `DT = 0,05` s, unabhängig vom Zeitraffer

Fehlt: ein aufgezeichnetes Eingabeprotokoll (`{t_sim, Handlung, Wert}`) und ein
Node-Prozess im Container, der den Lauf nachspielt und den Endhash vergleicht.
Damit wäre eine Bestenliste erst wirklich belastbar.

### Wiedergabe eines Laufs

Fällt als Nebenprodukt der Nachrechnung ab -- dasselbe Eingabeprotokoll,
dieselbe Engine, nur mit Bildausgabe. Passt zu dem, was das Spiel zeigen will:
nicht das Ende, sondern den Weg dorthin. Die Auswertung könnte an jeder
Meldung in der Zeitleiste anspringen.

### Simulation in einen Web Worker

Würde Rechnung und Bildaufbau trennen: kein Ruckeln mehr bei 60×, und der
Zeitraffer könnte höher gehen. `templates/index.html` ist darauf schon
vorbereitet (`window.RS_I18N` statt `const`, siehe Kommentar dort).

Der Aufwand steckt nicht in der Engine, sondern in der Bedienung: `ui/panels.js`,
`ui/controls.js` und die `uiControls()`-Haken der drei Typdateien greifen heute
direkt auf `engine.state` und `engine.ctx` zu -- jeder Schieber, jeder
Auto/Hand-Schalter, jeder Pumpenknopf. Über eine Worker-Grenze braucht jeder
davon eine Nachricht. Das ist ein Umbau, keine Optimierung, und erst dann
sinnvoll, wenn Ruckeln tatsächlich auftritt.

### Vierter Reaktortyp

Die Schnittstelle aus `spec` und `hooks` trägt das ohne Änderung an der Engine
-- genau dafür ist sie so geschnitten. Der lehrreichste Kontrast zu den drei
vorhandenen wäre **CANDU**: Schwerwasser, positiver Dampfblasenkoeffizient wie
beim RBMK, aber mit ganz anderer Abschaltlogik, und Brennstoffwechsel im
laufenden Betrieb.

### Lauf-Export als CSV

Der Trendpuffer (`ui/trend.js`) hält die Verläufe ohnehin. Ein Knopf in der
Auswertung, der sie als CSV herausgibt, kostet fast nichts und macht einen Lauf
außerhalb des Spiels auswertbar.

### Mehrbenutzerbetrieb

`persist.py` führt schon ein Spieler-Token je Gerät, `auth.py` kennt dagegen
genau ein Konto aus der Umgebung. Erst mit echten Konten ergibt eine
Bestenliste mit Namen Sinn.
