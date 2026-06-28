# TUIWatch — Backlog (Ideen für später)

Gesammelte, noch nicht umgesetzte Verbesserungen. Reihenfolge = grobe Priorität.

## 7. Such-Treffer als Sammel-Alarm
Aus einer Region-Suche heraus nicht nur einzelne Hotels tracken, sondern eine ganze
Suche als „Beobachtung" speichern: *melde, wenn **irgendein** Hotel dieser Suche unter
X € fällt* (oder neu in die Trefferliste kommt). 

- Neue Entität „Suchabo" (Region + Filter + Schwellenpreis), eigener Poll.
- Benachrichtigung mit den neuen/günstigeren Treffern (HA/Telegram/E-Mail).
- UI: aus der Suchmaske „Diese Suche beobachten" + Liste der Abos.

## 8. Regressionstests fürs Parsing
Die Normalisierung der TUI-API-Antworten in `scraper.py` (Suche / Offer / Kalender)
mit gespeicherten JSON-Fixtures testen, damit ein TUI-Formatwechsel nicht still etwas
kaputt macht.

- `tuiwatch/tests/` mit pytest, Fixtures aus echten (anonymisierten) Responses.
- Tests für `_run_search`-Normalisierung, `fetch_calendar`, `offer_url_for`,
  `_search_params_from_url`, Board-Code-Mapping, Datums-/Dauer-Helfer.
- Optional in CI (GitHub Actions) ausführen.

## 9. Image-Größe / Playwright-Last reduzieren
Der Playwright-/Chromium-Fallback macht das Add-on-Image groß. Da die JSON-APIs laut
Selbsttest stabil laufen, prüfen, ob Chromium nur noch bei Bedarf gebraucht wird.

- Messen, wie oft der Browser-Fallback real noch greift (Logging/Zähler).
- Option „nur API, kein Browser-Fallback" — spart Image-Größe & RAM.
- Ggf. Chromium erst bei erstem Bedarf nachladen statt im Image bündeln.
