# Backlog — MyPage

Zurückgestellte Vorhaben, die konkret genug sind, um später ohne Neuentwurf
weiterzugehen. Kein Ideen-Brainstorming — dafür ist `Ideas.md` da (Kartenspiele).

Recherchen zu einzelnen Themen liegen in eigenen Dateien:
`INSTAGRAM.md` (Beiträge automatisch auf Instagram veröffentlichen — Wege,
Meta-Voraussetzungen, Rezept über den RSS-Feed).

---

## Reiseblog — Ideen und Fallstricke

**Stand:** fertig mit v0.10.5, Überarbeiten des Berichts seit v0.11.7, Rückblick und
Wetter aus Home Assistant seit v0.11.8. Stufe 1 (Admin,
Wizard, KI-Bericht), Stufe 2 (öffentliche Seiten, Slugs, Freigabe je Tag, Mitglieder-Sperre,
Sitemap, Suche, IndexNow, statischer Export, Vorschau) und die vier Reste aus Stufe 3
(Ausgaben-Auswertung, übersetzte Auswahllisten, Formular-Abschnitt, eigene
Bildunterschriften) sind umgesetzt. Was hier steht, ist nichts Angefangenes: Ideen für
später und die Stolperstellen für spätere Arbeit am Modul.

**Zurückgestellte Ideen:**

- **Prompt anzeigen.** `/generate` und `/revise` geben den Prompt bereits mit zurück, die
  Oberfläche wirft ihn weg. Ausklappbar unter dem Bericht würde sofort erklären, warum ein
  Erlebnis im Text fehlt — leere Felder fallen ja kommentarlos aus dem Prompt.
- **Ort und Datum aus dem Foto-EXIF.** Beim Upload jagt `exif_transpose()` die Metadaten
  raus (`app.py`). Vorher Aufnahmedatum und GPS lesen und Tagesdatum/Ort vorbelegen — nur
  auf dem Reise-Upload-Weg, öffentlich bleiben die Bilder metadatenfrei.

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
- Beim Überarbeiten (`/revise`, seit v0.11.7) gehen die Tagesdaten **nur** bei `longer` und
  `custom` mit. Bei `shorter` und `polish` wären sie schädlich: sie laden das Modell ein,
  Weggelassenes nachzutragen, obwohl der Umfang gleich bleiben soll (`_REVISE_NEEDS_DATA`
  in `travelblog.py`).
- Der Bericht, den `/revise` überarbeitet, kommt aus dem **Formular**, nicht aus der
  gespeicherten Fassung — sonst ginge eine gerade von Hand geänderte Zeile verloren. Wer
  den Aufruf umbaut, muss `article` weiter mitschicken.
- Der Rückblick liegt in `trip.recap` und wird über eigene Routen gespeichert
  (`PUT /api/travel/trips/<tid>/recap`). `normalize_trip()` fasst ihn nicht an — sie
  übernimmt unbekannte Felder aus `existing`, weshalb ein normales Reise-Speichern ihn
  nicht verliert. Wer dort einmal von `dict(existing)` abweicht, löscht ihn still.
- `_recap_days()` nimmt Tage mit fertigem Text in **einer** der beiden Sprachen; der Prompt
  bevorzugt die deutsche Fassung, weil er selbst deutsch ist. Der Reise-Dialog bietet
  ohnehin nur „de" oder „de,en" an — eine rein englische Reise gibt es über die Oberfläche
  nicht.
- Die Wetter-Übernahme hängt an `SUPERVISOR_TOKEN` UND `homeassistant_api: true` in der
  `config.yaml`. Fehlt eines von beidem, antwortet der Supervisor mit 401 und die
  Entitätenliste bleibt leer.

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

## KI-Studio — nichts mehr offen, aber Fallstricke merken

**Stand:** alle acht Punkte der Durchsicht vom 2026-08-10 sind umgesetzt —
Übernahme passend zur Textart, Überarbeiten, Dauervorgaben (v0.10.16),
Seitenverhältnis im Studio, Variation, „Vorherige Fassung", Entwurfssuche
(v0.10.17), Kostenschätzung (v0.10.18), Prompt-Bibliothek (v0.10.19),
vorhandene Texte laden (v0.10.20), Alternativtexte (v0.10.21). Hier stehen nur
noch die Stolperstellen für spätere Arbeit.

**Fallstricke, die schon bekannt sind:**

- `_reference_blob()` entscheidet, was „Speicher aufräumen" für benutzt hält.
  `ai_prompts.json` **gehört hinein** (ein gespeichertes Vorlagenbild ist eine
  echte Verwendung), `uploads_meta.json` **auf keinen Fall** — sonst gälte jede
  Datei mit Alternativtext als benutzt und es gäbe nie wieder eine Waise.
- Alternativtexte hängen am Dateinamen. Wer einen weiteren Weg zum Löschen von
  Uploads baut, muss `_uploads_meta_forget()` mit aufrufen, sonst bleiben
  Einträge für Dateien zurück, die es nicht mehr gibt.
- `render_md()` füllt **nur leere** `alt=""`. Ein selbst geschriebener Text in
  `![…](…)` bleibt unangetastet — das ist Absicht und keine Lücke.
- Das Seitenverhältnis steht an zwei Stellen (Einstellungen und Bild-Studio).
  `aiRatioChanged()` hält sie gleich; gespeichert wird nur die obere. Wer eine
  dritte Stelle baut, muss sie dort eintragen.
- Die Kostenschätzung für Text ist bewusst eine Schätzung mit genannter Annahme.
  Wer sie „genauer" macht, ohne die Tokens zu kennen, macht sie nur falscher.
