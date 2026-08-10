# Backlog — MyPage

Zurückgestellte Vorhaben, die konkret genug sind, um später ohne Neuentwurf
weiterzugehen. Kein Ideen-Brainstorming — dafür ist `Ideas.md` da (Kartenspiele).

---

## Reiseblog — nichts mehr offen, aber Fallstricke merken

**Stand:** fertig mit v0.10.5. Stufe 1 (Admin, Wizard, KI-Bericht), Stufe 2 (öffentliche
Seiten, Slugs, Freigabe je Tag, Mitglieder-Sperre, Sitemap, Suche, IndexNow, statischer
Export, Vorschau) und die vier Reste aus Stufe 3 (Ausgaben-Auswertung, übersetzte
Auswahllisten, Formular-Abschnitt, eigene Bildunterschriften) sind umgesetzt. Hier stehen
nur noch die Stolperstellen für spätere Arbeit am Modul.

**Fallstricke, die schon bekannt sind:**

- `_reference_blob()` in `app.py` liest site.json UND travel.json. Wer eine weitere Ablage
  hinzufügt, muss sie dort ebenfalls eintragen, sonst hält „Speicher aufräumen" die Dateien
  für verwaist und löscht sie.
- Flask lädt Vorlagen **nicht** neu — den Testserver nach jeder Änderung an `admin.html`
  oder den öffentlichen Vorlagen neu starten, sonst testet man den alten Stand.
- Neue `.py`-Dateien brauchen eine eigene `COPY`-Zeile im Dockerfile.
- Die KI-Bildunterschriften in `article.captions` gehören zu den Fotos **mit** Hinweis, in
  genau deren Reihenfolge — Fotos ohne Hinweis überspringt der Prompt. Wer über den Index der
  vollen Fotoliste geht, hängt die Unterschrift ans falsche Bild (genau das war bis v0.10.4
  im Wizard so). Öffentlich schlägt seit v0.10.5 die eigene Unterschrift in
  `photo.caption_<lang>` die der KI.
- Die Auswahllisten in `travelblog.py` speichern **deutschen Klartext** (`sonnig`, `Eintritt`),
  und der wandert unverändert in den Prompt. Übersetzt wird ausschließlich die Anzeige, über
  `trav_opt_labels` in den Locales (`_trav_opt_label()` serverseitig, `travField()` im Admin).
  Wer die Werte in den Tupeln ändert, muss die Karten in `en.json` nachziehen — sonst steht
  dort wieder Deutsch, ohne dass etwas kaputtgeht.
- Öffentliche Beträge hängen an `settings.include_prices` der Reise, demselben Schalter, der
  der KI das Nennen von Preisen erlaubt. Kein zweiter Schalter — wer der KI Geld verbietet,
  will es auch nicht als Tabelle darunter.

---

## KI-Monatsbudget als harter Stopp

**Stand:** zurückgestellt am 2026-08-09 bei der Umsetzung der Verbrauchsanzeige (v0.9.8).

**Warum überhaupt:** Die Stundenlimits (20 Bilder, 60 Texte) begrenzen Ausreißer,
nicht die Summe — 20 Bilder pro Stunde sind 480 am Tag. Ein Monatsbudget schützt
die Geldbörse an der Stelle, an der es weh tut.

**Was zu bauen wäre:**

- Betrag je Monat, einstellbar im Tab *KI* neben der Preistabelle (in `ai_usage.json`
  unter einem eigenen Schlüssel, nicht in `site.json` — er gehört zu den Kosten).
- Prüfung in `api_ai_studio_image`, `api_ai_text` und im Gemini-Zweig von
  `api_translate`, jeweils **vor** `_ai_rate_take`: laufende Monatssumme über
  `_ai_usage_cost` gegen das Budget. Darüber → `{'error': 'budget'}`, HTTP 429.
- Frontend: eigener Fehlertext in `aiErrMsg`, dazu eine Warnzeile im Verbrauchs-Panel
  ab ~80 % (Locale-Keys `ai_err_budget`, `ai_budget_*`).

**Voraussetzung, die schon steht:** Verbrauch und Preise liegen seit v0.9.8 in
`ai_usage.json`, `_ai_usage_cost()` rechnet bereits eine Zeile ab.

**Haken, der beim Bauen zu bedenken ist:** Ohne gepflegte Preise ist die
Monatssumme 0 — ein Budget würde dann nie greifen und eine Sicherheit vortäuschen.
Also entweder auf Token-/Bild-Zahlen ausweichen oder deutlich sagen, dass das
Budget ohne Preise wirkungslos ist.

---

## HA-Sensoren für den KI-Verbrauch

**Stand:** zurückgestellt am 2026-08-09, gleicher Anlass.

**Warum überhaupt:** Damit „benachrichtige mich bei 80 % des Budgets" eine ganz
normale HA-Automation wird, statt im Add-on nachgebaut zu werden.

