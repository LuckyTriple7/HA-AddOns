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

## 10. PDF-Import: Debug-/Vorschau-Modus
Optionaler Diagnose-Modus, um bei einer künftigen TUI-Layout-Änderung selbst (ohne
Code-Runde) zu sehen, *warum* ein Feld nicht erkannt wurde. Ergänzt die bereits
umgesetzten Bausteine: Import-Hinweise (`check_fields`, v0.25.7) + Golden-Korpus
(`tests/fixtures/trips/`, v0.25.8) + Vorreinigung (`_clean_text`, v0.25.8).

- Endpoint/Schalter (admin/api-gated), der zu einem hochgeladenen oder gespeicherten
  PDF den **bereinigten Volltext** (`_clean_text`-Ausgabe) + das geparste JSON +
  `warnings` zurückgibt — so sieht man Roh-Text vs. Treffer nebeneinander.
- UI: kleiner „🔍 Debug"-Toggle in der Import-/Detailansicht (nur Admin), der den
  bereinigten Text und je Feld „erkannt/leer" anzeigt.
- Hinweis: Roh-/Detailtext kann PII enthalten (eigene Buchung) → nur für den
  eingeloggten Besitzer/Admin sichtbar, nicht ins Log.
- Wenn ein neues Layout bricht: bereinigten Text aus dem Debug-Modus kopieren,
  anonymisieren, als neuen Fall unter `tests/fixtures/trips/` ablegen → Test zeigt
  exakt das kippende Feld.

## 9. Image-Größe / Playwright-Last reduzieren
Der Playwright-/Chromium-Fallback macht das Add-on-Image groß. Da die JSON-APIs laut
Selbsttest stabil laufen, prüfen, ob Chromium nur noch bei Bedarf gebraucht wird.

- Messen, wie oft der Browser-Fallback real noch greift (Logging/Zähler).
- Option „nur API, kein Browser-Fallback" — spart Image-Größe & RAM.
- Ggf. Chromium erst bei erstem Bedarf nachladen statt im Image bündeln.
- _Teilschritt erledigt (v0.17.0):_ `playwright` wird in `scraper.py` nur noch **lazy**
  (im Browser-Fallback) importiert — das Modul lässt sich ohne playwright importieren.
