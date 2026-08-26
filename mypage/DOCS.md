# MyPage — Dokumentation

## Konfiguration

Seit **0.11.0** pflegst du fast alles im Admin-Panel unter **Einstellungen** — nicht mehr in den Add-on-Optionen. Vorteile: Es funktioniert genauso, wenn MyPage [ohne Home Assistant](STANDALONE.md) unter Docker läuft, und Tokens sowie Passwörter liegen **verschlüsselt** in `settings.json` statt im Klartext in `options.json`.

Beim ersten Start nach dem Update übernimmt MyPage die bisherigen Optionen automatisch in `settings.json` — du musst nichts abtippen.

### Add-on-Optionen (Home Assistant)

Hier stehen nur noch die Login-Daten. Sie bleiben bewusst in Home Assistant: Damit kommst du auch dann wieder ins Admin-Panel, wenn du dich über die Oberfläche aussperrst.

| Option | Beschreibung |
|---|---|
| `username` | Benutzername für das Admin-Panel (Direktzugriff über Port 17761) |
| `password` | Passwort für das Admin-Panel — **unbedingt ändern!** |
| `session_hours` | Gültigkeit der Login-Session in Stunden (Standard: 24) |

Die übrigen Optionen sind seit **0.11.2** aus dem Schema entfernt und tauchen in der HA-Konfigurationsseite nicht mehr auf. Beim Update von 0.11.0/0.11.1 wurden ihre Werte bereits einmalig nach `settings.json` übernommen.

### Reiter „Einstellungen" (Admin-Panel)

Gespeichert wird in `settings.json` im Add-on-Konfigurationsordner. Geheime Felder (GitHub-Token, SMTP-Passwort, Telegram-Token, SMB-Passwort, Gemini-Keys) werden mit `settings.key` verschlüsselt, im Browser nie angezeigt (nur „gesetzt"/„nicht gesetzt") und im Protokoll nur als Feldname geführt.

Der **Schlüssel liegt seit 0.11.4 nicht mehr im Konfigurationsordner**, sondern im privaten Add-on-Verzeichnis (`/data`, dort wo Home Assistant auch `options.json` hält). Grund: Der Konfigurationsordner ist über den Samba-Share einsehbar — lägen `settings.json` und `settings.key` dort nebeneinander, könnte jeder mit Share-Zugriff die Zugangsdaten entschlüsseln. Ein vorhandener Schlüssel wird beim ersten Start automatisch verschoben. Im [Standalone-Betrieb](STANDALONE.md) bleibt er bei den Daten, weil `/data` dort nur containerintern und nach einem Neuaufbau weg wäre.

* **Leeres Geheimfeld heißt „unverändert lassen"** — zum Entfernen den Knopf **Löschen** benutzen.
* Das MyPage-Backup enthält `settings.json`, aber **nicht** `settings.key`. Ein Backup verrät die Zugangsdaten also nicht. Damit ein Restore auf einer **frischen** Installation trotzdem gelingt, gibt es den Schlüssel-Export (siehe unten).

#### Schlüssel sichern

Im Reiter **Einstellungen** ganz unten. Der Export verpackt `settings.key` mit einer **Passphrase**, die du eingibst — die Datei darf deshalb neben dem Backup liegen, ohne Passphrase ist sie wertlos (scrypt zur Ableitung, 32 MB Speicher je Rateversuch).

* Vor Export **und** Import fragt MyPage das **Admin-Passwort** erneut ab, bei aktivem 2FA zusätzlich den Code. Nach fünf Fehlversuchen ist die Funktion 5 Minuten gesperrt; jeder Vorgang steht im Audit-Log.
* Die Passphrase wird nirgends gespeichert, auch nicht als Hash. Geht sie verloren, ist der Export wertlos — dann bleibt nur, die Zugangsdaten neu einzutragen.
* Beim Einspielen auf einer frischen Installation läuft der Import ohne Rückfrage durch. Liegt dagegen schon ein **anderer** Schlüssel mit nutzbaren Daten, kommt eine Warnung: Ersetzen macht die damit verschlüsselten Zugangsdaten unwiderruflich unlesbar.
* Nach dem Import meldet MyPage, wie viele Felder wieder lesbar sind.
* SMB-Felder greifen sofort, wenn beim Start schon eine Freigabe eingerichtet war — sonst erst nach einem Neustart des Add-ons (die Oberfläche sagt es).

