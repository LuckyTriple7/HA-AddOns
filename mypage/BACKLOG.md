# Backlog — MyPage

Zurückgestellte Vorhaben, die konkret genug sind, um später ohne Neuentwurf
weiterzugehen. Kein Ideen-Brainstorming — dafür ist `Ideas.md` da (Kartenspiele).

Recherchen zu einzelnen Themen liegen in eigenen Dateien:
`INSTAGRAM.md` (Beiträge automatisch auf Instagram veröffentlichen — Wege,
Meta-Voraussetzungen, Rezept über den RSS-Feed).

---

## Reiseblog — nichts mehr offen, aber Fallstricke merken

**Stand:** Stufe 1 (Admin, Wizard, KI-Bericht), Stufe 2 (öffentliche Seiten, Slugs, Freigabe
je Tag, Mitglieder-Sperre, Sitemap, Suche, IndexNow, statischer Export, Vorschau) und die
vier Reste aus Stufe 3 (Ausgaben-Auswertung, übersetzte Auswahllisten, Formular-Abschnitt,
eigene Bildunterschriften) sind mit v0.10.5 fertig geworden. Dazu kamen: Überarbeiten des
Berichts (v0.11.7), Rückblick auf die ganze Reise und Wetter aus Home Assistant (v0.11.8),
Prompt-Ansicht und Datum/Ort aus dem Foto-EXIF (v0.11.9). Offene Vorhaben stehen keine
mehr an — hier stehen nur noch die Stolperstellen für spätere Arbeit am Modul.

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
- `_exif_facts()` liest Aufnahmedatum und GPS **vor** `exif_transpose()`. Wer in
  `_store_upload_image()` die Reihenfolge dreht, bekommt stillschweigend leere Werte —
  kaputt geht dabei nichts, es füllt sich nur nichts mehr. Die abgelegte Datei muss
  metadatenfrei bleiben: der Rückgabewert geht ausschließlich an den hochladenden Browser.
- Der Ortsname kommt von Nominatim (OpenStreetMap) und **nur auf Knopfdruck**. Kein
  automatischer Aufruf einbauen: das schickte die Koordinaten privater Fotos ungefragt an
  einen fremden Dienst. Nominatim erlaubt eine Anfrage je Sekunde und verlangt die Kennung
  in `NOMINATIM_UA`.

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
2. **`Event`** aus `sections.events` (~1–1,5 h). Datum, Titel, Ort und URL sind
   alle da; `location` ist ein String und muss zu einem `Place`-Objekt werden.
   Erzeugt weiterhin erweiterte Treffer.
3. **`BreadcrumbList`** auf `/blog/<id>`, `/seite/<slug>`, `/bibliothek/<slug>`,
   `/p/<id>` und den Reiseblog-Seiten (~2 h). Google zeigt dann den Pfad statt
   der nackten Adresse.
4. **`Service` + `Offer`** aus `sections.services` (~1 h). `price` ist gepflegt.
5. **`FAQPage`** aus `sections.faq` (~1 h) — **nur noch Beiwerk.** Siehe die
   Richtigstellung unten; einzeln lohnt es nicht, mitnehmen kann man es, wenn
   ohnehin jemand am Startseiten-Schema arbeitet.
6. ~~**Snippet-Vorschau im Admin**~~ — **erledigt mit v0.10.49/0.10.50.** Fünf
   Vorschauen (Startseite, Beitrag, eigene Seite, Bibliothek-Eintrag,
   Reisebericht) mit Längenampel und Sprachumschalter.
7. **SEO-Ampel je Beitrag** (~1 Tag): Beschreibung gesetzt und lang genug?
   Titelbild? Alternativtexte? Text lang genug? Mindestens eine
   Zwischenüberschrift?
8. **Kleinkram:** `dateModified` fehlt bei `BlogPosting` — Beiträge haben gar
   kein `updated`-Feld, das müsste beim Speichern gesetzt werden (~1 h). Die
   Blog-Übersicht `/blog` hat kein `Blog`/`ItemList`-Schema.

