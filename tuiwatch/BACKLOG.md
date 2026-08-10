# TUIWatch — Backlog (Ideen für später)

Gesammelte, noch nicht umgesetzte Verbesserungen. Reihenfolge = grobe Priorität.

## 11. Aktionscodes mit den getrackten Angeboten verrechnen
Die öffentlichen Aktionscodes (seit 0.26.1 erkannt/gemeldet) auf die Angebote anwenden:

- Pro Angebot ein **„effektiver Preis mit Code"** (z. B. „1.499 € − SAVE150 → 1.349 €"),
  sofern der Code auf Wert/Reisezeitraum passt.
- Optional: Wunschpreis-Alarm bezieht den besten anwendbaren Code mit ein.
- Achtung: Mindestbuchungswerte/Bedingungen der Codes (z. B. „ab 1.500 €") beachten;
  myTUI-Codes brauchen ein Konto → als Hinweis kennzeichnen.

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

## 14. Check24: GIATA-Auto-Mapping
Hotel-Pinning fürs Check24-Feature ist heute manuell. Hotelname + Ort fuzzy
gegen die Check24-Hotelsuche matchen, besten Treffer vorschlagen, Nutzer
bestätigt nur noch (statt selbst zu suchen).

## 15. cert_expiry-Debug-Log aktivieren
Offener Punkt aus v0.58.1: das Debug-Log für den cert_expiry-Sensor wurde nie
aktiviert — bei nächster „Sensor unavailable"-Meldung zuerst dieses Log anwerfen.

## 16. static/app.js aufteilen
~3.300 Zeilen; analog zu den app.py-Tranchen (#12) in Module splitten
(Kalender / KI / Angebote / Suche je Datei). Rein intern, Tests bleiben grün.

---

## Erledigt

- **#12 Wartbarkeit: app.py / index.html aufteilen → v0.48.7.** In vier Tranchen,
  ohne Verhaltensänderung, Tests durchgehend grün:
  - _v0.48.1:_ `trips_routes.py` (Reisen-Blueprint, 984 Z.), `backup_routes.py`
    (Backup/Restore, 469 Z.), `digest.py` (Wochen-Digest, 190 Z.) — app.py von
    ~7.400 auf ~5.500 Zeilen.
  - _v0.48.4/0.48.5:_ `ai_client.py` (KI-Provider-Client), `price_calendar.py`
    (Preiskalender + Routen), `watch.py` (Suchabo) — app.py ~4.900 Zeilen.
  - _v0.48.6:_ `ai_routes.py` (KI-Analyse, 1.514 Z.), `offers_routes.py`
    (Angebote/Suche/Vergleiche, 768 Z.) — app.py ~2.800 Zeilen.
  - _v0.48.7:_ Frontend-JS nach `static/app.js` (~3.280 Z.), index.html ~930 Zeilen.
  - **Muster für weitere Splits:** `import app as A` und der Zugriff erst später
    über das Attribut — monkeypatch-sicher und zyklenfrei; Re-Exports für Poller
    und Tests. Guards dazu: `tests/test_dockerfile.py` (COPY-Liste),
    `tests/test_script_start.py` (Skript-Start wie run.sh). Gilt genauso für #16.
- **#7 Such-Treffer als Sammel-Alarm → v0.27.0.** Gespeicherte Suchen lassen sich als
  „Suchabo" beobachten (Schwellenpreis, eigener Poll, Telegram/HA-Meldung bei neuen/
  tieferen Treffern, „Jetzt prüfen", Trefferliste im UI).
- **#10 PDF-Import-Debug-Modus → v0.26.8.** Detailansicht „🔍 Debug": bereinigter
  PDF-Text, je Feld erkannt/leer, geparstes JSON; bei fehlgeschlagenem Import automatisch.
- **#8 Regressionstests fürs Parsing → v0.17.0.** `tuiwatch/tests/` (pytest, offline
  gegen echte reduzierte Fixtures), CI: `.github/workflows/test-tuiwatch.yml`.