**Was zu bauen wäre:** drei Sensoren in `push_ha_sensors()`, gleiche Form wie die
bestehenden:

- `sensor.mypage_ai_cost_month` — Monatskosten, Einheit `€`, `mdi:currency-eur`
- `sensor.mypage_ai_calls_month` — Aufrufe des Monats, `mdi:robot`
- `sensor.mypage_ai_tokens_month` — Tokens des Monats (rein + raus), `mdi:counter`

**Haken:** `push_ha_sensors()` läuft periodisch und liest dann bei jedem Durchlauf
`ai_usage.json` — die Summe je Monat vorher bilden, nicht je Sensor neu einlesen.
Sensoren nur melden, wenn überhaupt ein `gemini_api_key` gesetzt ist; sonst stehen
in jeder HA-Instanz ohne KI drei Sensoren mit 0 herum.

---

## KI-Studio — zurückgestellte Ausbaustufen

**Stand:** aufgenommen am 2026-08-10 bei der Durchsicht des KI-Tabs (v0.10.16).
Umgesetzt wurden daraus bereits die Übernahme passend zur Textart, das
Überarbeiten vorhandener Texte und die Dauervorgaben. Der Rest steht hier.

Grob nach Nutzen pro Aufwand sortiert:

- **Seitenverhältnis ins Bild-Studio spiegeln.** `ai-ratio` steht im
  Einstellungs-Panel, wird aber je Bildlauf mitgeschickt (`runAiImage`). Zum
  Wechseln muss man hochscrollen und die Einstellungen speichern. Dasselbe
  `<select>` gehört neben „Anzahl" — beide Stellen auf denselben Wert
  synchronisieren, gespeichert wird weiterhin nur oben.
- **„↻ Variation" an der Ergebniskarte.** Heute: „🎨 Als Vorlage" klicken, hoch
  scrollen, neu erzeugen. Ein Knopf auf der Karte kann `setAiRef(url)` und
  `runAiImage()` in einem Schritt tun. Nur für bereits gespeicherte Bilder
  sinnvoll — ein Entwurf hat noch keine Upload-Adresse, die als `ref` taugt.
- **Kostenschätzung vor dem Lauf.** Preise und Verbrauch liegen seit v0.9.8 in
  `ai_usage.json`, `_ai_usage_cost()` rechnet eine Zeile ab. Daraus eine Zeile
  „4 Bilder ≈ 0,12 $" neben dem Erzeugen-Knopf. Haken: für Text sind die Tokens
  vorher nicht bekannt — dort nur der Preis je Mio. Tokens als Anhalt, keine
  Summe, sonst steht da eine erfundene Zahl.
- **Prompt-Bibliothek fürs Bild-Studio.** Das Text-Studio hat Entwürfe
  (`ai_drafts.json`), das Bild-Studio nichts — ein guter Prompt ist nach dem
  Neuladen weg. Gleiche Mechanik, eigene Datei `ai_prompts.json`: Name, Prompt,
  Stil-Anhang, Vorlagenbild, Anzahl. Backup-Regex nicht vergessen.
- **Vorhandenen Beitrag ins Studio laden.** Gegenrichtung zu „Als Blogbeitrag
  übernehmen": Beitrag/Projekt/Bibliothek-Eintrag auswählen, Felder füllen, dann
  überarbeiten oder die fehlende Sprache nachziehen. Braucht eine Auswahl-Liste
  im Studio und die Rückrichtung der Feldzuordnung aus `aiToPost()` und
  Geschwistern. **Haken:** die Zuordnung ist nicht überall verlustfrei — ein
  Projekt hat nur einen Titel für beide Sprachen.
- **Sicherheitsnetz beim Neu-Erzeugen.** Ein zweiter Lauf überschreibt die Felder
  still, ebenso jede Überarbeitung. Die vorige Fassung im Speicher halten und
  „↶ Vorherige Fassung" anbieten (nur zur Laufzeit, nichts speichern).
- **Entwurfsliste: Suche und Sortierung.** Ab ~20 Einträgen wird die Liste
  unübersichtlich. Filterfeld über Name und Textart, Sortierung nach Datum oder
  Name. Rein im Frontend, `/api/ai/drafts` liefert bereits alle Zeilen.
- **KI-Alt-Text für Bilder.** Uploads haben keinerlei Alt-Text — nur
  Reiseblog-Fotos kennen Bildunterschriften. Bilder gehen damit ohne
  Alternativtext in Beiträge, schlecht für Barrierefreiheit und SEO. Gemini kann
  ihn aus dem Bild erzeugen (DE + EN). **Der größte Brocken der Liste:** Uploads
  brauchen dafür überhaupt erst eine Metadaten-Ablage, und die öffentlichen
  Vorlagen müssen den Text dann auch ausgeben.
