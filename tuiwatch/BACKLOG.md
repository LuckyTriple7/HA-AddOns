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

## 18. Last-Minute-Auswertung aus dem Kalender pausierter Angebote
Seit 0.114.0 läuft der Preiskalender pausierter Angebote bis zur Abreise weiter
(vorher riss er mit der Auto-Pause wenige Tage vor Abflug ab). Damit wird messbar,
was TUI in den letzten 2–3 Wochen vor Abreise mit den Preisen macht — steigen oder
fallen sie für dasselbe Hotel?

- Auswertung über `calendar_history`: Preis je Reisetag nach Vorlauf (Tage bis
  Abreise), gepoolt über alle Angebote, analog `_lead_curve` in stats_routes.py.
- Ergebnis könnte die Buchungsampel unter 14 Tagen ergänzen (heute dort nur
  „nie 🔴").
- Erst sinnvoll, wenn einige Reisen die letzten Wochen durchlaufen haben —
  frühestens Anfang 2027 ansehen.
- _Besprochen am 25.09.2026, bewusst zurückgestellt._

## 19. KI-Aufrufe über LiteLLM leiten
TUIWatch läuft auf vserv01 in Docker, LiteLLM ebenfalls. Die KI-Aufrufe könnten
über LiteLLM laufen (ein Ort für Keys, Budgets und Kostenübersicht). Stand
10.10.2026: `tuiwatch` hängt nur an `tuiwatch_default`, `litellm` an
`litellm-caveman_default` — die beiden sehen sich noch nicht.

- **Netz.** TUIWatch-Stack zusätzlich in ein gemeinsames Netz mit `litellm`
  hängen; Basis-URL ist dann `http://litellm:4000`, ohne Port-Binding und ohne
  Tailscale. Im vorhandenen `litellm-caveman_default` erreicht TUIWatch auch
  `litellm-db`, `litellm-redis` und alle MCPs — sauberer ist ein eigenes kleines
  Netz nur für die beiden.
- **Umsetzung.** Pro Anbieter eine optionale Basis-URL (leer = wie heute direkt
  zum Anbieter) und die Passthrough-Endpunkte von LiteLLM nutzen
  (`/anthropic`, `/gemini`), als Key ein virtueller LiteLLM-Key. So bleiben
  native Websuche, Quellen und Schema-Output in `ai_client.py` unverändert; über
  den OpenAI-kompatiblen Endpunkt gingen sie verloren.
- **Perplexity.** Vorerst direkt lassen. Ob LiteLLM die Agent API (`/v1/agent`)
  durchreicht, ist ungeprüft.
- **Caveman-Plugin und Headroom.** Beide verändern Prompts und würden Berichte
  und JSON-Antworten verfälschen. Key-Alias in `CAVEMAN_STYLE_SKIP_KEY_ALIASES`
  eintragen oder die Header `x-caveman-style: off` und `x-headroom-bypass: true`
  mitschicken.
- **Eigener Key.** Virtueller Key mit Budget nur für TUIWatch.
- **Ausfall.** Bei LiteLLM-Update oder -Neustart hat TUIWatch keine KI; deshalb
  muss die leere Basis-URL als Rückweg erhalten bleiben.
- **Datenschutz.** LiteLLM kann Prompts in seiner Datenbank mitschreiben —
  Logging-Einstellung vorher prüfen.
- **Kosten.** TUIWatch rechnet weiter mit der eigenen Preistabelle, LiteLLM bucht
  zusätzlich. Ob Passthrough-Aufrufe dort sauber gebucht werden, nach dem ersten
  Aufruf im LiteLLM-UI prüfen.
- _Besprochen am 10.10.2026, zurückgestellt._

## 20. Modell- und Preisliste nachziehen
Abgleich der Modellauswahl und von `_AI_PRICING` mit den Anbieter-Seiten am
10.10.2026. Claude stimmt vollständig, bei Gemini und Perplexity gibt es Abweichungen.

- **`gemini-3.1-pro` (Standardmodell).** Googles Modell- und Preisseite führen
  nur `gemini-3.1-pro-preview`, kein stabiles `gemini-3.1-pro` und keinen Alias.
  Ob die API unsere ID annimmt, ist ungeprüft — im Container-Log der letzten 30
  Tage steht kein einziger Gemini-Aufruf. Einmal testen; schlägt er fehl, ID
  umstellen und die alte über `_MODEL_SUCCESSOR` umleiten.
- **`gemini-3.7-flash` aus der Auswahl nehmen.** Google leitet Anfragen
  automatisch auf `gemini-3.8-flash` um, das Modell steht nicht mehr in der
  Modell- und Preisliste. Eintrag in `_MODEL_SUCCESSOR` auf 3.8-flash.
- **Gemini-Flash-Preise ab 01.01.2027.** Bis 31.12.2026 kosten 3.8- und
  3.6-flash die Hälfte (0,75/3,75 USD); in der Tabelle stehen die regulären
  1,50/7,50 USD. Die Schätzung liegt bis Jahresende also um den Faktor 2 zu hoch.
- **`pplx-high` / `pplx-xhigh`.** Dahinter steckt `openai/gpt-5.6-sol`, laut
  Perplexity 4/20 USD (über 272k Input-Tokens 8/30). In der Tabelle stehen
  5/30. Wirkt nur im Rückfallweg, wenn die Antwort keine Kosten mitliefert.
- **Cache-Lesepreis.** Die Schätzung nimmt pauschal 10 % des Input-Preises.
  Opus 5.5 kostet 0,20 USD (5 %), Fable 5.1 0,25 USD (2,5 %) — leichte
  Überschätzung bei diesen beiden.
- **Suchgebühren fehlen in der Schätzung.** Gemini-Grounding kostet nach 5.000
  freien Suchen im Monat 14 USD je 1.000; für Claude und Gemini rechnet
  `_ai_estimated_call_cost` keine Suchgebühr ein.
- **Auslauftermine.** Kein Modell der aktuellen Auswahl hat ein Abschaltdatum
  vor September 2027 (Claude) bzw. überhaupt eines (Gemini). `claude-haiku-4-5`
  kann ab 15.10.2026 abgekündigt werden, ist aber schon auf Haiku 5.5 umgeleitet.

---

## Erledigt

- **#18 Retention + #19 VACUUM → v0.113.25.** Beides im neuen `maintenance.py`,
  erreichbar ueber den Datenbank-Dialog (Klick auf „DB" in der Fusszeile).
  Verdichten dueennt aus, statt zu loeschen: je Angebot und Tag bleiben erste,
  letzte, guenstigste und teuerste Preismessung, je Reisetag und Woche der letzte
  Kalenderpreis plus Baseline und juengste Zeile — die sichtbaren Kennzahlen
  aendern sich dadurch nicht. Automatisch nur ueber die Einstellung
  `history_compact_months` (Standard 0 = aus, Minimum 3 Monate), sonst auf
  Knopfdruck mit Vorschau und Rueckfrage. `VACUUM` gibt es als eigenen Knopf, mit
  vorheriger Anzeige des rueckholbaren Platzes; automatisch laeuft es nie, weil es
  waehrenddessen den doppelten Platz braucht und Schreibzugriffe blockiert.
  `offer_events` und `calendar_month_moves` bleiben bewusst unangetastet: beide
  sind schon aggregiert bzw. klein, das Verdichten haette dort nichts zu holen.

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
