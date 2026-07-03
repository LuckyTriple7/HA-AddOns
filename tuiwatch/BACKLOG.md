# TUIWatch — Backlog (Ideen für später)

Gesammelte, noch nicht umgesetzte Verbesserungen. Reihenfolge = grobe Priorität.

## 11. Aktionscodes mit den getrackten Angeboten verrechnen
Die öffentlichen Aktionscodes (seit 0.26.1 erkannt/gemeldet) auf die Angebote anwenden:

- Pro Angebot ein **„effektiver Preis mit Code"** (z. B. „1.499 € − SAVE150 → 1.349 €"),
  sofern der Code auf Wert/Reisezeitraum passt.
- Optional: Wunschpreis-Alarm bezieht den besten anwendbaren Code mit ein.
- Achtung: Mindestbuchungswerte/Bedingungen der Codes (z. B. „ab 1.500 €") beachten;
  myTUI-Codes brauchen ein Konto → als Hinweis kennzeichnen.

## 12. Wartbarkeit: app.py / index.html aufteilen
`app.py` (~3.300 Zeilen) und `templates/index.html` (~2.300 Zeilen) in Module aufteilen,
damit künftige Änderungen kleiner und Reviews gezielter werden. Rein intern.

- z. B. `notifications.py` (HA/Telegram/SMTP/Digest), `trips_routes.py` (Reisen-DB),
  `watch.py` (Suchabo), JS aus dem Template in eine eigene Datei.
- Keine Verhaltensänderung; Tests müssen unverändert grün bleiben.

## 9. Image-Größe / Playwright-Last reduzieren
Der Playwright-/Chromium-Fallback macht das Add-on-Image groß. Da die JSON-APIs laut
Selbsttest stabil laufen, prüfen, ob Chromium nur noch bei Bedarf gebraucht wird.

- Messen, wie oft der Browser-Fallback real noch greift (Logging/Zähler).
- Option „nur API, kein Browser-Fallback" — spart Image-Größe & RAM.
- Ggf. Chromium erst bei erstem Bedarf nachladen statt im Image bündeln.
- _Teilschritt erledigt (v0.17.0):_ `playwright` wird in `scraper.py` nur noch **lazy**
  (im Browser-Fallback) importiert — das Modul lässt sich ohne playwright importieren.

## 13. Suchabo im Wochenüberblick
Der Digest könnte je aktivem Suchabo die aktuellen Treffer unter der Schwelle
mitauflisten (analog zu den Aktionscodes seit 0.26.2).

---

## Erledigt

- **#7 Such-Treffer als Sammel-Alarm → v0.27.0.** Gespeicherte Suchen lassen sich als
  „Suchabo" beobachten (Schwellenpreis, eigener Poll, Telegram/HA-Meldung bei neuen/
  tieferen Treffern, „Jetzt prüfen", Trefferliste im UI).
- **#10 PDF-Import-Debug-Modus → v0.26.8.** Detailansicht „🔍 Debug": bereinigter
  PDF-Text, je Feld erkannt/leer, geparstes JSON; bei fehlgeschlagenem Import automatisch.
- **#8 Regressionstests fürs Parsing → v0.17.0.** `tuiwatch/tests/` (pytest, offline
  gegen echte reduzierte Fixtures), CI: `.github/workflows/test-tuiwatch.yml`.