- Neue Ablagen im Add-on-Konfigurationsordner gehören in **beide** Listen des
  Backups (Sichern und Wiederherstellen) — sonst fehlen sie beim Zurückspielen.

---

## SEO: strukturierte Daten und Snippet-Vorschau

**Stand:** zurückgestellt am 2026-08-25 nach einer Bestandsaufnahme. Nichts davon
ist angefangen.

**Warum überhaupt:** Die Daten für Rich Results liegen bereits gepflegt in
`site.json`, werden aber nirgends als schema.org ausgegeben. JSON-LD gibt es nur
auf fünf Seitentypen: `Person` (Startseite), `BlogPosting` (Beitrag, Reisetag),
`SoftwareSourceCode` (Projekt), `Article` (Bibliothek). Die Startseite meldet
Google also weder FAQ noch Öffnungszeiten noch Termine — obwohl alles im Admin
eingetragen ist.

**Reihenfolge nach Wirkung, nicht nach Aufwand:**

1. **`LocalBusiness`** aus `sections.location` (~3–4 h). Name, Adresse und `geo`
   sind vorhanden — `lat`/`lng` werden schon für die Karte gepflegt. Größte
   Lücke, weil die Zielgruppe Verein/Handwerker/Dienstleister ohne dieses
   Schema in der lokalen Suche praktisch nicht vorkommt.
   - **Haken:** `hours_de` ist Freitext („Mo-Fr 9-17“), `openingHours` braucht
     `Mo-Fr 09:00-17:00`. Ein toleranter Parser ist richtig, aber er muss bei
     unklarer Eingabe die Angabe **weglassen** statt zu raten — falsche
     Öffnungszeiten in Google sind schlimmer als gar keine.
2. **`FAQPage`** aus `sections.faq` (~1 h). Google klappt die Fragen im
   Suchergebnis auf, der Treffer bekommt dadurch deutlich mehr Fläche.
3. **`Event`** aus `sections.events` (~1–1,5 h). Datum, Titel, Ort und URL sind
   alle da; `location` ist ein String und muss zu einem `Place`-Objekt werden.
4. **`BreadcrumbList`** auf `/blog/<id>`, `/seite/<slug>`, `/bibliothek/<slug>`,
   `/p/<id>` und den Reiseblog-Seiten (~2 h). Google zeigt dann den Pfad statt
   der nackten Adresse.
5. **`Service` + `Offer`** aus `sections.services` (~1 h). `price` ist gepflegt.
6. ~~**Snippet-Vorschau im Admin**~~ — **erledigt mit v0.10.49/0.10.50.** Fünf
   Vorschauen (Startseite, Beitrag, eigene Seite, Bibliothek-Eintrag,
   Reisebericht) mit Längenampel und Sprachumschalter.
7. **SEO-Ampel je Beitrag** (~1 Tag): Beschreibung gesetzt und lang genug?
   Titelbild? Alternativtexte? Text lang genug? Mindestens eine
   Zwischenüberschrift?
8. **Kleinkram:** `dateModified` fehlt bei `BlogPosting` — Beiträge haben gar
   kein `updated`-Feld, das müsste beim Speichern gesetzt werden (~1 h). Die
   Blog-Übersicht `/blog` hat kein `Blog`/`ItemList`-Schema.

**Bewusst nicht vorgesehen:** Keyword-Dichte, Lesbarkeits-Punktzahlen und eine
eigene Redirect-Suite. Weiterleitungen gibt es bereits; die beiden anderen
schleppt Yoast aus Gewohnheit mit, gewertet werden sie seit Jahren nicht.

**Fallstricke, die schon bekannt sind:**

- JSON-LD steht in den Vorlagen, nicht in `app.py` — `{%- set ld = {…} %}` je
  Seitentyp, ausgegeben über `{{ ld|tojson }}`. Wer es nach Python zieht, muss
  alle fünf Stellen gleichzeitig umstellen, sonst laufen sie auseinander.
- `_seo.html` gibt `canonical` und `hreflang` nur bei
  `site.design.allow_indexing` aus. Neue Schema-Blöcke gehören unter dieselbe
  Bedingung — über eine Seite, die nicht in den Index soll, gibt es Google auch
  nichts zu erzählen.
- Mehrere Schema-Blöcke auf der Startseite (Person + LocalBusiness + FAQPage +
  Event) sind erlaubt, sollten aber über `@graph` verbunden werden, statt sich
  gegenseitig zu ignorieren.
- Bewertungen aus `sections.testimonials` **nicht** als `Review`/
  `AggregateRating` ausgeben: Google wertet selbst eingetragene Bewertungen auf
  der eigenen Seite als Verstoß gegen die Richtlinien für Rich Results.
- Die Snippet-Vorschau bildet die Rückfallkette aus `app.py` nach
  (`_site_meta()`, `_plain_excerpt()`). Wer serverseitig an der Kette dreht, muss
  `SNIPS` in `admin.html` nachziehen — sonst zeigt die Vorschau etwas anderes,
  als die Seite ausliefert, und das ist schlimmer als gar keine Vorschau.
- `snipPlain()` ersetzt Tags durch ein **Leerzeichen**, genau wie
  `_plain_excerpt()`. Mit `textContent` klebt die Überschrift am ersten Absatz
  („HalloDas ist…“) und der Auszug weicht ab dem ersten Zeilenumbruch ab.
- Der Reise-Editor hat keine festen Feld-Ids — `travField()` baut die Eingaben
  zur Laufzeit und schreibt in `DAY.article`. Die Vorschau `snip-travel` liest
  deshalb aus dem Objekt und wird aus `travDraft()` heraus gezeichnet. Wer einen
  weiteren Weg baut, über den sich `DAY` ändert, muss `snipRender('snip-travel')`
  mit aufrufen.