| Einstellung | Beschreibung |
|---|---|
| `github_token` | Optional: GitHub-Token (erhöht das API-Limit für Import und Sterne-Updates) |
| `translate_email` | Optional: E-Mail für die DE↔EN-Auto-Übersetzung (MyMemory) — erhöht das kostenlose Tageslimit |
| `visit_log_max` | Größe des Besucher-Logs (50–10000, Standard 500) — Referrer/Browser/Länder/Top-Seiten werden daraus berechnet. Die **Liste im Admin zeigt immer höchstens die neuesten 500 Einträge**, auch bei größerem Wert; die übrigen fließen weiter in die Auswertungen |
| `visit_file_log` | Schreibt jeden Aufruf zusätzlich dauerhaft als CSV nach `addon_configs/XXX_mypage/visits/` (Standard: aus). Lässt sich alternativ im Admin-Reiter **Explorer** einschalten |
| `visit_file_keep` | Wie viele Monatsdateien des Besucher-Archivs behalten werden (0–120, Standard **1**; `0` = unbegrenzt). Das Archiv enthält ungekürzte IP-Adressen — höhere Werte sollten zur eigenen Datenschutzerklärung passen |
| `visit_bot_nets` | Optional: eigene IP-Netze in CIDR-Schreibweise (z. B. `194.180.48.0/24`), die zusätzlich zu den eingebauten Cloud-Netzen als Bot gelten |
| `user_journal_max` | Journal-Einträge pro Benutzer (20–1000, Standard 100) |
| `geoip_offline` | Länder-Erkennung über eine lokale IP-Tabelle (Standard: an, keine Besucher-IP verlässt das Add-on) |
| `telegram_bot_token` | Optional: Bot-Token — neue Kontaktnachrichten werden per Telegram gemeldet |
| `telegram_chat_id` | Chat-ID für die Telegram-Benachrichtigungen |
| `ha_notify` | Persistente Home-Assistant-Benachrichtigungen bei neuer Kontaktnachricht, neuem Blog-Kommentar und gesperrter IP (Brute-Force). Standard: an |
| `smtp_host` | Optional: SMTP-Server — neue Kontaktnachrichten werden per E-Mail gemeldet |
| `smtp_port` | SMTP-Port, meist 587 (STARTTLS) oder 465 (SSL) |
| `smtp_user` / `smtp_password` | Zugangsdaten für den Mailversand (App-Passwort empfohlen) |
| `smtp_from` | Optional: Absender-/Alias-Adresse (z. B. `noreply@deine-domain.de`). Leer = es wird `smtp_user` als Absender genutzt |
| `smtp_to` | Empfängeradresse der Benachrichtigungen |
| `smtp_tls` | `true` für Port 587 (STARTTLS), `false` für Port 465 (SSL) |
| `user_upload_max_mb` | Maximale Größe pro hochgeladener Datei im Mitglieder-Bereich in MB (1–4096, Standard 200) |
| `auto_backup_keep` | Anzahl automatischer Tages-Backups, die aufbewahrt werden (0–60, Standard 7). `0` schaltet die automatischen Backups ab |
| `revision_keep` | Anzahl früherer Stände der Seiteninhalte, die aufbewahrt werden (0–100, Standard 20). `0` schaltet die Stände ab |
| `smb_server` | Optional: Adresse des SMB-/CIFS-Servers für den Mitglieder-Speicher (z. B. FritzBox-NAS). Leer = lokaler Speicher im Add-on-Config-Ordner |
| `smb_share` | Name der SMB-Freigabe (z. B. `FRITZ.NAS`) |
| `smb_user` / `smb_password` | Zugangsdaten für die SMB-Freigabe |
| `gemini_api_key` | Optional: Google-Gemini-Key — schaltet den Tab **KI** und im Bibliothek-Editor den Knopf **Bild generieren** frei. Key auf [aistudio.google.com](https://aistudio.google.com) holen. **Bild- und Texterzeugung sind je nach Modell kostenpflichtig** |
| `gemini_image_model` | Startwert für die Bilderzeugung: `gemini-3.1-flash-image` (Allrounder, Standard), `gemini-3.1-flash-lite-image` (am schnellsten und günstigsten), `gemini-3-pro-image` (Premium), `gemini-2.5-flash-image` (älter). Im Tab **KI** überschreibbar |
| `gemini_image_ratio` | Startwert für das Seitenverhältnis der erzeugten Bilder (Standard `16:9`). Im Tab **KI** überschreibbar |

## Ports

| Port | Zweck |
|---|---|
| `17760` | Öffentliche Homepage — **kein Login**, diesen Port veröffentlichen |
| `17761` | Admin-Panel — Login-geschützt, möglichst nicht öffentlich freigeben |

Über die HA-Seitenleiste (Ingress) ist das Admin-Panel ohne zusätzlichen Login erreichbar — die Authentifizierung übernimmt dann Home Assistant.

## Admin-Panel

### Profil
Name, Kurzbeschreibung (Tagline), „Über mich"-Text, Profilbild, GitHub-Benutzername, E-Mail und beliebige weitere Links. Tagline und Bio gibt es jeweils in **DE und EN** — fehlt eine Sprache, wird automatisch die andere angezeigt.

### Inhalte
Der Tab **Inhalt** zeigt alle Startseiten-Bereiche als einklappbare Karten (Akkordeon). Jede Karte hat links einen **Griff (⠿)** und ein **Auge-Symbol**:

- **Reihenfolge:** Am Griff per **Drag & Drop** sortieren (Maus + Touch) — die Startseite übernimmt die Reihenfolge sofort. Der Kopfbereich bleibt immer oben, das Kontaktformular immer unten. Auch **Projekte**, **Blog** und **Bibliothek** lassen sich hier positionieren (bearbeitet werden sie in ihren eigenen Tabs).
- **Sichtbarkeit:** Mit dem Auge blendest du einen Bereich von der Startseite (und der Navigation) aus, ohne seinen Inhalt zu löschen.

Verfügbare Bereiche:

- **Countdown**: zählt sichtbar auf ein Zieldatum/-zeit herunter (z. B. Eröffnung, Launch, Veranstaltung) — Kacheln für Tage/Stunden/Minuten/Sekunden im Karten-Stil mit Akzentfarbe, optionaler Überschrift, Untertitel und Bild darüber. Bei Ablauf erscheint ein frei wählbarer „Es ist soweit!"-Text. Optional ein **„Benachrichtige mich"-Button**, über den Besucher ihre E-Mail fürs Newsletter-Abo hinterlegen (benötigt aktiven Newsletter). Leeres Zieldatum = Abschnitt aus. Ist ein Countdown eingerichtet, erscheint er **auch auf der Wartungs-/„Seite im Aufbau"-Seite** (siehe Wartungsmodus) — ideal als Coming-Soon-Seite; das Newsletter-Abo funktioniert dort trotz Wartungsmodus.
- **Skills**: kommagetrennte Liste, wird als Chips angezeigt
- **Leistungen**: Angebote/Dienstleistungen als Karten mit Symbol (Emoji), Beschreibung (DE/EN) und optionalem Preis
- **Referenzen**: Kundenstimmen mit Zitat (DE/EN), Name, Funktion und optionalem Foto
- **Team**: Personen mit Foto, Funktion (DE/EN) und Kurzbeschreibung
- **Aktuelles**: kurze News-Einträge mit Datum und optionalem Link
- **Werdegang**: Timeline mit Zeitraum, Titel und Text (jeweils DE/EN)
- **Veranstaltungen**: kommende Termine mit Datum, Titel (DE/EN), Ort und optionalem Link
- **Standort & Öffnungszeiten**: Adresse, Öffnungszeiten (DE/EN) und optional eine Karte. Die Karte nutzt **OpenStreetMap** und lädt **erst auf Klick** (datenschutzfreundlich); zusätzlich gibt es einen „Auf Karte öffnen"-Link. Für die eingebettete Karte optional Koordinaten (Breite, Länge) angeben.
- **Linksammlung**: Links zu anderen Seiten mit Titel und Beschreibung (DE/EN). Auf der Startseite erscheint ein Button, der ein Overlay mit allen Links öffnet; ein Klick öffnet die Zielseite in einem neuen Tab.
- **FAQ**: Fragen und Antworten (DE/EN, Antwort als Markdown), auf der Startseite als aufklappbare Liste
- **Bibliothek**: Anriss der Sammlung (bis zu 12 Einträge, Darstellung wählbar — Karussell, Bildkacheln, Mini-Karten, Liste oder Klappzeile —, mit Schlagwort-Filter) — Inhalt und Name werden im eigenen Tab *Bibliothek* gepflegt (siehe unten)
- **Fotoalben**: Alben mit Titel/Beschreibung (DE/EN) und beliebig vielen Bildern (Mehrfach-Upload). Ein Klick öffnet eine Diashow mit Ausblend-Effekt und Autoplay; ein **Klick auf das Bild** zeigt es groß, ein weiterer Klick in voller Auflösung (scroll-/schwenkbar). Bilder werden automatisch auf max. 1600 px verkleinert und als WebP gespeichert. Die Bild-Reihenfolge lässt sich per **Drag & Drop** ändern; ein Klick auf eine Mini-Kachel im Admin zeigt eine Vorschau.
  - **Bildschutz** (Schalter „Bilder schützen"): Brennt ein Wasserzeichen (frei wählbarer Text, Standard `© deine-domain.de`) in alle **Album- und Bibliothek-Bilder** ein und deaktiviert in den Alben Rechtsklick/Ziehen. Das Wasserzeichen wird beim Ausliefern dynamisch erzeugt und gecacht, eine Textänderung greift sofort. Ein vollständiger Download-Schutz ist im Web technisch nicht möglich (Screenshots), das Wasserzeichen ist der wirksame Teil. Siehe auch [Kennzeichnung von KI-Bildern](#kennzeichnung-von-ki-bildern).

### Markdown-Editor
Alle Markdown-Textfelder (Blog-Beiträge, eigene Seiten, Bibliothek-Einträge und -Einleitung, Projekt-Details, Bio, Freitext-Abschnitt, Newsletter, Formular-Einleitung & -Danke-Text, Tipps, FAQ-Antworten, Impressum & Datenschutz, Wartungsmodus-Text, Login-Nachricht je Benutzer, Standort-Öffnungszeiten, KI-Textausgabe) bieten über den Button **„✏️ Bearbeiten"** einen **Markdown-Editor mit Werkzeugleiste und Live-Vorschau**: Fett, Kursiv, Überschrift, Aufzählung, nummerierte Liste, Zitat, Code, **Link**, **Bild**, **Tabelle**, **Trennlinie** und Emoji. Beim **Bild** kannst du eine URL eingeben oder das Feld leer lassen — dann öffnet sich der **Medien-Browser** mit allen bereits hochgeladenen Bildern (siehe [Bilder](#bilder)), aus dem heraus sich auch ein neues hochladen lässt (wird automatisch auf max. 1600 px verkleinert, als WebP gespeichert und um Metadaten/GPS bereinigt). Tabellen und Codeblöcke werden auf der öffentlichen Seite korrekt dargestellt. Ob ein Feld den Editor bekommt, steht am Feld selbst — neue Wiederholfelder (FAQ, Tipps) bekommen ihn beim Anlegen der Zeile automatisch.

### Projekte
- **GitHub-Import**: Benutzernamen eingeben → „Repos laden" → Repos anhaken → importieren. Forks werden ausgeblendet, bereits importierte Repos sind ausgegraut. Sterne-Zahlen importierter Projekte werden stündlich automatisch aktualisiert.
- **Manuell**: Projekte mit Titel, Beschreibung (DE/EN), Bild, Demo-Link, GitHub-Link, Tags und Sprache anlegen.
- **Detailseiten**: Mit Detailtext (Markdown) oder Galerie-Bildern bekommt ein Projekt eine eigene Unterseite (`/p/<id>`), die automatisch von der Karte verlinkt wird.
- Reihenfolge per ↑/↓-Buttons ändern.

### Nachrichten
Das Kontaktformular (im Design-Tab aktivierbar) speichert Nachrichten im Tab „Nachrichten". Spam-Schutz dreifach: unsichtbares Honeypot-Feld, ein einfaches Rechen-Captcha („7 + 3 = ?", selbst gehostet, kein externer Dienst) und Rate-Limit (5 Nachrichten/Stunde pro IP). Benachrichtigungen bei neuen Nachrichten wahlweise per **Telegram** (Bot-Token + Chat-ID), **E-Mail** (SMTP-Optionen) und/oder als **Home-Assistant-Benachrichtigung** (`ha_notify`).

Im selben Tab werden unter **„Blog-Kommentare"** alle Mitglieder-Kommentare zur Moderation gelistet (mit Beitragstitel, verlinkt zur Vorschau). Einzelne Kommentare lassen sich per ✕ entfernen.

### Blog
Beiträge mit Datum, Titel und Markdown-Text (DE/EN). Liste unter `/blog`, einzelne Beiträge unter `/blog/<id>`, die neuesten drei erscheinen auf der Startseite. Jeder Beitrag zeigt neben dem Datum eine geschätzte **Lesezeit** (≈200 Wörter/Min). Optional je Beitrag ein Titelbild, ein Video-Embed (YouTube/Vimeo, datenschutzfreundlich erst auf Klick) und eine **Bild-Galerie** (horizontal scrollbar mit Pfeilen). Ein Klick auf ein Bild öffnet es groß, ein weiterer in voller Auflösung.

- **Schlagwörter (Tags)**: Pro Beitrag bis zu 8 Tags (komma-getrennt). Auf der Blog-Seite gibt es **Tag-Filter-Chips**; auf jeder Beitragsseite verlinken die Tags zur gefilterten Ansicht.
- **Ähnliche Beiträge**: Unter jedem Beitrag erscheinen bis zu drei verwandte Beiträge, ermittelt über **gemeinsame Schlagwörter** (sortiert nach Anzahl gemeinsamer Tags und Datum). Ohne Tags oder ohne Verwandte bleibt der Block aus; bei Mitglieder-only-Anrissen wird nichts angezeigt.
- **Aufrufe je Beitrag**: Jeder Blog-Beitrag zählt seine Aufrufe (ohne Bots). Die Zahl steht im Admin in der Beitragsliste und erscheint dezent (👁) auf der Beitragsseite. Die Zähler liegen in `stats.json` (im Backup).
- **Suche**: Ein Suchfeld auf `/blog` durchsucht Titel, Text und Tags (DE+EN). Suche und Tag-Filter lassen sich kombinieren. Entwürfe und geplante Beiträge bleiben außen vor.
- **Newsletter / Blog-Abo** (im Design-Tab aktivierbar, Standard aus): Auf der Blog-Seite erscheint ein Abo-Feld. Besucher tragen ihre E-Mail ein und bestätigen das Abo per Link (**Double-Opt-in**). Im Blog-Tab schreibst du dann eine Nachricht (Betreff + Markdown) und sendest sie per Klick an alle **bestätigten** Abonnenten — jede Mail enthält einen **Abmelde-Link**. Du siehst die Abonnentenzahl und kannst einzelne entfernen. Schutz: Honeypot + Rate-Limit, keine E-Mail-Enumeration. Benötigt SMTP + öffentliche URL; die Liste liegt in `subscribers.json` (im Backup).
- **Teilen-Buttons** (im Design-Tab über „Teilen-Buttons" aktivierbar, Standard aus): Unter jedem Beitrag **und auf Projekt-Detailseiten** erscheinen Buttons zum Teilen via **WhatsApp, X, Facebook, LinkedIn, E-Mail** sowie **Link kopieren** (und auf Mobilgeräten der native Teilen-Dialog). Reine Links — kein Tracking-Skript, es wird nichts nachgeladen.
- **Kommentare & Reaktionen** (im Design-Tab über „Kommentare & Reaktionen" aktivierbar, Standard aus): **Angemeldete Mitglieder** können Beiträge kommentieren und mit Emoji reagieren (👍 ❤️ 😄 🎉 👏 — eine Reaktion pro Person, per Klick umschaltbar). Gäste sehen die Reaktionsleiste ausgegraut mit einem Hinweis zum Anmelden. Mitglieder können auf Kommentare **antworten** (Antwort-Threads, eine Ebene tief); wird ein Mailserver genutzt, bekommt der Autor des beantworteten Kommentars eine **Benachrichtigung per E-Mail** (nicht bei Selbstantwort). Moderiert wird im Tab **Nachrichten** (siehe unten); bei neuen Kommentaren kommt zusätzlich eine Home-Assistant-Benachrichtigung. Kommentare/Reaktionen liegen in `comments.json` und werden im Backup mitgesichert.

### Seiten
Eigenständige Unterseiten neben Startseite und Blog — z. B. **„Über uns"**, **„Anfahrt"** oder **„Vereinsordnung"**. Jede Seite hat eine eigene Adresse unter `/seite/<slug>` und Inhalt in **Markdown** (DE/EN, gleicher Editor wie beim Blog, mit Live-Vorschau).

- **Adresse (Slug)**: Frei wählbar (Kleinbuchstaben, Ziffern, Bindestriche). Leer gelassen, wird sie automatisch aus dem Titel erzeugt. Reservierte und bereits vergebene Adressen werden automatisch umgangen (z. B. `ueber-uns-2`).
- **In der Navigation zeigen**: Schalter je Seite — sichtbare Seiten mit aktiviertem Schalter erscheinen als Link in der Navigationsleiste (auf der Startseite und auf den Seiten selbst).
- **Status**: „Veröffentlicht" oder „Entwurf". Entwürfe sind öffentlich nicht erreichbar (404), lassen sich im Admin aber über **Vorschau** ansehen.
- **Reihenfolge**: Per **Drag & Drop** in der Seitenliste sortieren.
- **SEO**: Veröffentlichte Seiten landen automatisch in `sitemap.xml` und im statischen Export; optional je Seite eine eigene Meta-Beschreibung. Die Seiten liegen in `site.json` (im Backup).

### Bibliothek
Eine Sammlung eigenständiger **Markdown-Dokumente mit Kategorien** — für alles, was weder ein Blog-Beitrag (chronologisch) noch eine einzelne Seite ist: Reiseführer, Kochrezepte, Anleitungen, Handbücher. Übersicht unter `/bibliothek`, Einzeleintrag unter `/bibliothek/<slug>`.

- **In der Navigation zeigen** (Schalter im Tab *Bibliothek*): Blendet die Sammlung als Eintrag in der Navigationsleiste ein — auf der Startseite als Sprung zum Abschnitt, auf Unterseiten als Link auf `/bibliothek`. Aus heißt: kein Navi-Eintrag; erreichbar bleibt die Übersicht über „Zur Übersicht →" unter dem Startseiten-Abschnitt und über die Adresse selbst. Ohne veröffentlichte Einträge erscheint ohnehin nichts.
- **Name frei wählbar**: Der Anzeigename der Sammlung wird im Tab *Bibliothek* gesetzt (DE/EN). Leer gelassen heißt sie „Bibliothek" — trägst du „Reiseführer" ein, heißt sie überall so (Navigation, Startseiten-Abschnitt, Suchergebnisse). Dazu optional eine **Einleitung** (Markdown), die über der Übersicht steht.
- **Kategorien**: frei anlegbar, je mit Name (DE/EN) und optionalem Emoji, per Drag & Drop sortierbar. Auf der Übersicht erscheinen sie als **Filter-Chips**. Eine gelöschte Kategorie nimmt ihre Einträge nicht mit — die rutschen nur in „ohne Kategorie".
- **Einträge**: Titel, Kurzbeschreibung, Titelbild, bis zu 8 Schlagwörter (erscheinen auf der Übersicht als **Filter-Chips**, kombinierbar mit Kategorie und Suche), Text in **Markdown** (DE/EN, gleicher Editor mit Live-Vorschau wie im Blog), eigene SEO-Beschreibung, Adresse (Slug, leer = automatisch aus dem Titel), Status *Veröffentlicht/Entwurf* und der Schalter **Nur für Mitglieder** (Gäste sehen dann nur einen Anriss). Reihenfolge per Drag & Drop; **Vorschau** zeigt auch Entwürfe. **Kopieren** dupliziert einen Eintrag samt PDF-Einstellung als Entwurf — praktisch für Einträge nach gleichem Muster.
- **Titelbild von der KI erzeugen lassen** (nur wenn `gemini_api_key` gesetzt ist): Neben dem Bild-Feld erscheint **✨ Bild generieren**. Der Knopf öffnet ein Feld mit einer **vorgeschlagenen Bildbeschreibung aus Titel, Kategorie, Schlagwörtern und Kurzbeschreibung** des Eintrags — trägt der Eintrag das Schlagwort „Rhodos", steht es im Vorschlag und das Bild passt dazu. Die Beschreibung ist frei änderbar; „Erzeugen" dauert etwa 10–60 Sekunden. Das fertige Bild wird auf max. 1600 px verkleinert, als WebP abgelegt und **sofort als Titelbild eingetragen** — gespeichert ist der Eintrag damit noch nicht, dazu braucht es „Speichern". Modell und Seitenverhältnis stehen in den App-Optionen; höchstens 20 Bilder pro Stunde. Lehnt die KI eine Beschreibung ab, sagt der Admin das und du kannst sie umformulieren.
- **PDF je Eintrag** — drei Möglichkeiten:
  - *Kein PDF*: Besucher können die Seite trotzdem über den **Druck-Knopf** als PDF speichern. Die Eintragsseite bringt ein eigenes Druck-Stylesheet mit (ohne Navigation, Fußzeile und Knöpfe, Links werden ausgeschrieben).
  - *Aus dem Text erzeugen*: Beim Speichern rendert das Add-on ein PDF aus dem Markdown — mit Titelkopf, Seitenzahlen, Tabellen und Code-Blöcken — und bietet es zum Download an. Währenddessen läuft oben ein **Banner mit Spinner**; danach meldet es grün „PDF erzeugt." oder rot den Grund. Der Speichern-Knopf ist so lange gesperrt. Unveränderte Einträge werden nicht neu gerendert (Zwischenspeicher über einen Fingerabdruck des Quelltexts). Braucht `weasyprint`; fehlt es, sagt der Admin das und die anderen beiden Wege funktionieren weiter.
  - *Eigenes PDF hochladen*: max. 25 MB. Die Datei wird am Dateikopf geprüft, nicht nur an der Endung.
- **Auslieferung der PDFs**: Sie liegen in einem eigenen Ordner (`docs/`, im Backup) und kommen **ausschließlich** über `/bibliothek/<slug>.pdf` als **Datei-Download** (`Content-Disposition: attachment`, `nosniff`) — nie inline über die offene `/uploads/`-Route. Bei Mitglieder-Einträgen ist auch das PDF gesperrt.
- **Startseite**: Die Bibliothek ist ein eigener Abschnitt — bis zu 12 Einträge als **seitwärts scrollendes Karussell** (wie die Fotoalben, mit Pfeilen und Touch-Wischen). Darüber steht eine **Schlagwort-Leiste**, die die Kacheln ohne Neuladen filtert, darunter der Link **„Zur Übersicht →"** auf `/bibliothek` (er übernimmt ein gewähltes Schlagwort). Ist der Abschnitt ausgeblendet oder auf Mitglieder beschränkt, erscheint die Sammlung stattdessen als echter Link in der Navigation. Der Abschnitt lässt sich im Tab *Inhalt* wie jeder andere sortieren, ausblenden oder auf Mitglieder beschränken.
- **Darstellung auf der Startseite** (Auswahl im Tab *Bibliothek*): Der Abschnitt frisst mit großen Bildkarten viel Höhe — deshalb fünf Varianten, alle mit derselben Schlagwort-Leiste und demselben Übersichts-Link:
  - *Große Karten (Karussell)* — Bild, Kategorie, Titel und Zusammenfassung untereinander (Standard, wie bisher).
  - *Bildkacheln mit Titel im Bild* — Titel liegt auf dem Bild statt darunter, Karte gut halb so hoch.
  - *Kleine Karten mit Bild links* — Karte quer, Vorschaubild links neben dem Titel.
  - *Liste* — kein Karussell: eine Zeile je Eintrag mit kleinem Vorschaubild, alle Einträge auf einen Blick.
  - *Klappzeile* — eine Zeile mit Name und Anzahl, das Karussell öffnet sich erst auf Klick.
- **SEO**: Veröffentlichte Einträge landen in `sitemap.xml`, im **IndexNow-Ping**, in der Volltextsuche und im statischen Export (dort inklusive der PDF-Dateien). Jede Eintragsseite liefert strukturierte Daten (`schema.org/Article`). Alle Inhalte liegen in `site.json` (im Backup).

### KI
Der Tab bündelt alles, was mit Google Gemini erzeugt wird. Ohne `gemini_api_key` bleibt davon nur der **Logo-Designer** sichtbar — der rechnet selbst und braucht keinen Schlüssel, solange man ihm ein eigenes Bild gibt.

- **Einstellungen**: Text- und Bildmodell, Seitenverhältnis und der Übersetzungsdienst. Die Modell-Listen werden **live bei Google abgefragt** (stündlich zwischengespeichert) — neue Modelle stehen also ohne Add-on-Update zur Auswahl. Was hier gespeichert wird, **überschreibt die App-Optionen** `gemini_image_model` und `gemini_image_ratio`; ein Modellwechsel braucht damit keinen Neustart. Darunter steht das verbrauchte Stundenkontingent.
- **Immer beachten (Dauervorgaben)**: ein Feld unter den Einstellungen, dessen Inhalt bei **jedem** Textlauf mitgeht — auch beim Überarbeiten. Gedacht für das, was man sonst in jedes Thema tippt: „Leser duzen", „keine Emojis", „Produktname immer als MyPage schreiben". Höchstens 800 Zeichen; leer lassen schaltet es ab. Die Vorgabe steht in der Systemanweisung, ändert also nichts an der Form der Antwort.
- **Übersetzung**: `MyMemory` (kostenlos, ohne Schlüssel — Standard) oder `Gemini` (deutlich bessere Qualität, verbraucht Kontingent). Die Wahl gilt für **alle 🌐-Knöpfe im Admin**. Scheitert Gemini, übernimmt automatisch MyMemory — eine schlechtere Übersetzung ist besser als keine.
- **🌐 Übersetzen** (eigener Bereich im Tab): Was die 🌐-Knöpfe in den Formularen nicht können — **freier Text** und **beide Richtungen**. Oben wählt man **Eintrag** und **Feld**: „freie Eingabe" oder einen vorhandenen Blogbeitrag, ein Projekt, einen Bibliothek-Eintrag oder eine Seite, daneben das Feld. Vorbelegt ist der **Fließtext**; Titel und SEO-Beschreibung stehen in derselben Auswahl. „Laden" holt die Fassung in der **Ausgangssprache** — bei „Englisch → Deutsch" also die englische. **„⇅ Richtung tauschen"** dreht Richtung und Texte für die Gegenprobe.
  - **Zurückgeschrieben wird nichts.** Das Ergebnis steht unten zum Kopieren; das Original bleibt unangetastet. Wer die Übersetzung direkt im Beitrag haben will, nimmt weiter den 🌐-Knopf im jeweiligen Formular (der füllt nur leere EN-Felder, DE→EN).
  - Übersetzt wird über denselben Anbieter wie überall — welcher gerade aktiv ist, steht unter der Auswahl. Der Bereich ist **auch ohne Gemini-Schlüssel da**, weil MyMemory keinen braucht. Mit Gemini zählt jede Übersetzung aufs Textkontingent. Höchstens 20.000 Zeichen pro Durchgang.
- **Bild-Studio**: Beschreibung eingeben, optional einen **Stil anhängen** (Fotorealistisch, Illustration, Flat/Vektor, 3D-Render, Aquarell, Retro) und **bis zu 4 Entwürfe** auf einmal erzeugen. Ein **Vorlagenbild** aus den eigenen Uploads wandelt ein vorhandenes Bild ab, statt neu zu erfinden (nur eigene Uploads, keine Fremd-URLs).
  - Entwürfe liegen zunächst **nur zwischengespeichert** auf dem Server und sind nicht öffentlich abrufbar. Erst **„Speichern"** legt einen Entwurf in den Uploads ab — verkleinert auf 1600 px, als WebP, ohne Metadaten und mit der [KI-Kennzeichnung](#kennzeichnung-von-ki-bildern). Nicht gespeicherte Entwürfe **verfallen nach einer Stunde**; „Verwerfen" löscht sofort. So wächst die Bildersammlung nicht mit jedem Fehlversuch.
  - Die Ergebnisse stehen in einem **waagerechten Streifen** mit Pfeilen — alle Entwürfe der Sitzung bleiben zum Vergleich stehen, ohne die Seite immer weiter nach unten zu schieben. Die Zeile darunter sagt, wie viele es sind und wie viele davon schon gespeichert wurden. Beim Neuladen der Seite ist der Streifen leer.
  - Das **Seitenverhältnis** steht direkt neben „Anzahl" und gilt für den nächsten Lauf. Beide Stellen — hier und in den Einstellungen — zeigen immer denselben Wert; **dauerhaft gespeichert** wird er nur oben über „Speichern".
  - **„↺ Zurücksetzen"** leert Beschreibung, Anzahl und Vorlagenbild und stellt das Seitenverhältnis auf den gespeicherten Wert zurück. Der Ergebnis-Streifen bleibt stehen — gelöscht wird nichts.
  - **„↻ Variation"** an einem gespeicherten Bild setzt es als Vorlage und startet sofort einen neuen Lauf mit derselben Beschreibung — der Weg über „Als Vorlage", Hochscrollen und „Erzeugen" entfällt. Nur an gespeicherten Bildern: ein Entwurf hat noch keine Adresse, die als Vorlage taugt.
  - **Prompt-Bibliothek**: **„💾 Prompt speichern"** legt Beschreibung, Anzahl, Seitenverhältnis und Vorlagenbild unter einem Namen ab — ein guter Prompt ist Arbeit und war bisher nach dem Neuladen weg. Ohne Namen werden die ersten Wörter genommen; **derselbe Name überschreibt** den Eintrag, statt eine zweite Zeile anzulegen. **„📂 Übernehmen"** füllt das Studio damit wieder, gestartet wird erst mit „Erzeugen". Gespeichert in `ai_prompts.json` (höchstens 100 Einträge, ältester fliegt raus), **im Backup enthalten**. Ein dort hinterlegtes Vorlagenbild gilt als benutzt und wird von „Speicher aufräumen" **nicht** gelöscht.
  - Gespeicherte Bilder stehen anschließend überall im Medien-Browser („Bild wählen") bereit. Gefällt eins doch nicht, löscht **„🗑 Löschen"** die Datei wieder. Ist das Bild bereits irgendwo eingebunden, verweigert das Add-on den Löschvorgang — sonst risse der betroffene Beitrag oder Eintrag ein Loch.
- **Logo-Designer**: Erzeugt fertige **Logo-Sätze in exakten Pixelmaßen** — für Home-Assistant-Add-ons, PWAs, Favicons und Link-Vorschaubilder. Gedacht für alles, was ein Icon in mehreren Größen braucht und nicht auf die Homepage soll.
  - **Warum ein eigener Ordner:** Logos landen **nicht** in den Uploads, sondern unter `logos/<name>/` im Add-on-Konfigurationsordner — erreichbar über den Share als `\\<host>\addon_configs\XXX_mypage\logos\<name>\`. In den Uploads würde aus jedem Logo ein WebP mit höchstens 1600 px **und** der eingebrannten [KI-Kennzeichnung](#kennzeichnung-von-ki-bildern); beides macht ein Logo unbrauchbar. Die Herkunft steht stattdessen unsichtbar in den **PNG-Textfeldern** und im mitgeschriebenen `prompt.txt`.
  - **Zielformate** (mehrere gleichzeitig wählbar, dazu ein freies Maß von 16 bis 4096 px):

    | Vorlage | Dateien |
    |---|---|
    | Home-Assistant-Add-on | `icon.png` 256×256, `logo.png` 250×100 |
    | PWA / App-Symbol | `icon-192.png`, `icon-512.png`, `apple-touch-icon.png` 180×180 |
    | Favicon | `favicon.ico` (16/32/48 in einer Datei), `favicon-32.png` |
    | Vorschaubild für Links | `og-image.png` 1200×630 |

  - **Die Maße rechnet MyPage, nicht die KI.** Gemini kennt nur Seitenverhältnisse. Der Entwurf entsteht deshalb immer quadratisch und wird je Ziel zugeschnitten und eingepasst — mittig, mit erhaltenem Seitenverhältnis. Die unveränderte Vorlage bleibt als `source.png` liegen, damit sich weitere Größen später **ohne neuen KI-Aufruf** nachziehen lassen („↻ Größen neu rechnen").
  - **Hintergrund freistellen** (Standard an): Der Prompt verlangt einen einfarbigen weißen Grund, danach entfernt das Add-on den **vom Bildrand aus zusammenhängenden** Hintergrund und macht ihn durchsichtig. Geschlossene Flächen im Motiv — das Auge eines Maskottchens, die Fläche in einem „O" — bleiben erhalten. Wie ähnlich der Grund sein darf, ist in vier Stufen einstellbar. Wirkt gut bei flachen Logos, bei Verläufen und Fotos eher nicht.
  - **Ohne KI nutzbar:** „⬆ Eigenes Bild einlesen" schickt ein vorhandenes Bild durch dieselbe Aufbereitung — praktisch, um zu einem längst gezeichneten Icon die fehlenden Größen nachzuziehen. Je größer die Vorlage, desto besser; kleiner als das größte Ziel wird sie hochgerechnet.
  - **„↺ Zurücksetzen"** setzt Beschreibung, Anzahl, Name, freies Maß, Zielformate und Freistellen auf den Ausgangszustand. Entwürfe im Streifen und fertige Logo-Sätze bleiben unangetastet.
  - **Vorhandene Sätze** stehen zusammengeklappt da — je Satz eine Zeile mit Name, Dateizahl und den Knöpfen. Ein Klick auf den Namen zeigt die Vorschaubilder, ein zweiter versteckt sie wieder. Frisch erzeugte oder neu gerechnete Sätze klappen von selbst auf.
  - **Herausholen:** entweder direkt aus dem Ordner auf dem Share, per Klick auf den Dateinamen als Einzeldownload oder als **ZIP über den ganzen Satz**. Logo-Sätze sind **Teil des Backups**.
- **Text-Studio**: Aus Thema und Stichpunkten entstehen **Titel, SEO-Beschreibung, Fließtext (Markdown) und Schlagwörter**. Einstellbar sind Textart (Blogartikel, Kurzmeldung, Projektbeschreibung, Bibliothek-Zusammenfassung, nur SEO), Tonfall und Länge.
  - **Sprachen**: nur DE, nur EN oder **DE + EN in einem Durchgang**. Bei beiden Sprachen wird entweder jede Fassung **eigenständig geschrieben** (idiomatischer) oder die englische **aus der deutschen übersetzt** (gleiche Gliederung). Beide Fassungen entstehen in **einem** Aufruf.
  - Das Ergebnis ist vor der Übernahme frei editierbar. **„Titelbild dazu vorbereiten"** füllt das Bild-Studio mit einer aus Titel, Schlagwörtern und SEO-Text gebauten Beschreibung.
  - **Vorhandenen Text ins Studio holen**: Die Auswahl ganz oben listet alle **Blogbeiträge, Projekte und Bibliothek-Einträge**; „Laden" füllt damit die Ergebnisfelder. Gedacht zum Überarbeiten, Nachübersetzen oder SEO-Nachtragen, ohne abzutippen. Das Original bleibt unangetastet, bis man es über „Übernehmen" zurückschreibt — dabei entsteht ein **neuer** Eintrag, der alte wird nicht ersetzt. Nicht ganz verlustfrei: ein **Projekt hat nur einen Titel** für beide Sprachen, der steht danach in beiden Titelfeldern.
  - **Überarbeiten statt neu erzeugen**: unter dem Ergebnis stehen **„✂ Kürzer"**, **„➕ Länger"** und **„✨ Feinschliff"**, dazu ein freies Feld für einen eigenen Änderungswunsch („Einleitung kürzen", „Beispiel mit Home Assistant ergänzen"). Der vorhandene Text geht dabei mit in die Anfrage und kommt vollständig überarbeitet zurück — die Handarbeit an den Feldern ist also nicht verloren. Über die Auswahl daneben lässt sich **eine einzelne Sprache** überarbeiten; die andere Fassung bleibt unangetastet und der Lauf kostet nur die Hälfte. **„↶ Vorherige Fassung"** holt den Stand vor dem letzten Überschreiben zurück — eine Stufe, derselbe Knopf führt auch wieder vorwärts. Sie lebt nur in der geöffneten Seite: nach einem Neuladen ist sie weg.
  - **Übernehmen richtet sich nach der Textart.** Bei *Blogartikel* und *Kurzmeldung* öffnet **„Als Blogbeitrag übernehmen"** den Beitrags-Dialog **als Entwurf**. Bei *Projektbeschreibung* steht stattdessen **„Als Projekt übernehmen"** vorn (SEO-Beschreibung → Kurzbeschreibung, Fließtext → lange Beschreibung, unveröffentlicht), bei *Bibliothek-Zusammenfassung* **„Als Bibliothek-Eintrag übernehmen"** (unsichtbar geschaltet) und bei *nur SEO* **„In die Website-SEO übernehmen"** — das trägt die Beschreibung in beide Felder im Design-Tab ein und springt dorthin; **gespeichert wird sie dort erst mit „Speichern"**. Der Weg zum Blogbeitrag bleibt daneben immer offen. Veröffentlicht wird auf keinem Weg automatisch.
  - **Entwürfe speichern**: **„💾 Entwurf speichern"** legt Ergebnis *und* Eingaben (Thema, Textart, Tonfall, Länge, Sprachen) ab — ein geladener Entwurf lässt sich also ohne Abtippen neu erzeugen. Ohne Namen wird der Titel genommen. Unter **„Gespeicherte Entwürfe"** stehen alle Einträge mit Textart, Sprachen, Zeichenzahl und Datum; **„Öffnen"** lädt alles zurück ins Studio, **„Löschen"** entfernt den Eintrag. Ab fünf Entwürfen erscheinen darüber ein **Suchfeld** (Name und Textart) und die **Sortierung** (neueste, älteste, Name A–Z) — beides reine Anzeige, ohne weiteren Aufruf. Solange ein Entwurf geöffnet ist, **überschreibt** Speichern ihn — „✕ Lösen" beendet das, danach entsteht beim nächsten Speichern ein neuer Eintrag. **„↺ Zurücksetzen"** neben „Text erzeugen" leert das ganze Formular samt Ergebnis und beginnt von vorn — gespeicherte Entwürfe bleiben davon unberührt. Gespeichert wird in `ai_drafts.json` (höchstens 200 Entwürfe, ältester fliegt raus), **im Backup enthalten**. Ein Entwurf ist nichts Öffentliches: er taucht weder im Blog noch in der Suche auf, bis er als Beitrag übernommen und dort veröffentlicht wird.
- **Limits**: 20 Bilder und 60 Textanfragen pro Stunde, add-on-weit. Sie schützen das Kontingent bei Google; jeder Entwurf zählt einzeln, ein Fehlversuch ebenfalls.
- **Kostenschätzung vor dem Lauf**: Unter jedem Erzeugen-Knopf steht, was der nächste Lauf ungefähr kostet — im Bild-Studio und im Logo-Designer „≈ 0,16 $ für 4 Bilder" (Listenpreis je Bild in 1K, größere Auflösungen kosten mehr), im Text-Studio eine grobe Schätzung mit **genannter Annahme** („bei rund 800 Wörtern Ausgabe"): abgerechnet wird nach Tokens, und die kennt vorher niemand. Gerechnet wird mit denselben Preisen wie im Verbrauchs-Bereich — eigene Werte schlagen die Vorgaben. Ohne hinterlegten Preis steht dort der Hinweis statt einer Zahl.
- **Verbrauch**: Jede Anfrage wird nach **Monat und Modell** festgehalten — Aufrufe, erzeugte Bilder sowie Ein- und Ausgabe-Tokens direkt aus der Antwort von Google (Denk-Tokens zählen zur Ausgabe). Abgelehnte und leere Antworten werden mitgezählt, denn sie kosten die Eingabe genauso. Gespeichert in `ai_usage.json`, 24 Monate, im Backup enthalten.
  - **Preise sind für bekannte Modelle hinterlegt** (Listenpreise von Google, USD je Mio. Tokens bzw. je Bild) und stehen grau als Platzhalter im Feld — sie werden gerechnet, ohne dass du etwas tun musst. Eintragen musst du nur, wo kein Platzhalter steht oder dein Tarif abweicht; ein eingetragener Wert schlägt die Vorgabe immer.
  - Die Tabelle ist **bewusst nicht vollständig**: Google benennt Modelle laufend um, und ein geratener Preis wäre schlimmer als eine leere Zeile. Die Spalte rechts sagt je Modell, ob gerade *Vorgabe*, *eigener Wert* oder *kein Vorgabepreis* gilt.
  - **„Preise bei Google abfragen“** erscheint nur, wenn die Option `gemini_billing_key` gesetzt ist. Der Knopf liest den Preiskatalog von Google Cloud und trägt die Treffer in die Felder ein — gespeichert wird erst mit „Speichern“, denn Google beschreibt seine Posten im Fließtext („Gemini 2.5 Flash Input Tokens“) und die Zuordnung zum Modell ist geraten.
  - **Warum ein zweiter Schlüssel:** der Gemini-Key aus AI Studio ist auf die Generative Language API beschränkt und wird vom Preiskatalog mit `API_KEY_SERVICE_BLOCKED` abgewiesen. Der zweite Schlüssel muss aus einem Google-Cloud-Projekt stammen, in dem die **Cloud Billing API** freigeschaltet ist. Fehlt er, bleibt der Knopf weg und du pflegst die Preise von Hand — für die üblichen Modelle sind sie ohnehin hinterlegt.
  - **Es bleibt eine Schätzung.** Maßgeblich ist die Abrechnung bei Google — Freikontingente, Rundungen und Preisänderungen kennt das Add-on nicht. Ein Zugriff auf die echten Kosten ist mit dem Gemini-Key nicht möglich: der berechtigt nur zum Modellaufruf, Abrechnungsdaten liegen hinter der Cloud Billing API mit eigenem Dienstkonto und hinken ohnehin Stunden hinterher. Der Link neben der Überschrift führt direkt zur Abrechnungsseite.

### Dateien (Tab System)
Ein Browser über **alle hochgeladenen Bilder** und die **PDFs der Bibliothek** — gedacht zum Aufräumen und Nachsehen, was eigentlich alles herumliegt.

- Der Abschnitt ist **zusammengeklappt**; in der Zeile steht die Bilanz („91 Bilder, 4 PDFs"). Ein Klick auf die Überschrift öffnet ihn. Die Kacheln werden erst dabei gebaut — bei einigen hundert Bildern lädt der Tab System sonst jedes Mal alles mit.
- **Linksklick** öffnet die Datei in einem neuen Tab. PDFs werden dabei **inline** angezeigt (mit `sandbox` und `nosniff`), anders als öffentlich — dort gibt es sie ausschließlich als Download.
- **Rechtsklick löscht**, nach Nachfrage. Das Löschen liegt bewusst auf dem Kontextmenü: ein Fehlklick in einem Raster aus hunderten Kacheln darf keine Datei kosten.
- **Eingebundene Dateien lassen sich nicht löschen.** Steckt der Dateiname noch in `site.json`, verweigert das Add-on den Vorgang — sonst reisst der betroffene Beitrag oder Eintrag ein Loch. Die Plakette „unbenutzt“ zeigt vorab, was gefahrlos weg kann.
- Die Kachel eines **KI-Bildes** trägt ✨; die Kennzeichnung stammt aus dem Dateinamen.
- Das Kontrollkästchen **„Nur KI-erzeugte Bilder“** blendet alles andere aus. Dieselbe Möglichkeit gibt es im Medien-Browser hinter jedem „Bild wählen“.

### Reiseblog
Ein eigenes Modul, getrennt vom normalen Blog: unterwegs ein paar Stichpunkte erfassen, den Tagesbericht schreibt die KI daraus.

- **Reise anlegen** (Name, Ziel, Unterkunft, Zeitraum). Schreibstil, Perspektive, Länge und Sprache werden **einmal je Reise** festgelegt und gelten für alle Tage — nicht bei jedem Tag neu.
- **Tag erfassen** im Wizard mit acht Schritten: Tag & Ort, Wetter, Erlebnisse, Essen, Eindrücke, Momente & Ausgaben, Fotos & Notizen, Bericht. **Pflicht sind nur Reisetag und Datum** — beide mit `*` gekennzeichnet, alles andere darf leer bleiben. Was leer ist, taucht im Prompt gar nicht erst auf, damit die KI nichts dazuerfindet.
- Die **Auswahllisten** (Wetter, Art des Erlebnisses, Verkehrsmittel, Kategorie …) speichern deutschen Klartext, weil genau der in den Prompt wandert. Auf Englisch werden nur die **Beschriftungen** übersetzt — im Admin wie auf der öffentlichen Seite.
- **Bildunterschriften**: die KI schreibt eine je Foto **mit Hinweis**. Im Schritt *Fotos* lässt sich je Foto eine **eigene** eintragen; sie hat Vorrang und ist der einzige Weg, ein Foto ohne Hinweis zu beschriften.
- Erlebnisse, Mahlzeiten, besondere Momente, Ausgaben und Fotos sind **beliebig oft** hinzufügbar. Ausgaben werden je Währung summiert — getrennt statt umgerechnet, ein geratener Wechselkurs wäre eine erfundene Zahl.
- **„Wetter war erwähnenswert“**: ohne Haken lässt die KI das Wetter im Bericht weg.
- **Wetter aus Home Assistant**: Läuft MyPage als Add-on, holt ein Knopf im Wetter-Schritt Wetterlage, Temperatur und Windstärke zum Datum des Reisetags — für heute den aktuellen Zustand der Entität, für einen vergangenen Tag den Verlauf aus dem Recorder (Zustand um die Mittagszeit, Aufbewahrung standardmäßig zehn Tage). Die Entität wird je Reise im Reise-Dialog gewählt; dort stehen alle `weather.*`-Entitäten zur Auswahl. **Sie misst dort, wo sie eingerichtet ist** — für ein Ziel im Ausland vorher in Home Assistant eine Entität für diesen Ort anlegen. Übernommen wird nur, was Home Assistant liefert; eine Wetterlage ohne Entsprechung im Formular (etwa „tornado") wird nicht geraten, sondern als Hinweis angezeigt. Unter Docker ohne Home Assistant gibt es Knopf und Auswahlfeld nicht.
- Der Zwischenstand wird **laufend lokal im Browser gesichert**. Bricht unterwegs die Verbindung weg, ist die Eingabe nicht verloren.
- **„Reisebericht erstellen“** baut aus den Angaben einen Prompt und liefert Titel, Anrisstext, Fließtext in Markdown, Schlagwörter und Bildunterschriften — auf Wunsch deutsch und englisch in einem Durchgang. Das Ergebnis ist frei editierbar.
- Die **vorherigen Reisetage** gehen als Kurzfassung mit in den Prompt, damit sich die Berichte nicht wiederholen.
- **Prompt einsehen:** Unter dem fertigen Bericht steht zugeklappt der Text, der an die KI ging. Fehlt etwas im Bericht, sieht man dort sofort, ob es überhaupt im Prompt stand — leere Felder fallen kommentarlos heraus.
- **Datum und Ort aus dem Foto:** Wird im Schritt „Fotos" ein Bild neu hochgeladen, liest das Add-on Aufnahmedatum und GPS aus, bevor es die Metadaten verwirft. Das Datum wird übernommen, sofern noch keines gesetzt ist. Die Koordinaten werden nur angezeigt; erst **📍 Ort nachschlagen** fragt bei OpenStreetMap nach dem Ortsnamen. Für ein bereits vorhandenes Bild aus der Medien-Auswahl gibt es diese Angaben nicht mehr — die Datei ist zu diesem Zeitpunkt längst metadatenfrei.
- **Überarbeiten statt neu erzeugen:** Steht der Bericht, ändern **Kürzer**, **Länger**, **Feinschliff** und ein freier Änderungswunsch ihn, ohne ihn neu zu würfeln — eigene Korrekturen bleiben also erhalten. Bei zweisprachigen Reisen lässt sich eine Sprache allein überarbeiten, das halbiert die Kosten. **↶ Vorherige Fassung** nimmt einen Lauf zurück (bis zum Wechsel auf einen anderen Tag). Auch hier wird nichts dazuerfunden: „Länger" und der freie Wunsch bekommen die Tagesdaten als einzige erlaubte Quelle, „Kürzer" und „Feinschliff" sehen nur den vorhandenen Text.
- **Rückblick auf die ganze Reise** (📖 Rückblick, neben „Neuer Reisetag"): ein Text über die komplette Reise, geschrieben aus den fertigen Tagesberichten — kein Tag-für-Tag-Protokoll, sondern der Bogen der Reise mit Höhepunkten und Fazit. Tage ohne Bericht bleiben draußen. Er lässt sich mit denselben Knöpfen überarbeiten wie ein Tagesbericht und wird **getrennt freigegeben**: ohne Haken bleibt er ein Entwurf. Öffentlich steht er auf der Reise-Seite über der Liste der Tage; sein Anrisstext wird zur Beschreibung dieser Seite und zum Text auf der Kachel in der Reise-Übersicht, und die Reise-Seite ist damit auch über die Suche zu finden. Bei einer Reise nur für Mitglieder zeigt er Fremden wie die Tage nur den Anriss.
- Gespeichert wird in **`travel.json`**, getrennt von `site.json` und im Backup enthalten. Rohdaten und fertiger Text liegen getrennt: eine Korrektur am Text geht nicht verloren, wenn später noch eine Ausgabe nachgetragen wird.

**Öffentlich:** Drei Seiten — die Übersicht aller Reisen unter `/reiseblog`, die Tage einer Reise unter `/reiseblog/<reise>` und der Bericht unter `/reiseblog/<reise>/<tag>`. Sichtbar wird davon nur, was ausdrücklich freigegeben ist:

- **„Tag veröffentlichen“** steht im letzten Wizard-Schritt beim Bericht. Ohne Haken bleibt der Tag im Admin — und mit Haken, aber **ohne Bericht**, ebenfalls: eine Seite mit Datum und ohne Text hilft niemandem. Die Liste im Reiter zeigt je Tag, was gerade gilt (🌐 veröffentlicht / Entwurf).
- **Vorschau** je Tag im Reiter — zeigt auch Entwürfe, damit vor dem Freigeben sichtbar ist, was tatsächlich herauskommt.
- **Adresse (Slug)** je Reise, frei wählbar im Reise-Dialog; leer gelassen wird sie aus dem Namen gebildet (`Gran Canaria 2027` → `gran-canaria-2027`). Einmal vergeben **bleibt sie**, auch beim Umbenennen — sonst führte jeder geteilte Link ins Leere. Die Tage heißen `tag-1`, `tag-2`, … und behalten ihre Adresse, wenn der Ort später korrigiert wird.
- **Nur für Mitglieder** je Reise: Titel und Anrisstexte bleiben sichtbar, die Berichte nicht. Die Sperre gilt für die ganze Reise — eine halb gezeigte Reise wäre eine Geschichte mit Löchern.
- Der **Abschnitt auf der Startseite** erscheint, sobald der Reiseblog unter *Design → Module* für die Website freigegeben ist **und** mindestens ein Tag veröffentlicht wurde. Position und Sichtbarkeit wie bei jedem Abschnitt unter *Inhalte*.
- Steht der Schalter auf **NEIN**, ist das Modul ganz aus: keine Seiten unter `/reise/…`, kein Abschnitt — und im Admin verschwinden **auch der Reiter *Reiseblog* und der Abschnitt unter *Inhalte***. Reisen und Tage bleiben gespeichert und kommen beim Einschalten unverändert zurück. Zum Vorbereiten muss der Schalter **nicht** aus: solange kein Tag veröffentlicht ist, zeigt die Website nichts an. **Werkseinstellung ist NEIN** — der Reiter *Reiseblog* erscheint also erst, wenn du ihn hier einschaltest.
- **Ausgaben**: Der Tagesbericht zeigt eine Aufstellung (Kategorie, Zweck, Betrag) mit Summe, die Reise-Seite die Summe über alle veröffentlichten Tage — je Währung getrennt, nicht umgerechnet. Gesteuert vom Schalter **„Preise im Bericht nennen"** der Reise: ist er aus, bleiben auch die Aufstellungen weg. Entwürfe zählen nicht mit.
- Der Tagesbericht zeigt **Fakten** (Datum, Ort, Wetter), den Text, eine **Bildergalerie** mit den Unterschriften, die Schlagwörter und eine Leiste zum **Blättern** zum vorherigen und nächsten Tag. Über „Drucken“ des Browsers entsteht ein sauberes PDF ohne Kopf-, Fuß- und Navigationsleiste.
- **Sitemap, Volltextsuche, IndexNow und der statische Export** kennen die veröffentlichten Tage; Entwürfe bleiben überall außen vor.

### Volltextsuche
Eine seitenweite Suche über **Blog-Beiträge, Projekte, Seiten, Bibliothek-Einträge und veröffentlichte Reisetage** (Titel, Inhalt und Tags, jeweils DE & EN). Im Design-Tab aktivierbar (Standard aus). Ist sie an, erscheint ein **Suchfeld im Kopfbereich** der Startseite; die Ergebnisse stehen unter `/suche`.

- **Treffer**: Jeder Treffer zeigt seine Art (Beitrag/Projekt/Seite/Bibliothek), den Titel und einen **Auszug mit hervorgehobenen Suchbegriffen**. Mehrere Wörter werden alle gefordert (UND-Suche). Entwürfe, geplante Beiträge und unveröffentlichte Inhalte bleiben außen vor.
- **Mitglieder-Inhalte**: Gesperrte (Mitglieder-only) Beiträge und Seiten erscheinen für Gäste nur als **Titel mit 🔒, ohne Inhalts-Vorschau** — angemeldete Mitglieder sehen die volle Vorschau. So wird kein geschützter Text geleakt.
- **Hinweis**: Die Suchseite ist auf `noindex` gesetzt (keine Indexierung durch Suchmaschinen). Sie nutzt ausschließlich vorhandene Inhalte aus `site.json` — kein zusätzlicher Speicher, kein externer Dienst.

### Formulare
Frei konfigurierbare Formulare über das eine Kontaktformular hinaus — z. B. **Veranstaltungs-Anmeldung, Umfrage oder Anfrage**. Jedes Formular ist unter `/formular/<slug>` erreichbar (optional als Navi-Eintrag).

- **Abschnitt auf der Startseite** mit einer Kachel je aktivem Formular; einsortierbar und ausblendbar unter *Inhalte*. Steht der Abschnitt in der Navigationsleiste, entfallen dort die einzelnen Formular-Links — sonst stünde erst „Formulare" und daneben nochmal jedes einzelne.
- Der Schalter **Formulare** unter *Design → Module* nimmt das Modul **ganz** aus dem Betrieb: Abschnitt, Navi-Einträge und die Seiten unter `/formular/…` sind weg — und im Admin verschwinden **auch der Reiter *Formulare* und der Abschnitt unter *Inhalte***. Angelegte Formulare und eingegangene Antworten bleiben unangetastet und kommen beim Einschalten unverändert zurück, samt Position und Augen-Zustand des Abschnitts. Zum Vorbereiten muss der Schalter also **nicht** aus: ein Formular ohne eigenen Schalter „aktiv“ geht ohnehin nicht online.

- **Felder**: beliebig viele, per Drag sortierbar. Typen: Text, mehrzeiliges Textfeld, E-Mail, Telefon, Zahl, Datum, Auswahl (Dropdown), Auswahl (Radio) und Kontrollkästchen. Je Feld DE/EN-Bezeichnung, optionaler Platzhalter, **Pflicht**-Schalter und (für Auswahl/Radio) Optionen (eine je Zeile).
- **Einleitung & Danke-Text** (DE/EN, Markdown) lassen sich frei texten.
- **Einsendungen** landen im Tab **„Nachrichten"** — mit Formularnamen als Markierung (📋) und allen Feldern aufgelistet. Sie zählen in den Nachrichten-Badge und werden im Backup mitgesichert.
- **Benachrichtigung**: Je Formular abschaltbar. Ist sie an, wird bei jeder Einsendung dieselbe Benachrichtigung wie beim Kontaktformular ausgelöst (E-Mail, Telegram und Home-Assistant-Notification).
- **Spam-Schutz**: wie beim Kontaktformular — verstecktes Honeypot-Feld, Rechen-Captcha und Rate-Limit.
- **Status**: „Veröffentlicht" oder „Entwurf"; Entwürfe sind öffentlich 404, im Admin aber über **Vorschau** sichtbar. Formulare liegen in `site.json` (im Backup).

### Mitglieder-only-Inhalte
Einzelne Inhalte lassen sich auf **angemeldete Mitglieder** beschränken (nutzt den bestehenden [Mitgliederbereich](#persönlicher-bereich-mitglieder)):

- **Blog-Beiträge**: Schalter **„🔒 Nur für Mitglieder"** im Beitrags-Editor. Gäste sehen den Beitrag in der Liste mit Schloss-Symbol; öffnen sie ihn, erscheinen nur Titel + ein kurzer Anriss und ein **„Zum Mitglieder-Login"**-Button (Kommentare, Galerie und Video bleiben verborgen). Eingeloggte Mitglieder sehen alles.
- **Eigene Seiten**: derselbe Schalter im Seiten-Editor — gleiches Verhalten (Anriss + Login-Aufforderung für Gäste).
- **Fotoalben**: Schalter **„🔒 Nur für Mitglieder"** im Album-Editor. Gäste sehen statt der Bilder eine **Schloss-Karte** (Titel + Foto-Anzahl + Link zum Login); es werden keine Bild-Adressen des Albums ausgeliefert. Eingeloggte Mitglieder sehen das Album normal mit Diashow.
- **Startseiten-Sektionen**: Im Tab **Inhalt** hat jeder Abschnitt neben dem Auge ein **Schloss-Symbol**. Aktiviert, ist der ganze Abschnitt nur für eingeloggte Mitglieder sichtbar (für Gäste komplett ausgeblendet, auch in der Navigation).

Der Anriss zeigt höchstens die Hälfte des Textes (max. ~280 Zeichen), sodass auch bei kurzen Inhalten stets ein Teil verborgen bleibt. Statischer Export und Suchmaschinen laufen als „Gast" — geschützte Inhalte landen nicht im Export.

### System
- **Wartungsmodus**: Schalter, der die öffentliche Seite durch eine Hinweisseite ersetzt (HTTP 503, eigener Text in DE/EN, Markdown möglich). Das Admin-Panel bleibt erreichbar. Ist im Tab **Inhalt** ein **Countdown** eingerichtet, wird er auf dieser Seite mit angezeigt — so entsteht eine Coming-Soon-Seite mit Countdown und optionalem „Benachrichtige mich"-Newsletter-Button.
- **Admin-Protokoll (Audit-Log)**: Listet sicherheitsrelevante Admin-Aktionen mit Zeitpunkt und IP — erfolgreiche und fehlgeschlagene Logins, Benutzer angelegt/gelöscht/freigegeben, Passwort/Quota/Spiele geändert, Einstellungen gespeichert und Backup eingespielt. Die letzten 500 Einträge werden in `audit.json` gehalten und im Backup mitgesichert.
- **Speicher aufräumen** — zwei getrennte Werkzeuge, keines fasst den Ordner des anderen an. Vor dem Löschen werden jeweils Anzahl und Größe angezeigt; entfernt wird ausschließlich, was nirgends mehr referenziert ist (geteilte Dateien bleiben erhalten).
  - **Ungenutzte Bilder aufräumen**: hochgeladene Bilder, die in keinem Beitrag, keiner Seite, keinem Projekt und keinem Album mehr verwendet werden (z. B. nach dem Löschen einer Seite oder nach einem verworfenen KI-Bild).
  - **Ungenutzte PDFs aufräumen**: PDFs der Bibliothek, zu denen es keinen Eintrag mehr gibt. Im Normalbetrieb räumt die Bibliothek selbst auf (neu gerendert, PDF-Modus gewechselt, Eintrag gelöscht) — der Knopf fängt ab, was daran vorbeigeht: ein abgebrochenes Rendern oder eine Wiederherstellung aus einem Backup mit weniger Einträgen.
- **Alternativtexte der Bilder**: Ein Bild ohne Alternativtext ist für Screenreader nicht vorhanden und für Suchmaschinen stumm. Der Abschnitt unter dem Datei-Browser ist **zusammengeklappt**; in der Zeile steht, wie viele Bilder es gibt und wie vielen davon ein Text fehlt. Ein Klick auf die Überschrift öffnet den Editor: je Bild ein Feld für **Deutsch und Englisch**, standardmäßig nur die Bilder **ohne** Text. Der Text hängt an der **Datei**, nicht am Beitrag — dasselbe Bild zeigt überall dasselbe.
  - **Wo er wirkt:** Titelbilder und Galerien in Beiträgen, Projekten, Bibliothek, Reiseblog und auf der Startseite. In Markdown füllt er nur leere Klammern: `![](…)` bekommt ihn, `![eigener Text](…)` behält deinen. Fehlt die gewünschte Sprache, gilt die andere — ein deutscher Text ist besser als keiner. Bei Titelbildern ersetzt er den bisherigen Rückfall auf den Titel.
  - **Mit Gemini erzeugen:** Mit hinterlegtem Textmodell steht je Bild ein **„✦ KI"**-Knopf bereit, dazu **„Alle fehlenden erzeugen"** (der Reihe nach, wegen des Stundenlimits). Der Fortschritt läuft im **Banner oben** wie im KI-Tab — „Alternativtext für Bild 3 von 12 …", am Ende die Zahl, im Fehlerfall der Grund. Der Vorschlag landet erst im Feld — **gespeichert wird mit „Speichern"**, damit er sich vorher korrigieren lässt. Bricht der Sammellauf ab, bleibt gespeichert, was bis dahin fertig war. Jede Anfrage zählt auf das Textkontingent.
  - Gespeichert wird in `uploads_meta.json`, **im Backup enthalten**. Wird ein Bild gelöscht oder weggeräumt, verschwindet sein Alternativtext mit. Ein Alternativtext allein schützt eine Datei **nicht** vor dem Aufräumen — sonst fände „Ungenutzte Bilder aufräumen" nie wieder eine Waise.
- **Weiterleitungen (301)**: Leitet alte/geänderte Adressen auf eine neue um — dauerhaft (301) oder temporär (302). Ziel als interner Pfad (`/neue-seite`) oder vollständige URL (`https://…`). Greift **nur für Pfade, die es nicht (mehr) gibt** — bestehende Seiten werden nie überschrieben. Praktisch, wenn du den Slug einer Seite/eines Beitrags geändert hast und alte Links/Lesezeichen weiter funktionieren sollen.
- **Backup**: Ein Klick lädt ein ZIP mit allen Inhalten, Statistiken, Nachrichten, Blog-Kommentaren, Benutzern, Spielständen und Uploads herunter; über „Backup einspielen" wird es wiederhergestellt.
- **Automatische Backups**: Einmal täglich legt das Add-on dasselbe ZIP automatisch unter `addon_configs/<slug>_mypage/autobackup/` ab (Dateiname `mypage-auto-JJJJ-MM-TT.zip`). Wie viele Stände aufbewahrt werden, steuert die Option `auto_backup_keep` (Standard 7, `0` schaltet es ab) — ältere werden automatisch gelöscht. Im Tab **System** siehst du die vorhandenen Stände mit Datum und Größe und kannst sie einzeln herunterladen oder löschen; „Jetzt sichern" erzeugt den Stand des Tages sofort neu. Die Sicherungen liegen bewusst **außerhalb** des Backup-Inhalts, damit sie sich nicht gegenseitig aufblähen. Einspielen geht wie gewohnt über „Backup einspielen" mit der heruntergeladenen Datei.
- **Frühere Stände (Revisionen)**: Vor jeder Änderung sichert das Add-on den bisherigen Stand der Seiteninhalte unter `addon_configs/<slug>_mypage/revisions/` (Dateiname `site-JJJJMMTT-HHMMSS.json`). Im Tab **System → Frühere Stände** stehen sie mit Zeitpunkt und den geänderten Abschnitten („Profil, Design“) und lassen sich einzeln zurückholen, herunterladen oder löschen. Beim Zurückholen wird der aktuelle Stand vorher selbst zum Stand — ein versehentlicher Griff ist also wieder rückgängig zu machen.
  - Enthalten sind **nur die Seiteninhalte** (`site.json`): Profil, Projekte, Blog, Seiten, Design, Rechtstexte, Formulare, Bibliothek. Mitglieder, Nachrichten, Reiseblog, Umfragen und Statistik liegen in eigenen Dateien und bleiben beim Zurückholen unberührt. Für alles zusammen ist das Backup zuständig.
  - Stände, die weniger als 90 Sekunden auseinanderliegen, werden zu einem zusammengefasst — sonst bestünde die Liste aus einer längeren Bearbeitung von vor zehn Minuten und der Stand von gestern wäre längst herausrotiert. Änderungen, die nur vom Besuch der Seite kommen (Slot-Jackpot, Tipp-Statistik), erzeugen gar keinen Stand.
  - Die Stände sind **nicht** Teil des Backup-ZIPs — wie bei den automatischen Backups würde sich das Backup sonst mit allen Vorgängerständen selbst aufblähen.
- **Statischer Export**: Die Seite als fertiges HTML-Paket (deutsch), z. B. für GitHub Pages. Kontaktformular und Sprachumschalter sind im Export deaktiviert.

## Persönlicher Bereich (Mitglieder)

Unter `/bereich` (Login-Link im Footer) gibt es einen passwortgeschützten Dateibereich pro Benutzer — praktisch zum einfachen Teilen von Dateien mit Familie und Freunden.

- **Benutzer anlegen** im Admin-Tab „Benutzer": E-Mail (= Benutzername), Passwort (min. 8 Zeichen), Speicher-Quota. Ist ein Mailserver konfiguriert, bekommt der Benutzer die Zugangsdaten **automatisch per E-Mail** (ebenso bei Passwort-Reset).
- **E-Mail-Sprache pro Mitglied (DE/EN)**: Jedes Konto hat eine bevorzugte Sprache, in der **alle automatischen E-Mails** ankommen (Zugangsdaten, neues Passwort, Passwort-Reset, E-Mail-Bestätigung, Konto-Freischaltung, Kommentar-Antworten, Postfach-Erinnerung). Beim Anlegen im Admin wählbar, jederzeit über den **🌐-Knopf** in der Benutzerliste umschaltbar; bei der Selbst-Registrierung wird die aktuelle Seitensprache übernommen. Mitglieder können ihre Sprache auch **selbst im Profil** ändern (nur sichtbar, wenn ein Mailserver konfiguriert ist). Standard ist Deutsch.
- **Selbst-Registrierung**: Besucher können sich (optional) selbst ein Konto anlegen — Details siehe Abschnitt [Selbst-Registrierung](#selbst-registrierung) unten.
- **Passwort vergessen (Self-Service)**: Sind ein Mailserver (`smtp_host`) **und** die öffentliche URL gesetzt, erscheint auf der Login-Seite ein „Passwort vergessen?"-Link. Das Mitglied erhält einen zeitlich begrenzten Link (1 Stunde gültig) und setzt selbst ein neues Passwort — ohne Admin. Aus Sicherheitsgründen: stets dieselbe neutrale Rückmeldung (keine Rückschlüsse, ob eine E-Mail existiert), Einmal-Token, Rate-Limit pro IP, und nach dem Zurücksetzen werden alle bestehenden Sitzungen beendet.
- **Spiele pro Mitglied abschaltbar**: In der Benutzerliste schaltet ein Button (🕹️/🚫) die Mitglieder-Spiele für ein Konto frei oder sperrt sie. Gesperrte Mitglieder sehen keine Spiel-Kacheln mehr, und die Spiel-Seiten/-APIs sind serverseitig blockiert — der Dateibereich bleibt normal nutzbar.
- **Nachrichten zwischen Mitgliedern** (verschlüsselt): siehe Abschnitt [Mitglieder-Nachrichten](#mitglieder-nachrichten) unten.
- **Speicheranzeige**: Im persönlichen Bereich zeigt ein Balken die Quota-Auslastung in **Prozent**; er färbt sich ab 80 % orange, ab 95 % rot, und ein kurzer Hinweis erscheint, wenn der Speicher fast voll ist.
- **Datenschutz (DSGVO-Self-Service)**: Im Profil kann jedes Mitglied **„Meine Daten exportieren"** — ein ZIP mit allen eigenen Daten (Kontodaten, hochgeladene Dateien, eigene Blog-Kommentare, gesendete Nachrichten, Profilbild; Art. 15/20 DSGVO) — und sein **Konto selbst löschen** (nach Passwort-Bestätigung; entfernt Konto und alle eigenen Dateien unwiderruflich und meldet ab; Art. 17 DSGVO).
- **Sicherheit**: Passwörter werden ausschließlich als scrypt-Hash gespeichert; Brute-Force-Schutz (5 Fehlversuche → 15 Min. Sperre); jeder Benutzer sieht nur den eigenen Bereich; Downloads werden immer als Datei-Anhang ausgeliefert, hochgeladene HTML-Dateien können also nie im Browser ausgeführt werden.
- **Limits**: `user_upload_max_mb` begrenzt die Größe pro Datei (Standard 200 MB), die Quota pro Benutzer ist im Admin einstellbar.

### Selbst-Registrierung

Statt jeden Benutzer von Hand anzulegen, können sich Besucher selbst registrieren. Die Funktion ist **standardmäßig aus** und nur mit konfiguriertem **E-Mail-Versand (`smtp_host`)** und gesetzter **öffentlicher URL** nutzbar (die E-Mail-Bestätigung ist Pflicht).

**Aktivieren:** Im Tab **Design** den Schalter **„Selbst-Registrierung"** auf **Ja** stellen und optional die **Standard-Quota** für neue Konten festlegen (Standard 500 MB). Auf der Login-Seite (`/bereich`) erscheint dann der Link **„Konto erstellen"**.

**Ablauf (zweistufig):**

1. Der Besucher füllt das Formular aus (E-Mail, optionaler Anzeigename, Passwort) und löst eine kleine **Sicherheitsfrage** (Captcha).
2. Es wird ein **unbestätigtes** Konto angelegt und eine **Bestätigungs-E-Mail** mit Link verschickt (24 Stunden gültig).
3. Der Besucher klickt den Link → seine **E-Mail ist bestätigt**.
4. Der **Admin** gibt das Konto frei: in der Benutzerliste erscheint bei wartenden Konten ein grüner Button **„Freigeben"**. Nach der Freigabe bekommt das Mitglied eine **Aktivierungs-E-Mail**.
5. Erst jetzt ist die **Anmeldung** möglich. Vorher wird ein Login mit einem klaren Hinweis abgewiesen („E-Mail bestätigen" bzw. „wartet auf Freigabe").

**Selbst-registrierte Konten** starten bewusst **ohne Spielezugang** (lässt sich pro Person über den 🕹️-Button freigeben) und mit der eingestellten Standard-Quota. In der Benutzerliste sind sie als **`🆕 selbst registriert`** mit Status (`unbestätigt` / `wartet auf Freigabe` / `aktiv`) markiert.

**Schutz vor Missbrauch:** Rechen-Captcha, unsichtbares Honeypot-Feld, Rate-Limit (5 Versuche/Stunde pro IP) und **keine E-Mail-Enumeration** — die Rückmeldung ist immer gleich („Prüfe dein Postfach"); existiert die Adresse bereits, bekommt sie stattdessen eine Hinweis-Mail.

**Im Blick behalten:** Bei jeder Registrierung und Bestätigung gibt es eine **Home-Assistant-Benachrichtigung** (`ha_notify`). Zusätzlich zählt `sensor.mypage_pending_approvals`, wie viele bestätigte Konten auf deine Freigabe warten, und solange welche offen sind, bleibt eine **stehende HA-Benachrichtigung** sichtbar (sie verschwindet automatisch, sobald alles freigegeben ist).

### Mitglieder-Nachrichten

Eingeloggte Mitglieder können sich gegenseitig **private Nachrichten** schreiben — ohne dass E-Mail-Adressen sichtbar werden.

**Aktivieren:** Im Tab **Design** den Schalter **„Mitglieder-Nachrichten"** auf **Ja** stellen. Im persönlichen Bereich (`/bereich`) erscheint dann die Karte **„Nachrichten"** mit Ungelesen-Zähler.

- **Postfach** (`/bereich/nachrichten`): Liste der Unterhaltungen (neueste oben), Vorschau und Ungelesen-Markierung. Zum Schreiben einen Empfänger über das **durchsuchbare Dropdown** wählen — gelistet werden nur Mitglieder, die Nachrichten empfangen.
- **Pro Mitglied abschaltbar**: Jedes Mitglied kann im **eigenen Profil** den Empfang deaktivieren („Andere Mitglieder dürfen mir schreiben"). Wer das abschaltet, taucht in keiner Empfängerliste mehr auf; bestehende Unterhaltungen bleiben für beide sichtbar. Der **Admin** kann den Empfang zusätzlich pro Mitglied erzwingen/sperren (✉️/🔕-Button in der Benutzerliste).
- **Löschen**: Einzelne Nachrichten (✕ an der Sprechblase) oder eine ganze Unterhaltung (🗑 in der Kopfzeile) lassen sich entfernen. Das gilt **nur für einen selbst** — die Gegenseite behält ihre Sicht. Erst wenn beide gelöscht haben (oder ein Konto entfernt wurde), verschwindet der Eintrag endgültig aus `dm.json`.
- **Erinnerung**: Bleibt eine neue Nachricht **3 Stunden ungelesen**, erhält der Empfänger eine **E-Mail** (nur wenn `smtp_host` **und** die öffentliche URL gesetzt sind). Die Mail enthält **bewusst keinen Inhalt und keinen Absendernamen** — nur einen Hinweis und den **Link zum Postfach**. Je ungelesener Nachricht wird höchstens **einmal** erinnert.
- **Verschlüsselung**: Die **Nachrichtentexte** werden mit Fernet (AES-128 + HMAC) verschlüsselt in `dm.json` gespeichert; der Schlüssel liegt in `dm.key` (wird beim ersten Start automatisch erzeugt, Dateirechte 600). Metadaten wie Absender, Empfänger und Zeitstempel bleiben im Klartext, damit das Postfach ohne Entschlüsseln funktioniert.
- **Backup**: `dm.json` **und** `dm.key` werden vom Add-on-Backup mitgesichert und beim Restore wiederhergestellt — verschlüsselte Nachrichten bleiben so lesbar. Achtung: Dadurch ist das Backup-Archiv so vertraulich wie der Klartext (es enthält ohnehin schon Passwort-Hashes) — entsprechend sicher aufbewahren.
- **Datei-Anhänge:** An eine Nachricht lässt sich eine **Datei anhängen** (max. 25 MB; Bilder, PDF, Office-Dokumente, Archive, Audio/Video). Anhänge werden — wie der Text — **mit Fernet verschlüsselt** in `dm_files/` gespeichert und nur für die Gesprächsteilnehmer beim Download entschlüsselt; sie werden stets als Datei-Download ausgeliefert (nie im Browser ausgeführt). Eine Nachricht darf auch nur aus einem Anhang bestehen. Beim endgültigen Löschen wird die Anhang-Datei mitentfernt; das Backup sichert die verschlüsselten Anhänge mit.
- **Limits**: max. 4000 Zeichen pro Nachricht, kurze Sende-Bremse gegen Spam, je Unterhaltung werden die letzten 500 Nachrichten behalten.
- **Rundnachricht (Admin):** Im Tab **Benutzer** gibt es ein Feld **„Rundnachricht an alle Mitglieder"**. Damit landet eine **Ankündigung** im Postfach jedes Mitglieds — verschlüsselt wie normale Nachrichten, mit deinem Seitentitel und 📢-Markierung. Mitglieder können sie lesen und für sich löschen, aber nicht beantworten. (Bei aktiviertem 3h-Reminder erinnert die ungelesene Ankündigung wie jede andere Nachricht.)

### Mitglieder-Verzeichnis

Damit Mitglieder wissen, wem sie schreiben, gibt es ein optionales internes **Verzeichnis** mit Avatar und Kurzvorstellung.

**Aktivieren:** Tab **Design → „Mitglieder-Verzeichnis"** auf **Ja**. Im persönlichen Bereich erscheint dann die Karte **„Mitglieder-Verzeichnis"**.

- **Opt-in pro Mitglied:** Jedes Mitglied entscheidet im **Profil** selbst, ob es im Verzeichnis erscheint („Mich im Mitglieder-Verzeichnis anzeigen", Standard aus), und hinterlegt optional **Profilbild** und **Kurzvorstellung** (max. 300 Zeichen).
- **Profilbilder** werden quadratisch zugeschnitten, auf 256 px verkleinert und **ohne EXIF-Metadaten** (also ohne GPS/Kamera-Infos) als JPEG gespeichert — lokal im Add-on-Ordner, nicht auf dem SMB-Share. Sie werden vom Backup mitgesichert.
- **Verknüpfung mit Nachrichten:** Aus dem Verzeichnis führt ein **„Schreiben"-Knopf** direkt in die Unterhaltung — sofern das Mitglied Nachrichten empfängt und die Nachrichten-Funktion aktiv ist.
- Das Verzeichnis ist **nur für eingeloggte Mitglieder** sichtbar und zeigt ausschließlich Mitglieder, die sich freiwillig sichtbar gemacht haben.

### Optionaler SMB-Speicher

Damit die Benutzerdateien nicht die SD-Karte füllen, können sie auf eine SMB-Freigabe (z. B. FritzBox-NAS) ausgelagert werden: `smb_server`, `smb_share`, `smb_user`, `smb_password` im Admin-Panel unter **Einstellungen** setzen und das Add-on neu starten.

- **Unterordner wählbar**: Im Benutzer-Tab gibt es einen Ordner-Browser, mit dem du den genauen Zielordner auf dem Share festlegst. Bestehende Dateien werden beim Wechsel **nicht** automatisch umgezogen.
- **Kein Fallback**: Ist der SMB-Speicher nicht erreichbar (Server aus, Neustart), geht der Dateibereich bewusst **offline** — Benutzer und Admin sehen eine entsprechende Meldung. So landen nie versehentlich Dateien auf der SD-Karte.
- **Automatische Wiederverbindung**: Ein Watchdog prüft jede Minute und mountet nach einem FritzBox-/NAS-Neustart automatisch neu (`soft`-Mount verhindert hängende Zugriffe).

### Dateien für Benutzer hinterlegen

Im Benutzer-Tab öffnet der „Dateien"-Button pro Benutzer eine Dateiverwaltung: Du kannst Dateien **hinterlegen** (zählt gegen die Quota des Benutzers), herunterladen und löschen — praktisch, um jemandem etwas bereitzustellen, ohne dass er selbst hochladen muss.

## Home-Assistant-Sensoren

Das Add-on meldet alle 2 Minuten vier Sensoren an Home Assistant:

| Sensor | Inhalt |
|---|---|
| `sensor.mypage_views_total` | Seitenaufrufe gesamt |
| `sensor.mypage_visitors_total` | Eindeutige Besucher gesamt |
| `sensor.mypage_views_today` | Aufrufe heute |
| `sensor.mypage_visitors_today` | Eindeutige Besucher heute |
| `sensor.mypage_traffic_today` | Ausgeliefertes Datenvolumen heute (MB) |
| `sensor.mypage_traffic_total` | Ausgeliefertes Datenvolumen gesamt (MB) |
| `sensor.mypage_user_storage` | Belegter Speicher aller Mitglieder-Dateien (MB) |
| `sensor.mypage_failed_logins` | Fehlgeschlagene Logins der letzten 24 h (Admin + Mitglieder) |
| `sensor.mypage_messages` | Anzahl gespeicherter Kontaktnachrichten |
| `sensor.mypage_members` | Anzahl angelegter Benutzer |
| `sensor.mypage_pending_approvals` | Selbst-Registrierungen, die auf deine Freigabe warten |
| `sensor.mypage_projects` / `_posts` / `_albums` | Anzahl Projekte / Blog-Beiträge / Fotoalben |
| `binary_sensor.mypage_storage_online` | SMB-/Dateispeicher erreichbar (on/off) |
| `binary_sensor.mypage_maintenance` | Wartungsmodus aktiv (on/off) |

Zusätzlich gibt es **Live-Spiel-Sensoren** (alle 30 s aktualisiert): `sensor.mypage_spieler_aktiv` (Anzahl gerade Spielender, mit Detail-Attributen), je Spiel `sensor.mypage_aktiv_<spiel>` und `binary_sensor.mypage_spielt_jemand` (on/off).

Damit lassen sich Dashboards und Automationen bauen (z. B. Benachrichtigung bei Besucherrekord).

### Benachrichtigungen

Ist `ha_notify` aktiv (Standard), erzeugt MyPage **persistente Benachrichtigungen** direkt in Home Assistant bei:

- **neuer Kontaktnachricht** (mit Absender und Vorschau),
- **neuem Blog-Kommentar** (mit Beitragstitel und Vorschau),
- **verdächtigen Anmeldeversuchen** — wenn eine IP wegen zu vieler Fehllogins gesperrt wird.

Wiederholungen derselben Quelle aktualisieren dieselbe Meldung, statt sie zu vervielfachen. So siehst du wichtige Ereignisse direkt im HA-Dashboard bzw. auf dem Handy (HA-App), zusätzlich zu den optionalen Telegram-/E-Mail-Hinweisen.

## SEO

`sitemap.xml` und `robots.txt` werden automatisch erzeugt. Damit die Sitemap korrekte Links enthält, im Design-Tab die **öffentliche URL** eintragen (z. B. die Cloudflare-Tunnel-Domain). Strukturierte Daten (JSON-LD) für Person und Blog-Beiträge sind eingebaut.

**Search-Console-Verifizierung (optional):** Im Design-Tab gibt es Felder für den **Google-Search-Console-** und **Bing-Webmaster-Code**. Trägst du dort den Bestätigungs-Code ein (oder fügst das komplette Meta-Tag ein — der Code wird automatisch herausgelesen), setzt MyPage das passende `<meta>`-Tag in den Kopf der Startseite, sodass du die Seite per „HTML-Tag"-Methode bestätigen kannst. Leer lassen, wenn deine Seite dort bereits bestätigt ist.

**Sprache und kanonische Adressen:** Jede indexierbare Seite trägt ein `<link rel="canonical">` **ohne Filter- und Suchparameter** — `/blog`, `/blog?tag=x` und `/blog?q=y` melden alle `/blog`, statt die Signale auf drei fast gleiche Seiten zu verteilen. Dazu kommen `hreflang`-Angaben für die deutsche und die englische Fassung (`?lang=de` / `?lang=en`, plus `x-default`) sowie die Kopfzeilen `Content-Language` und `Vary`.

Welche Sprache eine Adresse **ohne Zusatz** ausliefert, legt *Design → Standardsprache der Website* fest. Die Reihenfolge ist `?lang=` → Cookie → diese Einstellung. Die Browser-Einstellung des Besuchers entscheidet nur bei *Automatisch*. Das ist bewusst so: ein Suchmaschinen-Roboter schickt keine Spracheinstellung mit, und der frühere Rückfall war `en` — auf einer deutschen Domain wurde also die englische Fassung indexiert. Außerdem kann `canonical` nur dann etwas Wahres aussagen, wenn einer Adresse **eine** Sprache fest zugeordnet ist.

**„Gefunden – zurzeit nicht indexiert"** in der Search Console ist kein Fehler der Seite: Google kennt die Adresse aus deiner Sitemap, hat sie aber noch nicht abgerufen. Bei jungen Domains normal. Erzwingen lässt sich nichts, beschleunigen schon — in der Search Console *URL-Prüfung → Indexierung beantragen*. Am meisten bringt das für **`/blog`**, denn erst diese Seite verlinkt alle Beiträge; von dort findet Google den Rest von allein.

**Snippet-Vorschau:** Im Design-Tab (Startseite) sowie in den Dialogen für **Blog-Beitrag**, **eigene Seite**, **Bibliothek-Eintrag** und im **Reisebericht** eines Reisetags steht unter den SEO-Feldern eine Vorschau des Suchtreffers, wie Google ihn baut — Adresse als Pfad-Krumen, Titel, Beschreibung. Sie zeigt auch die **Rückfallkette**: ist kein eigener SEO-Text gesetzt, greift dieselbe Reihenfolge wie auf der Seite (eigenes Feld → Textauszug der ersten 155 Zeichen → Beschreibung der Startseite → Tagline → Bio-Auszug). Zwei Zähler nennen die Länge von Titel (Ziel 20–60 Zeichen) und Beschreibung (Ziel 120–160): grün passt, gelb ist zu kurz, rot wird von Google gekürzt. Die Anzeige selbst kürzt genauso wie Google — am letzten Wortende vor der Grenze, nicht mitten im Wort. Mit **DE/EN** schaltest du zwischen beiden Sprachfassungen um — beim Reisebericht stehen nur die Sprachen zur Wahl, die für diese Reise eingestellt sind. Die Reise-Übersichtsseite `/reiseblog/<slug>` bekommt keine eigene Vorschau: ihre Beschreibung ist der Anrisstext des ersten veröffentlichten Tages, also genau das, was dessen Vorschau schon zeigt.

**✦ KI-Beschreibung:** Mit hinterlegtem Gemini-Schlüssel steht neben der Sprachumschaltung der Vorschau ein Knopf, der aus dem vorhandenen Fließtext eine SEO-Beschreibung schreibt — ein Satz, Ziellänge 120–155 Zeichen, in der Sprache, die gerade gewählt ist. Ist die Fassung dieser Sprache noch leer, geht die vorhandene andere in die Anfrage; geschrieben wird trotzdem in der gewählten. Das Ergebnis landet im Feld, nicht auf der Platte: gespeichert wird der Dialog wie immer von Hand.

**Alle SEO-Beschreibungen (Design-Tab):** Unter der Snippet-Vorschau listet ein eigener Bereich **Startseite, Blog-Beiträge, eigene Seiten und Bibliothek-Einträge** untereinander — je Zeile Art, Titel, Link auf die Seite, Eingabefeld und Zeichenzähler, umschaltbar zwischen DE und EN. Wo kein eigener Text gesetzt ist, steht darunter, was Google heute ausliefert (**„Zeigt heute:"**) — meist der Anfang des Fließtextes. **„Nur ohne eigene Beschreibung"** filtert auf genau diese Lücken, **„✦ Leere per KI füllen"** arbeitet sie der Reihe nach ab (das Stundenlimit der KI gilt weiter). Geschrieben wird alles erst mit **„Beschreibungen speichern"**; bei Blog-Beiträgen geht danach ein IndexNow-Ping raus. Die Zeile der Startseite ist dasselbe Feld wie oben im Design-Formular — eine Änderung hier steht sofort auch dort.

Eine ausführliche Schritt-für-Schritt-Anleitung (Google Search Console, Sitemap einreichen, Tipps für die Platzierung) findest du in [SEO.md](SEO.md).

## RSS-Feed

Unter **`/feed.xml`** liefert MyPage einen RSS-2.0-Feed. Er ist im Kopf jeder öffentlichen Seite verlinkt, Feed-Leser finden ihn also durch die bloße Eingabe der Domain. Adressaten sind Feed-Leser (Feedly, NetNewsWire, Thunderbird), die `feedreader`-Integration von Home Assistant und Automatisierungsdienste wie Buffer, Make oder Zapier, die auf einen neuen Eintrag hin etwas auslösen.

**Was drinsteht** — die 50 neuesten Einträge, neueste zuerst:

| Quelle | Bedingung |
|---|---|
| Blogbeiträge | immer (veröffentlicht, Datum nicht in der Zukunft) |
| Reisetage | wenn *Design → Module → Reiseblog* auf JA steht; nur freigegebene Tage |
| Projekte | Schalter *Projekte im Feed*; nur mit Detailseite. Datum ist der **letzte Push** des Repositories; von Hand angelegte Projekte haben keins und stehen am Ende |
| Bibliothek | Schalter *Bibliothek im Feed* |

Projekte und Bibliothek sind abschaltbar, weil sie sich selten ändern: beim Einschalten spült der Feed den Altbestand einmalig als „neu" durch jeden Reader.

**Je Eintrag** stehen Titel, Adresse, Datum, ein Anriss (`<description>`), der Autorname als `<dc:creator>`, die Schlagwörter als `<category>`, der **Volltext** als `<content:encoded>` mit absoluten Bild- und Link-Adressen und — falls vorhanden — das Titelbild als `<enclosure>`. Genau daran hängen Automatisierungsdienste, wenn sie einen Beitrag mit Bild weiterreichen sollen.

**Autor**: als `<atom:author>` im Kanal und `<dc:creator>` je Eintrag — beides ohne E-Mail-Adresse. Das RSS-Feld `<managingEditor>` wäre die naheliegende Stelle, verlangt aber laut Spezifikation eine Adresse; die Website zeigt sie bewusst nur zerlegt (Schutz vor Adress-Sammlern), und ein Feed ist der denkbar schlechteste Ort, sie doch noch offen hinzuschreiben.

**Links aus importierten READMEs**: Ein GitHub-README verlinkt relativ (`docs/README.md`, `filebox/`). Solche Adressen werden auf das Repository umgebogen (`<repo>/blob/HEAD/…`, Ordner auf `/tree/HEAD/…`, Bilder auf `/raw/HEAD/…`) — sowohl im Feed als auch auf der Projektseite selbst, wo sie sonst genauso ins Leere zeigen.

**Mitglieder-only-Inhalte** stehen mit Titel und Adresse im Feed, aber ohne Text und ohne Bild; an der Stelle des Anrisses steht ein Hinweis. Sie ganz zu verschweigen wäre falsch — auf der Website stehen sie ebenfalls in der Liste, nur gesperrt.

**Sprache**: fest über *Design → Sprache des RSS-Feeds*, nicht über den Browser des Abrufers. Ein Feed-Leser holt dieselbe Adresse für alle seine Nutzer und schickt meist gar keine Sprachkennung; hinge die Sprache daran, lieferte derselbe URL mal Deutsch und mal Englisch. Die andere Fassung gibt es unter `/feed.xml?lang=en` bzw. `?lang=de`.

**Zeitstempel**: Beiträge haben nur ein Datum, keine Uhrzeit. Der Feed setzt **12:00 UTC** — bei `00:00` stünde ein Beitrag für jeden Leser westlich von Greenwich unter dem Vortag. Mehrere Einträge desselben Tages werden um je eine Minute versetzt; das ist keine erfundene Uhrzeit, sondern die einzige Möglichkeit, „selber Tag, diese Reihenfolge" in RSS auszudrücken.

**Abrufe** beantwortet der Feed mit `ETag` und `Cache-Control`; ein unveränderter Feed kommt als `304` zurück. Ohne veröffentlichte Inhalte liefert er einen **gültigen leeren Feed** statt eines Fehlers — ein 404 heißt für einen Reader „kaputt", und manche tragen einen so gemeldeten Feed dauerhaft aus.

## Bilder

**Medien-Browser:** Überall, wo ein Bild gesetzt wird — Titelbild der Bibliothek, Beitrags- und Projektbild, Favicon, Karten-Bild, Mitglieder-Avatar, Team-Fotos, Fotoalben —, führt der Knopf **„Bild wählen"** zu einer Galerie aller bereits hochgeladenen Bilder, neueste zuerst, mit Datum und Größe. Ein Klick übernimmt das Bild; **„Neues Bild hochladen"** in derselben Galerie öffnet den Dateidialog. Bilder, die nirgends verwendet werden, tragen die Plakette **„unbenutzt"** — so ist vor dem Aufräumen im Tab *System* sichtbar, was übrig ist. Angezeigt werden die neuesten 300 Bilder; die Gesamtzahl steht in der Kopfzeile.

Uploads werden automatisch auf maximal 1600 px verkleinert und als WebP gespeichert (GIFs bleiben unverändert, damit Animationen erhalten bleiben). Dabei wird die **EXIF-Orientierung angewendet** (Handy-Hochkant-Fotos erscheinen also richtig herum) und die **Metadaten werden entfernt** — insbesondere ein evtl. eingebetteter **GPS-Standort**, der sonst öffentlich auslesbar wäre. KI-erzeugte Bilder (siehe [Bibliothek](#bibliothek)) laufen durch dieselbe Verarbeitung.

### Kennzeichnung von KI-Bildern

Bilder, die über **✨ Bild generieren** entstanden sind, tragen beim Ausliefern immer den eingebrannten Hinweis **„KI generiert"** (englische Seite: „AI generated") — **unabhängig** vom Schalter „Bilder schützen". Er erfüllt die Transparenzpflicht für KI-erzeugte Inhalte und lässt sich deshalb bewusst nicht abschalten.

- Ist „Bilder schützen" zusätzlich an, stehen beide Angaben in **einer Zeile** unten rechts, z. B. `@deine-domain.de · KI generiert`.
- Der Hinweis erscheint auch beim **direkten Aufruf** der Bildadresse und im **erzeugten PDF** — sonst wäre der Download des PDF der einfachste Weg, die Kennzeichnung loszuwerden.
- Woran das System ein KI-Bild erkennt: der Dateiname endet auf `-ai` (z. B. `a1b2…-ai.webp`). Der Marker steckt im Dateinamen statt in einer Liste, damit er Backup und Wiederherstellung übersteht. Wer eine Datei außerhalb des Add-ons umbenennt, verliert die Kennzeichnung.

**Ausnahme Logo-Designer:** Ein Logo mit eingebranntem Hinweis wäre kein Logo mehr. Erzeugte Logo-Sätze tragen deshalb **keine sichtbare Kennzeichnung** — sie sind auch nicht Teil der Website, sondern Arbeitsmaterial in einem eigenen Ordner und werden von MyPage nirgends ausgeliefert. Die Herkunft steht in den **PNG-Textfeldern** (`Software`, `Source`, `Description`) und in `prompt.txt` neben den Dateien. Wer ein solches Logo veröffentlicht, entscheidet selbst über die Kennzeichnung — das Add-on nimmt ihm diese Entscheidung nicht ab.

**Wasserzeichen in der Bibliothek** wird im Tab *Bibliothek* unter „Bilder schützen" ein- und ausgeschaltet — es ist dieselbe Einstellung wie unter *Inhalt → Fotoalben*, nur an beiden Stellen bedienbar. Es gilt für das Titelbild *und* für Bilder im Markdown-Text eines Eintrags. Eingebundene Fremd-URLs bleiben unangetastet — an fremden Bildern hat weder ein Wasserzeichen noch ein KI-Marker etwas zu suchen.

**KI-Bilder, die du verwirfst, bleiben zunächst liegen.** Das Bild entsteht beim Klick auf „Erzeugen", nicht erst beim Speichern des Eintrags — schließt du den Dialog ohne zu speichern, liegt die Datei weiter unter `/uploads`. Sie verschwindet, sobald du im Tab **System** auf „Unbenutzte Uploads aufräumen" gehst; automatisch gelöscht wird nie etwas. Dasselbe gilt für ein Bild, das du von Hand hochlädst und dann doch nicht speicherst.

### Design
**Design-Vorlagen (1-Klick-Stile):** Oben im Design-Tab gibt es eine Galerie fertiger Vorlagen (z. B. „Elegant Dunkel", „Hell & Clean", „Verspielt", „Tech Neon", „Magazin", „Natur Warm" sowie „Standard"). Ein Klick setzt **Modus, Akzentfarbe, Schrift und Layout** auf einmal — die Felder werden gefüllt, mit „Speichern" wird die Vorlage angewendet. Dein eigenes CSS bleibt dabei unangetastet.

**Ankündigungs-Banner:** Eine schmale Hinweisleiste ganz oben auf allen öffentlichen Seiten (z. B. „Sommerfest am 12.7.!"). Text in DE/EN, optionaler Link (URL oder interner Pfad wie `/formular/anmeldung`) mit eigenem Link-Text, in Akzentfarbe. Wahlweise **schließbar** — Besucher können es ausblenden; wird der Text geändert, erscheint es erneut.

Einzeln einstellbar: Seitentitel, Akzentfarbe (Farbwähler), Standard-Theme (hell/dunkel/auto), Layout (Karten/Liste/Minimal), Schriftart (System-Fonts, Web-Fonts oder eigener Font-Upload), Besucherzähler ein/aus, Navigationsleiste ein/aus, Kontaktformular ein/aus, **Kommentare & Reaktionen** ein/aus, **Selbst-Registrierung** ein/aus (+ Standard-Quota), **Newsletter / Blog-Abo** ein/aus, **Wöchentlicher Rückblick** ein/aus (siehe [Statistik](#statistik)), Footer-Text, eigenes CSS.

- **Unterstützen-Button**: Frei konfigurierbarer Link (Buy Me a Coffee, Ko-fi, PayPal, Patreon, GitHub Sponsors …). Das passende Icon wird automatisch anhand der URL gewählt; eine eigene Beschriftung ist möglich.
- **Termin-/Buchungs-Button**: Link zu einem externen Buchungsdienst (z. B. Calendly, Cal.com). Erscheint mit Kalender-Symbol im Kopfbereich neben dem Unterstützen-Button und öffnet beim Klick einen neuen Tab. Ist kein Link gesetzt, erscheint kein Button. Details siehe [README](README.md#-buchungskalender--termin-button).
- **Navigationsleiste**: Sprungmarken im Kopf zu den vorhandenen Bereichen; folgt der im Inhalt-Tab gewählten Reihenfolge und blendet ausgeblendete/leere Bereiche aus.

### Rechtliches
Impressum und Datenschutzerklärung als Freitext (DE/EN). Der Text wird als **Markdown** ausgegeben: `##` wird eine Überschrift, `**Text**` fett, `- ` eine Aufzählung. Zum Schreiben steht über **„✏️ Bearbeiten“** derselbe [Markdown-Editor](#markdown-editor) mit Werkzeugleiste und Live-Vorschau bereit wie beim Blog. Wer einfach nur Zeilen tippt, bekommt sie unverändert wie bisher. Bis zu 150 000 Zeichen je Feld. Sobald Text eingetragen ist, werden `/impressum` und `/datenschutz` im Footer der öffentlichen Seite verlinkt. Vorlagen liefern z. B. der [Impressum-Generator von e-recht24](https://www.e-recht24.de/impressum-generator.html) und der [Datenschutz-Generator von Dr. Schwenke](https://datenschutz-generator.de) (für Privatpersonen kostenlos). Ein Cookie-Banner ist nicht nötig: MyPage setzt nur technisch notwendige Cookies (Sprachwahl nach Klick, Anmeldung, Umfrage-Kennung) und keinerlei Tracking.

**Aus PDF übernehmen.** Über jedem Textfeld sitzt ein Knopf „📄 Aus PDF". Damit lässt sich das PDF eines Generators direkt einlesen, statt es abzutippen:

- Viele Generatoren (e-Recht24 zum Beispiel) legen den fertigen HTML-Quelltext unsichtbar als Formularfeld ins PDF. Genau der wird bevorzugt gelesen — Überschriftenebenen, Aufzählungen und Links kommen dadurch **exakt** an und werden in Markdown umgesetzt.
- Fehlt so ein Feld, wird die Struktur aus dem Seitenlayout geschätzt: die häufigste Schriftgröße gilt als Fließtext, größere Zeilen werden Überschriften, fette Zeilen werden hervorgehoben. Das steht dann auch so im Fenster, damit klar ist, dass man die Vorschau prüfen sollte.
- Vor dem Übernehmen zeigt ein Fenster links den Text und rechts die gerenderte Fassung — gerendert mit derselben Funktion, die auch die öffentliche Seite benutzt. Der Text ist schon dort bearbeitbar, danach im Feld ohnehin.
- **Ersetzen** überschreibt das Feld, **Anhängen** hängt an vorhandenen Text an. Gespeichert wird beides erst mit „Speichern".
- Passt das PDF nicht zum gewählten Feld (Datenschutz-PDF im Impressum-Feld, englisches PDF im deutschen Feld), erscheint ein Hinweis — verboten wird es nicht.
- Grenzen: höchstens 20 MB und 200 Seiten. Reine Scans ohne Texterkennung enthalten keinen Text und werden abgewiesen.

### Statistik
Aufrufe gesamt, Aufrufe und eindeutige Besucher heute, Verlauf der letzten 30 Tage. Eindeutige Besucher werden über gesalzene Tages-Hashes erkannt; bekannte Bots und Monitoring-Tools zählen nicht in die Statistik.

Zusätzlich gibt es **Top-Seiten** (meistbesuchte Seiten aus den letzten Aufrufen, ohne Bots — für Blog-Beiträge und Projekt-Detailseiten mit Titel statt nur Pfad) sowie Verteilungen nach **Referrern, Browsern und Ländern**.

**Wöchentlicher Rückblick** (im Design-Tab aktivierbar, Standard aus): Montags ab 8 Uhr verschickt MyPage eine Zusammenfassung der Vorwoche — Aufrufe (inkl. Trend gegenüber der Vorwoche), eindeutige Besucher, Datenvolumen (ebenfalls mit Trend), Top-Seite, neue Mitglieder und neue Nachrichten — als **Home-Assistant-Benachrichtigung** und, falls SMTP eingerichtet ist, zusätzlich **per E-Mail** an die Admin-Adresse (`smtp_to`). Pro Kalenderwoche wird höchstens einmal gesendet.

Zusätzlich zeigt das **Besucher-Log** die letzten 500 Aufrufe mit Zeit, Land, IP-Adresse, Browser/User-Agent, Sprache und Referrer (Bots werden markiert). Hinweis: Wer die Seite öffentlich betreibt, sollte die IP-Speicherung ggf. in seiner Datenschutzerklärung erwähnen.

**Datenvolumen:** Die Statistik zeigt, wie viele Daten MyPage ausgeliefert hat — als Kachel für heute und die letzten 30 Tage, dazu ein Tagesbalken mit getrennten Werten für Besucher und Bots. Gezählt wird an der Server-Schnittstelle: jede Antwort samt Kopfzeilen, Uploads getrennt als Eingang. Abgebrochene Downloads zählen nur mit dem, was wirklich hinausging.

Wichtig für die Einordnung: Das ist **nicht die Leitungslast**. Ein vorgelagerter Reverse Proxy (NGINX, NPMplus, Cloudflare) komprimiert selbst und legt TLS obendrauf — bei HTML/CSS/JS liegen die echten Werte deutlich darunter, bei Bildern und PDFs etwa gleichauf. Wer die tatsächliche Last am Anschluss braucht, wertet die Protokolle des Proxys aus. Antwortet der Proxy aus seinem Zwischenspeicher, sieht MyPage die Anfrage gar nicht.

Die Tageswerte stehen in `stats.json` neben Aufrufen und Besuchern und werden einmal pro Minute geschrieben, nicht bei jeder Anfrage. Zusätzlich gibt es `sensor.mypage_traffic_today` und `sensor.mypage_traffic_total`, und der wöchentliche Rückblick nennt das Volumen der Woche samt Trend gegenüber der Vorwoche.

**Länder-Erkennung** (in dieser Reihenfolge):
1. **Cloudflare-Header** `CF-IPCountry` — exakt, falls die Seite hinter Cloudflare läuft
2. **Lokale IP-Tabelle** — Standard, solange die Option `geoip_offline` aktiv ist. Das Add-on hält eine eigene Tabelle „IP-Bereich → Land“ und fragt **keinen Dienst** mehr an: Es verlässt keine Besucher-IP das Add-on, es gibt kein Tageslimit und keinen API-Schlüssel.
   - Quelle ist **[DB-IP Lite](https://db-ip.com)** (*IP Geolocation by DB-IP*, CC BY 4.0). Fällt der Download aus, greift das Add-on auf die Delegationsdateien der fünf Regional Internet Registries zurück (APNIC, RIPE NCC, ARIN, LACNIC, AFRINIC) — dieselben Rohdaten, aus denen NPMplus seine Ländersperre baut. Die Registries führen allerdings das Land der *Zuteilung*: Telekom-Bereiche stehen dort auch mal auf `GB`, Wikimedia-Server in Amsterdam auf `US`. Deshalb ist DB-IP erste Wahl.
   - Die Tabelle liegt unter `/config/geoip/ranges.tsv.gz` (rund 10 MB) und wird wöchentlich erneuert; ein Neustart lädt nichts nach. Im Betrieb kostet sie gut 20 MB Arbeitsspeicher, ein Lookup wenige Mikrosekunden.
   - Fehlende Länder werden **nachträglich ergänzt**: stündlich im Besucher-Log, und nach jeder Tabellen-Erneuerung auch in den Monatsdateien des Besucher-Archivs. Alte Einträge ohne Land füllen sich damit von selbst auf.
   - Genauigkeit: Land, keine Stadt. VPN, Proxy und Anycast-Adressen (z. B. `8.8.8.8`) zeigen den Ort des Dienstes, nicht den des Besuchers.
3. **Browser-Sprache** als Näherung (`de-DE` → Deutschland) — Fallback, wenn beides nicht greift

**Reverse-Proxy (NGINX):** Damit Besucher-IPs, Brute-Force-Schutz und Rate-Limit korrekt arbeiten, muss der Proxy die Original-IP weiterreichen: `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`

## Sicherheit

- Login mit Brute-Force-Schutz: nach 5 Fehlversuchen wird die IP 15 Minuten gesperrt
- Hinter Cloudflare wird die echte Besucher-IP (`CF-Connecting-IP`) verwendet
- Session-Cookies sind `HttpOnly` + `SameSite=Lax`
- Uploads: nur PNG/JPG/GIF/WebP, max. 8 MB, zufällige Dateinamen

### Zwei-Faktor-Authentifizierung (2FA)

Der **direkte Login** (Port 17761) lässt sich optional mit einem zeitbasierten Einmalcode (TOTP) absichern — zusätzlich zu Benutzername und Passwort.

- **Einrichten:** Tab **System → Zwei-Faktor-Authentifizierung → „2FA aktivieren"**. Den angezeigten **QR-Code** mit einer Authenticator-App scannen (z. B. Google Authenticator, Aegis, 1Password) oder das **Geheimnis** manuell eintragen, dann mit einem aktuellen Code bestätigen.
- **Backup-Codes:** Beim Aktivieren werden **10 einmalige Backup-Codes** angezeigt (nur dieses eine Mal). Damit kommst du auch ohne die App rein. Jeder Code funktioniert genau einmal; sie lassen sich jederzeit neu erzeugen.
- **Über Home Assistant (Ingress) ist 2FA nicht erforderlich** und wird dort nicht abgefragt — HA authentifiziert dich bereits. Die 2FA greift ausschließlich beim direkten Zugriff auf Port 17761.
- **Technik:** TOTP nach RFC 6238 (30 s, 6 Stellen, ±1 Fenster Toleranz), umgesetzt mit der Python-Standardbibliothek. Das Geheimnis und die **gehashten** Backup-Codes liegen in `admin_2fa.json` (Dateirechte 600) und werden vom Backup mitgesichert.

#### Zugang verloren? (Wiederherstellung)

Du kannst dich praktisch nie wirklich aussperren — vom bequemsten zum letzten Weg:

1. **Über Home Assistant (einfachster Weg).** Die 2FA gilt **nur** für den direkten Login auf Port 17761. Über die **MyPage-Seitenleiste in HA (Ingress) wird nie ein Code verlangt** — dort authentifiziert dich HA bereits. Du kommst also jederzeit über HA ins Admin-Panel und kannst 2FA dort deaktivieren oder neu einrichten. Das ist dein eingebauter Wiederherstellungs-Pfad.
2. **Backup-Code verwenden.** Beim Login statt des App-Codes einen der 10 Backup-Codes eingeben (jeder genau einmal gültig). Neue Codes gibt es im Panel über „Backup-Codes neu erzeugen".
3. **Notnagel: Datei löschen.** Sind App **und** Backup-Codes weg und es gibt keinen HA-Zugang: `admin_2fa.json` im Add-on-Konfigurationsordner (`\\<host>\addon_configs\XXX_mypage\admin_2fa.json`) löschen und das Add-on neu starten — der Login geht dann wieder nur mit Passwort.

## Veröffentlichen (Cloudflare Tunnel)

Im Tunnel nur `http://<host>:17760` als Ziel eintragen. Das Admin-Panel auf 17761 sollte nicht öffentlich erreichbar sein — falls doch nötig, schützt der Login mit Rate-Limit.

### Besucher-Archiv (Datei)

Das Besucher-Log im Admin ist ein **Ringpuffer** — es zeigt die neuesten 500 Aufrufe, ältere fallen heraus. Wer die vollständige Historie behalten will, schaltet das Archiv ein. Dafür gibt es zwei gleichwertige Wege (Standard: beide aus):

- die Add-on-Option **`visit_file_log`**, oder
- den Knopf **„Archiv jetzt einschalten"** im Admin-Reiter **Explorer**. Der Schalter gehört der Seite selbst und lässt sich dort auch wieder umlegen; die Add-on-Option hat Vorrang, solange sie an ist.

- **Ablage**: `addon_configs/XXX_mypage/visits/visits-JJJJ-MM.csv` — eine Datei je Monat, über den Share direkt erreichbar.
- **Format**: CSV mit Semikolon als Trennzeichen und UTF-8-BOM, also **per Doppelklick in Excel/LibreOffice** korrekt in Spalten und mit richtigen Umlauten. Spalten: `datum`, `ip`, `land`, `browser`, `system`, `pfad`, `referrer`, `sprache`, `bot`, `neuer_besucher`, `user_agent`. Semikolons und Anführungszeichen in Referrer/User-Agent werden maskiert.
- **Aufbewahrung**: `visit_file_keep` (Standard **1 Monat**, `0` = unbegrenzt). Aufgeräumt wird beim **Start des Add-ons** und beim Anlegen einer neuen Monatsdatei — eine gesenkte Frist greift also sofort, weil Home Assistant das Add-on nach jeder Optionsänderung neu startet. Bei `1` reicht das Archiv je nach Tag im Monat 1 bis 31 Tage zurück; das deckt sich mit der in vielen Datenschutzerklärungen zugesagten Frist von 30 Tagen.
- Es werden — wie im Admin-Log — nur **öffentliche IPs** geschrieben; Bots stehen mit `bot=1` drin.
- **Was als Scanner gilt**: eine Sitzung mit **einem** Aufruf, **ohne** Referrer und **ohne** Sprachangabe. Jeder Browser schickt `Accept-Language` mit — wer ohne Sprache genau eine Seite abholt und nie wiederkommt, hat keine Seite angesehen, sondern eine Adresse abgeklopft. Solche Sitzungen blendet der Explorer aus, solange der Bot-Schalter aus ist; unter der Tabelle steht, wie viele es waren. Diese Prüfung greift unabhängig von der Herkunft und damit auch bei Scannern aus Mobilfunk- und Endkundennetzen, für die keine Netzliste reicht.
- **Was als Bot gilt**: die übliche Textsuche in der Browserkennung (`bot`, `crawl`, `spider`, `curl`, …) **und** die Herkunft aus einem bekannten Rechenzentrums-Netz (AWS, Azure, Google, Tencent, Alibaba, Oracle, DigitalOcean, Hetzner, OVH, Linode, Vultr, Scaleway). Scanner geben sich massenhaft als „Safari · iOS" aus und wären sonst nicht von echten Besuchern zu unterscheiden — im Explorer fielen sie als Ein-Seiten-Aufrufe ohne Verweildauer auf. Eigene Netze lassen sich über die Option `visit_bot_nets` ergänzen. Die Netzprüfung greift auch **rückwirkend** beim Auswerten, alte Archivdateien werden dadurch mitbereinigt.
- **Datenschutz**: IP-Adressen sind personenbezogene Daten. Deshalb ist die Option bewusst standardmäßig aus, und die Aufbewahrungsdauer ist begrenzbar. Das Archiv ist **nicht** Teil des Backups (es würde jedes Backup mit der Zeit aufblähen) — sichere den Ordner bei Bedarf selbst.

### Besucher-Explorer

Der Reiter **Explorer** im Admin liest dieses Archiv und macht daraus lesbare Auswertungen — die CSV selbst muss niemand mehr öffnen. Oben wird der Monat gewählt, wahlweise ein einzelner Tag, und ob Suchmaschinen-Bots mitzählen (Standard: nicht).

- **Sitzungen**: eine Zeile je Besuch mit Beginn, Adresse, Browser, Land, Seitenzahl, Dauer und Einstieg → Ausstieg. Ein Klick auf **„Weg ansehen"** öffnet die Zeitleiste: welche Seite in welcher Reihenfolge, mit Verweildauer je Schritt. Zur letzten Seite gibt es keine Verweildauer — es ist nicht erfasst, wann jemand die Seite verlässt.
- **Weg durch die Seite**: häufigste Einstiegs- und Ausstiegsseiten und die häufigsten Seitenfolgen.
- **Wann kommen die Besucher**: Wochentag × Stunde als Raster.
- **Wiederkehrende Besucher**: gleiche Adresse und gleiche Browserkennung an mindestens zwei verschiedenen Tagen.

Eine **Sitzung** ist dabei geschätzt, nicht gemessen: Aufrufe derselben Adresse mit derselben Browserkennung, höchstens **30 Minuten** auseinander. Hinter einem gemeinsamen Anschluss (Mobilfunk, Firmennetz) können mehrere Personen zusammenfallen. Alle Zeiten sind Add-on-Zeit; die CSV speichert keine Zeitzone.

Erfasst werden nur die öffentlichen Seiten (Start, Blog, Projekte, Seiten, Bibliothek, Reiseblog, Suche, Formulare) — keine Bilder, keine Admin-Aufrufe. Die Wege sind dadurch echte Seitenfolgen. Was aus dem Heimnetz kommt, steht ohnehin nicht im Archiv.

## Daten

Alle Inhalte (`site.json`, `stats.json`, `sessions.json`, `uploads/`, `docs/`, `logos/`) liegen im Add-on-Konfigurationsordner und sind über den Share erreichbar: `\\<host>\addon_configs\XXX_mypage`. Sie überleben Add-on-Updates, Neustarts und sogar eine Neuinstallation.

## Jeopardy-Hintergrundmusik (optional)

Das Spiel „Jeopardy" kann eine Hintergrundmelodie abspielen. Aus urheberrechtlichen Gründen wird **keine** Musik mitgeliefert. Wer eine eigene Datei nutzen möchte, legt sie als **`jeopardy_theme.m4a`** direkt in den Add-on-Konfigurationsordner (`\\<host>\addon_configs\XXX_mypage\jeopardy_theme.m4a`). Sie wird dann automatisch ausgeliefert und kann im Spiel über den 🔊-Button an-/ausgeschaltet werden. Fehlt die Datei, läuft das Spiel einfach ohne Musik (der Buzzer-Ticker ist davon unabhängig und immer aktiv).

## Credits / Lizenzhinweise

- **Jeopardy-Quizfragen:** Der Fragen-Pool des Mitglieder-Spiels „Jeopardy" basiert teilweise auf der [Open Trivia Database](https://opentdb.com) und steht unter **CC BY-SA 4.0**. Die Fragen wurden ins Deutsche übersetzt, kuratiert und gefiltert.
- **Hintergrundmusik:** nicht enthalten; nutzerseitig bereitgestellt (siehe oben). Bitte nur Material verwenden, für das du die Rechte hast.
