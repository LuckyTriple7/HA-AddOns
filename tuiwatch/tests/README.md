# TUIWatch — Tests

Regressionstests für die Parsing-/Normalisierungslogik in `scraper.py`. Sie laufen
**offline** (kein Netzwerk): die netzbehafteten Funktionen werden gegen echte, reduzierte
TUI-API-Antworten in `fixtures/` getestet, indem `requests.get`/`requests.post`
gemonkeypatcht werden.

## Ausführen

```bash
pip install -r tests/requirements.txt
pytest tests/ -q          # aus dem Ordner tuiwatch/
```

## Was geprüft wird

- **Reine Helfer**: Dauer-/Reisende-/Hotel-Parsing aus URLs, `with_duration`
  (Fenster-Weitung), Board-Code-Mapping, Slug, Datums-Formatierung, Suchparameter aus
  URL, `offer_url_for`.
- **Normalisierung echter Antworten**: `fetch_price_api` (Preis, Rabatt, Nächte,
  Verpflegung, Reisende, Flug, Rückreisedatum, Bewertung, Region), HTTP-400-Leermenge,
  `fetch_search`, `fetch_calendar`, `fetch_destinations`, `fetch_airports`,
  `region_giata_from_breadcrumb`.

## Fixtures aktualisieren

Ändert TUI das API-Format, die betroffene Datei in `fixtures/` durch eine frische
(reduzierte) Antwort ersetzen und die erwarteten Werte im Test anpassen. Die Tests zeigen
dann genau, welche Stelle im Parsing nachgezogen werden muss.
