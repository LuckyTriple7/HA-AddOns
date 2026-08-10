# Backlog — MyPage

Zurückgestellte Vorhaben, die konkret genug sind, um später ohne Neuentwurf
weiterzugehen. Kein Ideen-Brainstorming — dafür ist `Ideas.md` da (Kartenspiele).

Recherchen zu einzelnen Themen liegen in eigenen Dateien:
`INSTAGRAM.md` (Beiträge automatisch auf Instagram veröffentlichen — Wege,
Meta-Voraussetzungen, Rezept über den RSS-Feed).

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
