# MyPage — Dokumentation

## Konfiguration

| Option | Beschreibung |
|---|---|
| `username` | Benutzername für das Admin-Panel (Direktzugriff über Port 17761) |
| `password` | Passwort für das Admin-Panel — **unbedingt ändern!** |
| `session_hours` | Gültigkeit der Login-Session in Stunden (Standard: 24) |
| `github_token` | Optional: GitHub-Token (erhöht das API-Limit für Import und Sterne-Updates) |
| `translate_email` | Optional: E-Mail für die DE↔EN-Auto-Übersetzung (MyMemory) — erhöht das kostenlose Tageslimit |
| `visit_log_max` | Größe des Besucher-Logs (50–10000, Standard 500) — Referrer/Browser/Länder werden daraus berechnet |
| `user_journal_max` | Journal-Einträge pro Benutzer (20–1000, Standard 100) |
| `geoip_lookup` | Exakte Länder-Erkennung über ipapi.is (Standard: aus — Besucher-IPs werden an den Dienst übertragen) |
| `geoip_api_key` | Optional: ipapi.is-Key — ohne Key ca. 1.000 Lookups/Tag frei |
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
| `smb_server` | Optional: Adresse des SMB-/CIFS-Servers für den Mitglieder-Speicher (z. B. FritzBox-NAS). Leer = lokaler Speicher im Add-on-Config-Ordner |
| `smb_share` | Name der SMB-Freigabe (z. B. `FRITZ.NAS`) |
| `smb_user` / `smb_password` | Zugangsdaten für die SMB-Freigabe |

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

