# Backlog — MyPage

Zurückgestellte Vorhaben, die konkret genug sind, um später ohne Neuentwurf
weiterzugehen. Kein Ideen-Brainstorming — dafür ist `Ideas.md` da (Kartenspiele).

---

## Reiseblog Stufe 2 — öffentliche Darstellung

**Stand:** Stufe 1 ist fertig und live (v0.10.0–0.10.3). Reisen, Tage, Wizard, Prompt-Bau und
KI-Bericht laufen im Admin. Öffentlich ist noch nichts sichtbar.

**Was fehlt:**

- **Slugs** für Reisen und Tage, dazu ein `veröffentlicht`-Schalter je Tag — ein halbfertiger
  Tag darf nicht online stehen.
- **Routen** `/reiseblog` (Reisen), `/reiseblog/<reise>` (Tage einer Reise),
  `/reiseblog/<reise>/<tag>` (der Bericht).
- **Vorlagen**: Übersicht, Reise, Tagesbericht. Die Bibliothek (`library.html`,
  `library_entry.html`) ist die passende Bauvorlage — gleiche Struktur aus Liste und Detail,
  inklusive SEO-Meta, Mitglieder-Sperre und Bildergalerie.
- **Abschnitt auf der Startseite**: `section_defs['travel']` steht schon in `app.py`, aber mit
  `present=False`. Sobald es öffentliche Seiten gibt, auf „aktiviert und mindestens ein
  veröffentlichter Tag" umstellen — sonst ist die Sprungmarke ein Verweis ins Leere.
  Dasselbe gilt für `section_defs['forms']`.
- **Sitemap und Volltextsuche** ergänzen (siehe wie `bibliothek/...` dort eingehängt ist).
- **Ausgaben-Auswertung** je Reise wäre ein hübsches Extra, ist aber Kür.

**Fallstricke, die schon bekannt sind:**

- `_reference_blob()` in `app.py` liest site.json UND travel.json. Wer eine weitere Ablage
  hinzufügt, muss sie dort ebenfalls eintragen, sonst hält „Speicher aufräumen" die Dateien
  für verwaist und löscht sie.
- Flask lädt Vorlagen **nicht** neu — den Testserver nach jeder Änderung an `admin.html`
  oder den öffentlichen Vorlagen neu starten, sonst testet man den alten Stand.
- Neue `.py`-Dateien brauchen eine eigene `COPY`-Zeile im Dockerfile.

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
