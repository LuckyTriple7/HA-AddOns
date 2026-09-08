# TUIWatch — Backlog (Ideen für später)

Gesammelte, noch nicht umgesetzte Verbesserungen. Reihenfolge = grobe Priorität.

## 14. TUI-Aufrufe beim ersten Start senken
Eine frische Installation verbraucht rund 2.000 TUI-Aufrufe, bevor jemand etwas
angeklickt hat: `_ensure_dest_index()` crawlt beim Start den kompletten
Reiseziel-Baum (`build_destination_index`, ein Aufruf je Knoten). Danach liegt der
Index 14 Tage in `meta`, das Problem trifft also nur Neuinstallationen und Restores.

- `dest_index` + `dest_index_ts` in `_BACKUP_META_KEYS` aufnehmen — dann bringt ein
  Restore den Index mit, statt ihn neu zu crawlen.
- Crawl erst bei der ersten Reiseziel-Suche auslösen statt beim Start; wer die
  globale Suche nie benutzt, zahlt die Aufrufe sonst trotzdem.
- Sofortprüfung jedes wiederhergestellten Angebots nach einem Restore
  ([backup_routes.py](backup_routes.py), `for oid in new_ids`) weglassen — der
  Poller holt sie ohnehin, und bei vielen Angeboten kommt so ein zweiter Schwung
  Aufrufe obendrauf.
- _Besprochen am 31.08.2026, bewusst zurückgestellt._

## 18. Retention: alte Verlaufsdaten verdichten
`price_history`, `calendar_history`, `offer_events` und `calendar_month_moves`
wachsen unbegrenzt — aufgeraeumt wird heute nur `notify_log` (letzte 500),
`market_basket` (`_prune`) und die KI-Jobs. Treiber ist mit Abstand
`calendar_history`: im Messaufbau (20 Angebote, 500 Reisetage, ~25 Aenderungen je
Tag) waren das 250.000 Zeilen = rund 15 von 16,6 MB.

Bei den heutigen Groessenordnungen (Nutzer-DB ~25 MB, September 2026) ist das
unkritisch — SQLite stoert das nicht, und die Historie ist der eigentliche Wert
des Add-ons. Nur ist der Pfad eben unbegrenzt.

- **Verdichten statt loeschen:** aelter als X Monate auf einen Wert je Reisetag
  und Woche ausduennen. Die Trend-Aussage bleibt, das Volumen faellt deutlich.
- Als abschaltbare Option mit sicherem Standard (aus), nicht hart verdrahtet.
- Vorher messen, ab welcher Zeilenzahl die Abfragen wirklich weh tun — mit der
  gepflegten Spalte `offers.calendar_last_move_ts` (v0.113.22) faellt der
  groesste Dauerverbraucher ohnehin weg.
- _Aufgenommen am 08.09.2026._

## 19. VACUUM / Speicherplatz zurueckgeben
SQLite gibt geloeschten Platz nicht ans Dateisystem zurueck: nach dem Loeschen
eines Angebots (mitsamt `price_history`/`calendar_history` per CASCADE) bleibt die
Datei gross, die freien Seiten werden nur intern wiederverwendet. Ein `VACUUM`
gibt es im Add-on nirgends.

- Entweder `PRAGMA auto_vacuum=INCREMENTAL` (muss VOR der ersten Tabelle gesetzt
  werden, bei einer bestehenden Datei also nur ueber ein einmaliges `VACUUM`)
  plus gelegentliches `incremental_vacuum`,
- oder schlicht ein Wartungsknopf „Datenbank verdichten" neben der schon
  vorhandenen DB-Groessenanzeige — ehrlicher, weil der Nutzer den kurzen
  Schreibstopp dann bewusst ausloest.
- Achtung: `VACUUM` schreibt die Datei komplett neu und braucht waehrenddessen
  Platz in Hoehe der DB-Groesse.
- _Aufgenommen am 08.09.2026._

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

## 17. Perplexity: Preset-Modus statt fester Sonar-Modelle
Die Agent API (seit v0.106.0 in Benutzung, siehe `ai_client.py`) kennt neben dem
direkten `model: "perplexity/<name>"` auch `preset: "fast"|"low"|"medium"|"high"|"xhigh"`.
Ein Preset ist ein vorkonfiguriertes Bündel aus Modell, Systemprompt und
Suchparametern — und wählt dabei quer über Anbieter (OpenAI, Anthropic, Google,
xAI), inklusive `models`-Fallbackkette, wenn ein Anbieter ausfällt.

Reizvoll wegen der Fallbackkette und weil Perplexity die Presets pflegt, statt
dass wir Modellnamen nachziehen müssen. Offen zu klären, bevor sich das lohnt:

- **Was wird das für eine Option?** Heute ist `perplexity_model` eine Auswahl aus
  vier Sonar-Namen. Entweder die Liste um die fünf Presets erweitern (dann muss
  `_ai_request_perplexity_messages` je nach Wert `model` **oder** `preset` senden)
  oder ganz auf Presets umstellen — Letzteres wäre eine Breaking-Option und
  bräuchte eine Migration bestehender Konfigurationen.
- **Kostenanzeige.** `_AI_PRICING`/`_AI_PERPLEXITY_REQUEST_FEE` sind auf die
  Sonar-Namen verdrahtet; ein Preset hat kein festes Modell und damit keinen
  Listenpreis. Seit v0.107.0 kommt der echte Betrag aus `usage.cost.total_cost`
  mit — falls das auch bei Presets zuverlässig kommt, ist der Punkt erledigt und
  die Schätzung wird gar nicht mehr gebraucht. **Vorher nachmessen.**
- **Nutzungsstatistik.** Zähler-Buckets sind nach Modellname geschlüsselt. Ein
  Preset müsste als eigener Schlüssel laufen (z. B. `preset:high`), sonst
  vermischen sich die Zahlen mit denen der Sonar-Modelle.
- **Datenschutz/Erwartung.** Presets schicken die Anfrage je nach Auswahl an
  OpenAI oder Google — wer bewusst „Perplexity" eingestellt hat, rechnet damit
  nicht unbedingt. Gehört in die Options-Beschreibung und in DOCS.md.

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