- **Reihenfolge:** Am Griff per **Drag & Drop** sortieren (Maus + Touch) — die Startseite übernimmt die Reihenfolge sofort. Der Kopfbereich bleibt immer oben, das Kontaktformular immer unten. Auch **Projekte** und **Blog** lassen sich hier positionieren (bearbeitet werden sie in ihren eigenen Tabs).
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
- **Fotoalben**: Alben mit Titel/Beschreibung (DE/EN) und beliebig vielen Bildern (Mehrfach-Upload). Ein Klick öffnet eine Diashow mit Ausblend-Effekt und Autoplay; ein **Klick auf das Bild** zeigt es groß, ein weiterer Klick in voller Auflösung (scroll-/schwenkbar). Bilder werden automatisch auf max. 1600 px verkleinert und als WebP gespeichert. Die Bild-Reihenfolge lässt sich per **Drag & Drop** ändern; ein Klick auf eine Mini-Kachel im Admin zeigt eine Vorschau.
  - **Bildschutz** (Schalter „Bilder schützen"): Brennt ein Wasserzeichen (frei wählbarer Text, Standard `© deine-domain.de`) in alle Album-Bilder ein und deaktiviert Rechtsklick/Ziehen. Das Wasserzeichen wird beim Ausliefern dynamisch erzeugt und gecacht, eine Textänderung greift sofort. Ein vollständiger Download-Schutz ist im Web technisch nicht möglich (Screenshots), das Wasserzeichen ist der wirksame Teil.

### Markdown-Editor
Alle Markdown-Textfelder (Blog-Beiträge, eigene Seiten, Projekt-Details, Bio, Newsletter, Formular-Einleitung & -Danke-Text, Tipps, FAQ-Antworten, Wartungsmodus-Text, Login-Nachricht je Benutzer, Standort-Öffnungszeiten) bieten über den Button **„✏️ Bearbeiten"** einen **Markdown-Editor mit Werkzeugleiste und Live-Vorschau**: Fett, Kursiv, Überschrift, Aufzählung, nummerierte Liste, Zitat, Code, **Link**, **Bild**, **Tabelle**, **Trennlinie** und Emoji. Beim **Bild** kannst du eine URL eingeben oder das Feld leer lassen, um eine Datei direkt **hochzuladen** (wird automatisch auf max. 1600 px verkleinert, als WebP gespeichert und um Metadaten/GPS bereinigt). Tabellen und Codeblöcke werden auf der öffentlichen Seite korrekt dargestellt.

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

### Volltextsuche
Eine seitenweite Suche über **Blog-Beiträge, Projekte und Seiten** (Titel, Inhalt und Tags, jeweils DE & EN). Im Design-Tab aktivierbar (Standard aus). Ist sie an, erscheint ein **Suchfeld im Kopfbereich** der Startseite; die Ergebnisse stehen unter `/suche`.

- **Treffer**: Jeder Treffer zeigt seine Art (Beitrag/Projekt/Seite), den Titel und einen **Auszug mit hervorgehobenen Suchbegriffen**. Mehrere Wörter werden alle gefordert (UND-Suche). Entwürfe, geplante Beiträge und unveröffentlichte Inhalte bleiben außen vor.
- **Mitglieder-Inhalte**: Gesperrte (Mitglieder-only) Beiträge und Seiten erscheinen für Gäste nur als **Titel mit 🔒, ohne Inhalts-Vorschau** — angemeldete Mitglieder sehen die volle Vorschau. So wird kein geschützter Text geleakt.
- **Hinweis**: Die Suchseite ist auf `noindex` gesetzt (keine Indexierung durch Suchmaschinen). Sie nutzt ausschließlich vorhandene Inhalte aus `site.json` — kein zusätzlicher Speicher, kein externer Dienst.

### Formulare
Frei konfigurierbare Formulare über das eine Kontaktformular hinaus — z. B. **Veranstaltungs-Anmeldung, Umfrage oder Anfrage**. Jedes Formular ist unter `/formular/<slug>` erreichbar (optional als Navi-Eintrag).

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
- **Speicher aufräumen**: Entfernt hochgeladene Bilder, die in keinem Beitrag, keiner Seite, keinem Projekt und keinem Album mehr verwendet werden (z. B. nach dem Löschen einer Seite). Vor dem Löschen werden Anzahl und Größe angezeigt; es werden ausschließlich nicht mehr referenzierte Dateien entfernt (geteilte Bilder bleiben erhalten).
- **Weiterleitungen (301)**: Leitet alte/geänderte Adressen auf eine neue um — dauerhaft (301) oder temporär (302). Ziel als interner Pfad (`/neue-seite`) oder vollständige URL (`https://…`). Greift **nur für Pfade, die es nicht (mehr) gibt** — bestehende Seiten werden nie überschrieben. Praktisch, wenn du den Slug einer Seite/eines Beitrags geändert hast und alte Links/Lesezeichen weiter funktionieren sollen.
- **Backup**: Ein Klick lädt ein ZIP mit allen Inhalten, Statistiken, Nachrichten, Blog-Kommentaren, Benutzern, Spielständen und Uploads herunter; über „Backup einspielen" wird es wiederhergestellt.
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

Damit die Benutzerdateien nicht die SD-Karte füllen, können sie auf eine SMB-Freigabe (z. B. FritzBox-NAS) ausgelagert werden: `smb_server`, `smb_share`, `smb_user`, `smb_password` in den Add-on-Optionen setzen und das Add-on neu starten.

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

Eine ausführliche Schritt-für-Schritt-Anleitung (Google Search Console, Sitemap einreichen, Tipps für die Platzierung) findest du in [SEO.md](SEO.md).

## Bilder

Uploads werden automatisch auf maximal 1600 px verkleinert und als WebP gespeichert (GIFs bleiben unverändert, damit Animationen erhalten bleiben). Dabei wird die **EXIF-Orientierung angewendet** (Handy-Hochkant-Fotos erscheinen also richtig herum) und die **Metadaten werden entfernt** — insbesondere ein evtl. eingebetteter **GPS-Standort**, der sonst öffentlich auslesbar wäre.

### Design
**Design-Vorlagen (1-Klick-Stile):** Oben im Design-Tab gibt es eine Galerie fertiger Vorlagen (z. B. „Elegant Dunkel", „Hell & Clean", „Verspielt", „Tech Neon", „Magazin", „Natur Warm" sowie „Standard"). Ein Klick setzt **Modus, Akzentfarbe, Schrift und Layout** auf einmal — die Felder werden gefüllt, mit „Speichern" wird die Vorlage angewendet. Dein eigenes CSS bleibt dabei unangetastet.

**Ankündigungs-Banner:** Eine schmale Hinweisleiste ganz oben auf allen öffentlichen Seiten (z. B. „Sommerfest am 12.7.!"). Text in DE/EN, optionaler Link (URL oder interner Pfad wie `/formular/anmeldung`) mit eigenem Link-Text, in Akzentfarbe. Wahlweise **schließbar** — Besucher können es ausblenden; wird der Text geändert, erscheint es erneut.

Einzeln einstellbar: Seitentitel, Akzentfarbe (Farbwähler), Standard-Theme (hell/dunkel/auto), Layout (Karten/Liste/Minimal), Schriftart (System-Fonts, Web-Fonts oder eigener Font-Upload), Besucherzähler ein/aus, Navigationsleiste ein/aus, Kontaktformular ein/aus, **Kommentare & Reaktionen** ein/aus, **Selbst-Registrierung** ein/aus (+ Standard-Quota), **Newsletter / Blog-Abo** ein/aus, **Wöchentlicher Rückblick** ein/aus (siehe [Statistik](#statistik)), Footer-Text, eigenes CSS.

- **Unterstützen-Button**: Frei konfigurierbarer Link (Buy Me a Coffee, Ko-fi, PayPal, Patreon, GitHub Sponsors …). Das passende Icon wird automatisch anhand der URL gewählt; eine eigene Beschriftung ist möglich.
- **Termin-/Buchungs-Button**: Link zu einem externen Buchungsdienst (z. B. Calendly, Cal.com). Erscheint mit Kalender-Symbol im Kopfbereich neben dem Unterstützen-Button und öffnet beim Klick einen neuen Tab. Ist kein Link gesetzt, erscheint kein Button. Details siehe [README](README.md#-buchungskalender--termin-button).
- **Navigationsleiste**: Sprungmarken im Kopf zu den vorhandenen Bereichen; folgt der im Inhalt-Tab gewählten Reihenfolge und blendet ausgeblendete/leere Bereiche aus.

### Rechtliches
Impressum und Datenschutzerklärung als Freitext (DE/EN). Sobald Text eingetragen ist, werden `/impressum` und `/datenschutz` im Footer der öffentlichen Seite verlinkt. Vorlagen liefern z. B. der [Impressum-Generator von e-recht24](https://www.e-recht24.de/impressum-generator.html) und der [Datenschutz-Generator von Dr. Schwenke](https://datenschutz-generator.de) (für Privatpersonen kostenlos). Ein Cookie-Banner ist nicht nötig: MyPage setzt nur technisch notwendige Cookies (Sprachwahl nach Klick, Admin-Session) und keinerlei Tracking.

### Statistik
Aufrufe gesamt, Aufrufe und eindeutige Besucher heute, Verlauf der letzten 30 Tage. Eindeutige Besucher werden über gesalzene Tages-Hashes erkannt; bekannte Bots und Monitoring-Tools zählen nicht in die Statistik.

Zusätzlich gibt es **Top-Seiten** (meistbesuchte Seiten aus den letzten Aufrufen, ohne Bots — für Blog-Beiträge und Projekt-Detailseiten mit Titel statt nur Pfad) sowie Verteilungen nach **Referrern, Browsern und Ländern**.

**Wöchentlicher Rückblick** (im Design-Tab aktivierbar, Standard aus): Montags ab 8 Uhr verschickt MyPage eine Zusammenfassung der Vorwoche — Aufrufe (inkl. Trend gegenüber der Vorwoche), eindeutige Besucher, Top-Seite, neue Mitglieder und neue Nachrichten — als **Home-Assistant-Benachrichtigung** und, falls SMTP eingerichtet ist, zusätzlich **per E-Mail** an die Admin-Adresse (`smtp_to`). Pro Kalenderwoche wird höchstens einmal gesendet.

Zusätzlich zeigt das **Besucher-Log** die letzten 500 Aufrufe mit Zeit, Land, IP-Adresse, Browser/User-Agent, Sprache und Referrer (Bots werden markiert). Hinweis: Wer die Seite öffentlich betreibt, sollte die IP-Speicherung ggf. in seiner Datenschutzerklärung erwähnen.

**Länder-Erkennung** (in dieser Reihenfolge):
1. **Cloudflare-Header** `CF-IPCountry` — exakt, falls die Seite hinter Cloudflare läuft
2. **GeoIP-Lookup über [ipapi.is](https://ipapi.is)** — exakt, wenn die Option `geoip_lookup` aktiviert ist. Ein Hintergrund-Worker schlägt maximal 20 neue IPs pro Minute nach, jede IP nur einmal (Cache); private IPs werden nie übertragen. **Datenschutz:** Besucher-IPs werden dabei an ipapi.is gesendet — das gehört in die Datenschutzerklärung. Ohne API-Key sind ~1.000 Lookups/Tag frei, dank Cache reicht das für die meisten Seiten locker.
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

## Daten

Alle Inhalte (`site.json`, `stats.json`, `sessions.json`, `uploads/`) liegen im Add-on-Konfigurationsordner und sind über den Share erreichbar: `\\<host>\addon_configs\XXX_mypage`. Sie überleben Add-on-Updates, Neustarts und sogar eine Neuinstallation.

## Jeopardy-Hintergrundmusik (optional)

Das Spiel „Jeopardy" kann eine Hintergrundmelodie abspielen. Aus urheberrechtlichen Gründen wird **keine** Musik mitgeliefert. Wer eine eigene Datei nutzen möchte, legt sie als **`jeopardy_theme.m4a`** direkt in den Add-on-Konfigurationsordner (`\\<host>\addon_configs\XXX_mypage\jeopardy_theme.m4a`). Sie wird dann automatisch ausgeliefert und kann im Spiel über den 🔊-Button an-/ausgeschaltet werden. Fehlt die Datei, läuft das Spiel einfach ohne Musik (der Buzzer-Ticker ist davon unabhängig und immer aktiv).

## Credits / Lizenzhinweise

- **Jeopardy-Quizfragen:** Der Fragen-Pool des Mitglieder-Spiels „Jeopardy" basiert teilweise auf der [Open Trivia Database](https://opentdb.com) und steht unter **CC BY-SA 4.0**. Die Fragen wurden ins Deutsche übersetzt, kuratiert und gefiltert.
- **Hintergrundmusik:** nicht enthalten; nutzerseitig bereitgestellt (siehe oben). Bitte nur Material verwenden, für das du die Rechte hast.