**Richtigstellung vom 2026-08-27 — `FAQPage` bringt keine Fläche mehr:**

Die frühere Fassung dieser Liste führte `FAQPage` an zweiter Stelle mit der
Begründung, Google klappe die Fragen im Suchergebnis auf und der Treffer bekomme
dadurch deutlich mehr Fläche. **Das gilt nicht mehr.** Google hat die
FAQ-Rich-Results am **7. Mai 2026** abgeschaltet. Vorstufe war der August 2023,
seitdem gab es sie nur noch für bekannte Behörden- und Gesundheitsseiten; seit
Mai 2026 für niemanden. Die Berichte in der Search Console fielen im Juni 2026
weg, die Unterstützung in der Search-Console-API im August 2026.

Was bleibt: Die Auszeichnung ist weiterhin gültiges schema.org, sie schadet
nicht (Google sagt ausdrücklich, ungenutzte strukturierte Daten seien
unschädlich), und KI-Crawler lesen sie. Als Hebel für die **Darstellung im
Suchergebnis** ist sie tot — deshalb steht sie jetzt an letzter Stelle.

`LocalBusiness` und `Event` sind davon **nicht** betroffen und erzeugen weiter
erweiterte Treffer. Wer diese Liste später wieder aufnimmt: nicht aus dem
Gedächtnis planen, sondern kurz gegen die aktuelle Google-Dokumentation prüfen —
die Menge der Typen mit erweiterten Treffern wird seit Jahren kleiner, nicht
größer (`How-to` fiel 2023, `FAQPage` 2026).

Belege: <https://developers.google.com/search/docs/appearance/structured-data/local-business>,
<https://www.searchenginejournal.com/google-drops-faq-rich-results-from-search/574429/>

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

---

## Vergleich mit WordPress — die verbliebenen Lücken

**Stand:** Bestandsaufnahme am 2026-08-27, am Code geprüft (nicht aus Erinnerung).
Nichts davon ist angefangen. Was WordPress kann und hier fehlt — sortiert nach
Wirkung je Aufwand, nicht nach Größe des Vorhabens.

**Was ausdrücklich schon da ist** und deshalb hier nicht auftaucht: geplante
Veröffentlichung (`post_status()` in `app.py`, Status `scheduled` über ein
Datum in der Zukunft), RSS/Atom, OpenGraph, Volltextsuche, Weiterleitungen,
Sitemap, IndexNow, Kommentare mit Moderation, Newsletter mit Double-Opt-in,
Formular-Baukasten, Design-Vorlagen, statischer Export, Backup samt
Rückholen früherer Stände.

### 1. Responsive Bilder (`srcset`) — größter Web-Vitals-Hebel

`_store_upload_image()` legt genau **eine** Fassung ab: höchstens 1600 px, WebP.
WordPress erzeugt mehrere Größen und liefert sie über `srcset` aus. Ein Handy
lädt hier also 1600 px für einen 400 px breiten Platz — auf jeder Seite, für
jedes Bild.

**Was zu bauen wäre:** beim Ablegen zusätzlich 480 px und 960 px erzeugen,
Namensschema `<uuid>-480.webp`; `render_md()` und die Vorlagen geben `srcset`
plus `sizes` aus.

**Haken:** `_unused_uploads()` erkennt verwaiste Dateien über einen
Vorkommen-Scan im JSON-Text. Die Varianten dürfen deshalb **nie** einzeln in
`site.json` landen — sonst gilt jede Variante ohne eigenen Verweis als Waise und
wird weggeräumt. Löschen und Aufräumen müssen die Geschwisterdateien am
Namenspräfix mitnehmen, und beide Backup-Listen (Sichern und Wiederherstellen)
brauchen sie ebenfalls. Aufwand ~1 Tag.

