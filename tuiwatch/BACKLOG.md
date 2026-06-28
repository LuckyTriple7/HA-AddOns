# TUIWatch — Backlog (Ideen für später)

Gesammelte, noch nicht umgesetzte Verbesserungen. Reihenfolge = grobe Priorität.

## 7. Such-Treffer als Sammel-Alarm
Aus einer Region-Suche heraus nicht nur einzelne Hotels tracken, sondern eine ganze
Suche als „Beobachtung" speichern: *melde, wenn **irgendein** Hotel dieser Suche unter
X € fällt* (oder neu in die Trefferliste kommt). 

- Neue Entität „Suchabo" (Region + Filter + Schwellenpreis), eigener Poll.
- Benachrichtigung mit den neuen/günstigeren Treffern (HA/Telegram/E-Mail).
- UI: aus der Suchmaske „Diese Suche beobachten" + Liste der Abos.

## 8. Regressionstests fürs Parsing — ERLEDIGT (v0.17.0)
Umgesetzt in `tuiwatch/tests/` (pytest, offline gegen echte reduzierte Fixtures in
`tests/fixtures/`). Abgedeckt: Helfer (Dauer/Reisende/Hotel aus URL, `with_duration`,
Board-Mapping, Slug, Datum, `_search_params_from_url`, `offer_url_for`) sowie die
Normalisierung von `fetch_price_api`, `fetch_search`, `fetch_calendar`,
`fetch_destinations`, `fetch_airports`, `region_giata_from_breadcrumb`. CI:
`.github/workflows/test-tuiwatch.yml`. Lauf: `pytest tests/` im Ordner `tuiwatch/`.

## 9. Image-Größe / Playwright-Last reduzieren
Der Playwright-/Chromium-Fallback macht das Add-on-Image groß. Da die JSON-APIs laut
Selbsttest stabil laufen, prüfen, ob Chromium nur noch bei Bedarf gebraucht wird.

- Messen, wie oft der Browser-Fallback real noch greift (Logging/Zähler).
- Option „nur API, kein Browser-Fallback" — spart Image-Größe & RAM.
- Ggf. Chromium erst bei erstem Bedarf nachladen statt im Image bündeln.
- _Teilschritt erledigt (v0.17.0):_ `playwright` wird in `scraper.py` nur noch **lazy**
  (im Browser-Fallback) importiert — das Modul lässt sich ohne playwright importieren.