### ~~2. Blättern im Blog~~ — erledigt mit v0.11.16

`blog_index()` rendert **alle** veröffentlichten Beiträge in eine einzige Seite.
Bei zweihundert Beiträgen sind das mehrere Megabyte, und der Besucher lädt sie
bei jedem Aufruf. WordPress zeigt zehn je Seite.

**Was zu bauen wäre:** `?seite=n` mit fester Seitengröße, `rel="prev"`/`rel="next"`
im Kopf, Blätterleiste unten.

**Umgesetzt als:** `blog_pager()` (Ausschnitt plus Nummernfenster mit
Auslassung), `_page_arg()` und `_blog_page_url()` in `app.py`, Leiste in
`blog.html`, zehn Beiträge je Seite (`BLOG_PAGE_SIZE`). Sitemap und Feed führen
weiterhin alle Beiträge — nachgemessen. Seite jenseits des Bestandes: 404.
Kanonische Adresse trägt `?seite=`, aber nur ohne aktiven Filter; gefilterte
Ansichten kanonisieren wie bisher auf `/blog`.

### 3. Strukturierte Daten auf der Startseite

Eigener Abschnitt weiter oben in dieser Datei („SEO: strukturierte Daten und
Snippet-Vorschau"), Reihenfolge `LocalBusiness` → `Event` → `BreadcrumbList` →
`Service`. Für die Zielgruppe Verein, Handwerk, Dienstleistung die größte
Sichtbarkeitslücke überhaupt. `FAQPage` stand hier früher an zweiter Stelle und
ist seit dem 7. Mai 2026 wirkungslos — Einzelheiten in der Richtigstellung im
SEO-Abschnitt.

### 4. Mehrere Autoren

Ein Beitrag hat kein `author`-Feld (`_normalize_post()`), und es gibt keine
Rollen: einen Admin, ansonsten Mitglieder, die ausschließlich lesen. WordPress
kennt Redakteur, Autor und Mitarbeiter samt Autorenarchiv. Für eine Vereinsseite,
auf der mehrere Leute schreiben, ist das der strukturell größte Unterschied.

**Was zu bauen wäre:** Rollenkennzeichen am Mitglied, ein eingeschränkter
Admin-Zugang (nur eigene Beiträge), `author` am Beitrag, Autorenseite unter
`/autor/<id>`.

**Haken:** Das ist ein sicherheitsrelevanter Umbau — jede Admin-Route braucht
dann eine Rechteprüfung, nicht nur die Anmeldung. Vorher lohnt der Smoke-Test
über alle Routen aus `Ideas.md`, sonst merkt niemand, welche Route die Prüfung
vergessen hat. Aufwand ~3–4 Tage.

### 5. Revisionen je Beitrag

Es gibt Versionsstände der **ganzen** `site.json` (zwanzig Stück,
90-Sekunden-Zusammenfassung). „Nur diesen einen Beitrag auf gestern zurück" geht
nicht. Baubar **ohne** neues Ablageformat: den Beitrag per Id aus den
vorhandenen Schnappschüssen ziehen, Textvergleich anzeigen, einzeln
zurückschreiben.

**Haken:** Ein einzeln zurückgeschriebener Beitrag darf den Rest der Datei nicht
anfassen — also über den normalen Speicherweg gehen, nicht die alte Datei
einspielen. Aufwand ~1 Tag, weil die Datenbasis bereits steht.

### 6. Kategorien und echte Archivseiten für den Blog

Der Blog kennt nur Schlagwörter (höchstens acht) und filtert über `?tag=`.
Kategorien gibt es ausschließlich in der Bibliothek. Damit fehlen Archivseiten
mit eigener Adresse und eigener Beschreibung — eine Filteradresse mit
Fragezeichen nimmt Google selten in den Index.

**Was zu bauen wäre:** `/tag/<slug>` als eigene Seite mit eigenem
`meta_description`, wahlweise eine Kategorie je Beitrag mit `/kategorie/<slug>`.
Zusammen mit Punkt 2 zu bauen, beide fassen dieselbe Route an. Aufwand ~4 h
zusätzlich.

### ~~7. HTTP-Cache für die öffentlichen Seiten~~ — erledigt mit v0.11.16

Nur der Feed setzt `Cache-Control` und beantwortet `If-None-Match` mit 304. Jede
Anfrage an die Startseite rendert die Seite neu, obwohl sich zwischen zwei
Aufrufen meist nichts geändert hat.

**Was zu bauen wäre:** ETag aus der Änderungszeit von `site.json`, der Sprache
und dem Anmeldestatus; danach `make_conditional(request)` wie beim Feed.

**Umgesetzt als:** `_cache_headers()` in `app.py` (after_request am
`public_app`). Der Fingerabdruck stammt aus dem **fertigen Rumpf**, nicht aus
Änderungszeiten der Ablagen — damit kann kein neues Feld vergessen werden.
Gespart wird die Übertragung, nicht das Rendern.

**Haken, der beim Weiterbauen gilt:** Seiten mit Mitgliederinhalt dürfen
**niemals** `public` bekommen. Erkannt wird das am Sitzungs-Cookie `usession`;
liegt eines an, geht `private, no-store` heraus und gar kein ETag. Wer diese
Prüfung durch etwas Genaueres ersetzt, muss dieselbe Richtung wahren: im
Zweifel `private`, nie `public`. Seiten mit Aufrufzähler (Beitragsseiten,
Startseite mit Zähler) ändern sich bei jedem Aufruf und bekommen deshalb nie
ein 304 — das ist so richtig und kein Fehler.

### 8. Import aus WordPress

Es gibt keinen. Wer von WordPress herüberzieht, tippt Beiträge, Seiten und
Schlagwörter ab — der Grund, warum MyPage heute eher ein Zweitsystem als ein
Ersatz ist. Ein Leser für die WXR-Datei (Beiträge, Seiten, Schlagwörter, Bilder)
ändert das.

**Haken:** Die Bilder stecken als absolute Adressen im Text und müssen beim
Import heruntergeladen, durch `_store_upload_image()` geschickt und im Markdown
ersetzt werden. Das Herunterladen ist ein Zugriff auf eine vom Benutzer
angegebene Adresse — die SSRF-Prüfung über `ipaddress` ist dort Pflicht
(gleiches Muster wie beim GitHub-Import). WXR ist zudem XML mit
HTML-Beitragstext: der Text muss durch dieselbe Bereinigung wie eigene Eingaben,
nicht ungeprüft übernommen. Aufwand ~2 Tage.

### Kleinkram, gesammelt

- `updated`/`dateModified` fehlt am Beitrag komplett — steht schon als Punkt 8 im
  SEO-Abschnitt, ~1 h.
- **Menü-Baukasten:** Die Navigation entsteht automatisch aus den vorhandenen
  Sektionen und den eigenen Seiten. Kein frei gesetzter Menüpunkt, kein
  Untermenü, kein eigenes Fußzeilenmenü.
- **Kommentare nur für Mitglieder** (`blog_comment()` bricht ohne
  `current_member` mit 403 ab). Gäste mit Freigabe wären der WordPress-Weg. Die
  jetzige Regelung ist eine bewusste Entscheidung gegen Spam, kostet aber
  Reichweite — vor einem Umbau gehört geklärt, ob Moderation und Rate-Limit dafür
  reichen.
- **Formulare** kennen kein Dateifeld und keine Bedingungslogik
  (`FORM_FIELD_TYPES`). Ein Dateifeld zieht Quota, Virenfrage und Aufräumen nach
  sich — nicht nebenbei zu machen.
- ~~**Medienverwaltung** ohne Suche, ohne Ersetzen einer Datei, ohne Ordner~~ —
  **erledigt mit v0.11.17.** Suche über Herkunftsname, Etiketten,
  Alternativtexte und Fundstellen; Dialog *Datei verwalten* mit „Verwendet in";
  Ersetzen unter gleichem Dateinamen. Dazu **Ordner nur im Admin** (v0.11.18):
  eine Ebene, ein Ordner je Datei, Mehrfachauswahl im Raster zum Einsortieren.
  Im Dateisystem wandert nichts — der Dateiname steht in jeder Einbindung und
  in bereits veröffentlichten Adressen, ein echtes Verschieben zerrisse sie
  alle. Ordner und Etiketten haben getrennte Rollen: der Ordner sagt, wo eine
  Datei liegt (genau einer), das Etikett, was drauf ist (beliebig viele).

  **Fallstricke für spätere Arbeit am Modul:**

  - `uploads_meta.json` trägt jetzt zwei Karten (`alts` und `files`). Wer eine
    dritte hinzufügt, muss sie in `_uploads_meta_forget()` mit aufräumen und
    über `_uploads_meta_update()` schreiben — wer die Datei lädt, ändert und
    speichert, überschreibt zwischendurch Geschriebenes der anderen Karte.
  - `_usage_entities()` bestimmt, was „Verwendet in" kennt. Fehlt dort ein
    Bereich, meldet die Verwaltung „nirgends verwendet", obwohl das Bild
    eingebunden ist. Der **Löschschutz** hängt weiterhin an `_reference_blob()`
    und nicht an dieser Liste — ein Vergessen kostet damit keine Datei.
  - Ersetzen geht nur für `.webp`. `_store_upload_image()` schreibt immer WebP;
    in eine `.png` geschrieben, lieferte die Datei WebP-Daten unter falscher
    Endung aus.
  - Die `-ai`-Kennzeichnung steckt im Dateinamen und übersteht das Ersetzen
    deshalb. Das ist Absicht und die vorsichtige Richtung: ein gekennzeichnetes
    Bild bleibt gekennzeichnet.
  - Der Bild-Zwischenspeicher heißt jetzt `<stamm des bildes>-<schlüssel>.webp`.
    Wer das Namensschema ändert, muss `_wm_cache_forget()` und
    `_unused_wm_cache()` gleichzeitig mitziehen — sonst räumt das Aufräumen
    entweder nichts mehr weg oder die Fassungen lebender Bilder.
  - Ordner sind eine reine Anzeige-Angabe in `uploads_meta.json`, eine Ebene
    tief. Wer Unterordner nachrüstet, braucht Baum, Brotkrumen und ein
    Umbenennen ganzer Zweige — und muss `_upload_folder_clean()` ändern, das
    Schrägstriche heute absichtlich zu Leerzeichen macht.
  - Die Ordnerliste in `/api/uploads/list` kommt aus der **ganzen** Ablage,
    nicht aus den höchstens 300 gezeigten Kacheln. Wer das umstellt, lässt
    Ordner aus der Leiste verschwinden, sobald ihre Bilder jenseits der
    Kachelgrenze liegen.
  - Browser halten ein ersetztes Bild bis zu einen Tag fest (`max_age=86400` an
    der Auslieferroute). Wer das ändern will, ändert es für **alle** Bilder —
    also Ladezeit gegen Aktualität. Der Admin umgeht es über `?v=<mtime>`.

### Empfohlene Reihenfolge

7 (Cache) und 2 (Blättern) sind mit v0.11.16 erledigt. Weiter mit
1 (`srcset`, ~1 Tag) → 3 (schema.org). Erst das technische Fundament, dann die
Sichtbarkeit, dann die großen Bauten 4 und 8.

**Bewusst nicht vorgesehen:** ein Erweiterungssystem nach Art der WordPress-Plugins,
ein Shop und Mehrsprachigkeit über DE/EN hinaus. Alle drei ziehen mehr Wartung
nach sich, als sie dieser Zielgruppe bringen.
