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
| `smtp_host` | Optional: SMTP-Server — neue Kontaktnachrichten werden per E-Mail gemeldet |
| `smtp_port` | SMTP-Port, meist 587 (STARTTLS) oder 465 (SSL) |
| `smtp_user` / `smtp_password` | Zugangsdaten für den Mailversand (App-Passwort empfohlen) |
| `smtp_to` | Empfängeradresse der Benachrichtigungen |
| `smtp_tls` | `true` für Port 587 (STARTTLS), `false` für Port 465 (SSL) |

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
- **Skills**: kommagetrennte Liste, wird als Chips angezeigt
- **Aktuelles**: kurze News-Einträge mit Datum und optionalem Link
- **Werdegang**: Timeline mit Zeitraum, Titel und Text (jeweils DE/EN)
- **Linksammlung**: Links zu anderen Seiten mit Titel und Beschreibung (DE/EN). Auf der Startseite erscheint ein Button, der ein Overlay mit allen Links öffnet; ein Klick öffnet die Zielseite in einem neuen Tab.
- **Fotoalben**: Alben mit Titel/Beschreibung (DE/EN) und beliebig vielen Bildern (Mehrfach-Upload). Erscheinen auf der Startseite zwischen Skills und Werdegang; ein Klick öffnet eine Diashow mit Ausblend-Effekt und Autoplay. Bilder werden automatisch auf max. 1600 px verkleinert und als WebP gespeichert. Die Bild-Reihenfolge im Album lässt sich per **Drag & Drop** ändern.
  - **Bildschutz** (Schalter „Bilder schützen"): Brennt ein Wasserzeichen (frei wählbarer Text, Standard `© deine-domain.de`) in alle Album-Bilder ein und deaktiviert Rechtsklick/Ziehen. Das Wasserzeichen wird beim Ausliefern dynamisch erzeugt und gecacht, eine Textänderung greift sofort. Ein vollständiger Download-Schutz ist im Web technisch nicht möglich (Screenshots), das Wasserzeichen ist der wirksame Teil.

### Projekte
- **GitHub-Import**: Benutzernamen eingeben → „Repos laden" → Repos anhaken → importieren. Forks werden ausgeblendet, bereits importierte Repos sind ausgegraut. Sterne-Zahlen importierter Projekte werden stündlich automatisch aktualisiert.
- **Manuell**: Projekte mit Titel, Beschreibung (DE/EN), Bild, Demo-Link, GitHub-Link, Tags und Sprache anlegen.
- **Detailseiten**: Mit Detailtext (Markdown) oder Galerie-Bildern bekommt ein Projekt eine eigene Unterseite (`/p/<id>`), die automatisch von der Karte verlinkt wird.
- Reihenfolge per ↑/↓-Buttons ändern.

### Nachrichten
Das Kontaktformular (im Design-Tab aktivierbar) speichert Nachrichten im Tab „Nachrichten". Spam-Schutz dreifach: unsichtbares Honeypot-Feld, ein einfaches Rechen-Captcha („7 + 3 = ?", selbst gehostet, kein externer Dienst) und Rate-Limit (5 Nachrichten/Stunde pro IP). Benachrichtigungen bei neuen Nachrichten wahlweise per **Telegram** (Bot-Token + Chat-ID) und/oder **E-Mail** (SMTP-Optionen) — beides in den Add-on-Optionen, wie bei GitPulse.

### Blog
Beiträge mit Datum, Titel und Markdown-Text (DE/EN). Liste unter `/blog`, einzelne Beiträge unter `/blog/<id>`, die neuesten drei erscheinen auf der Startseite.

### System
- **Wartungsmodus**: Schalter, der die öffentliche Seite durch eine Hinweisseite ersetzt (HTTP 503, eigener Text in DE/EN, Markdown möglich). Das Admin-Panel bleibt erreichbar.
- **Backup**: Ein Klick lädt ein ZIP mit allen Inhalten, Statistiken, Nachrichten und Uploads herunter; über „Backup einspielen" wird es wiederhergestellt.
- **Statischer Export**: Die Seite als fertiges HTML-Paket (deutsch), z. B. für GitHub Pages. Kontaktformular und Sprachumschalter sind im Export deaktiviert.

## Persönlicher Bereich (Mitglieder)

Unter `/bereich` (Login-Link im Footer) gibt es einen passwortgeschützten Dateibereich pro Benutzer — praktisch zum einfachen Teilen von Dateien mit Familie und Freunden.

- **Benutzer anlegen** im Admin-Tab „Benutzer": E-Mail (= Benutzername), Passwort (min. 8 Zeichen), Speicher-Quota. Ist ein Mailserver konfiguriert, bekommt der Benutzer die Zugangsdaten **automatisch per E-Mail** (ebenso bei Passwort-Reset).
- **Sicherheit**: Passwörter werden ausschließlich als scrypt-Hash gespeichert; Brute-Force-Schutz (5 Fehlversuche → 15 Min. Sperre); jeder Benutzer sieht nur den eigenen Bereich; Downloads werden immer als Datei-Anhang ausgeliefert, hochgeladene HTML-Dateien können also nie im Browser ausgeführt werden.
- **Limits**: `user_upload_max_mb` begrenzt die Größe pro Datei (Standard 200 MB), die Quota pro Benutzer ist im Admin einstellbar.

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
| `sensor.mypage_projects` / `_posts` / `_albums` | Anzahl Projekte / Blog-Beiträge / Fotoalben |
| `binary_sensor.mypage_storage_online` | SMB-/Dateispeicher erreichbar (on/off) |
| `binary_sensor.mypage_maintenance` | Wartungsmodus aktiv (on/off) |

Damit lassen sich Dashboards und Automationen bauen (z. B. Benachrichtigung bei Besucherrekord).

## SEO

`sitemap.xml` und `robots.txt` werden automatisch erzeugt. Damit die Sitemap korrekte Links enthält, im Design-Tab die **öffentliche URL** eintragen (z. B. die Cloudflare-Tunnel-Domain). Strukturierte Daten (JSON-LD) für Person und Blog-Beiträge sind eingebaut.

Eine ausführliche Schritt-für-Schritt-Anleitung (Google Search Console, Sitemap einreichen, Tipps für die Platzierung) findest du in [SEO.md](SEO.md).

## Bilder

Uploads werden automatisch auf maximal 1600 px verkleinert und als WebP gespeichert (GIFs bleiben unverändert, damit Animationen erhalten bleiben).

### Design
Seitentitel, Akzentfarbe (Farbwähler), Standard-Theme (hell/dunkel), Besucherzähler ein/aus, Footer-Text.

### Rechtliches
Impressum und Datenschutzerklärung als Freitext (DE/EN). Sobald Text eingetragen ist, werden `/impressum` und `/datenschutz` im Footer der öffentlichen Seite verlinkt. Vorlagen liefern z. B. der [Impressum-Generator von e-recht24](https://www.e-recht24.de/impressum-generator.html) und der [Datenschutz-Generator von Dr. Schwenke](https://datenschutz-generator.de) (für Privatpersonen kostenlos). Ein Cookie-Banner ist nicht nötig: MyPage setzt nur technisch notwendige Cookies (Sprachwahl nach Klick, Admin-Session) und keinerlei Tracking.

### Statistik
Aufrufe gesamt, Aufrufe und eindeutige Besucher heute, Verlauf der letzten 30 Tage. Eindeutige Besucher werden über gesalzene Tages-Hashes erkannt; bekannte Bots und Monitoring-Tools zählen nicht in die Statistik.

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

## Veröffentlichen (Cloudflare Tunnel)

Im Tunnel nur `http://<host>:17760` als Ziel eintragen. Das Admin-Panel auf 17761 sollte nicht öffentlich erreichbar sein — falls doch nötig, schützt der Login mit Rate-Limit.

## Daten

Alle Inhalte (`site.json`, `stats.json`, `sessions.json`, `uploads/`) liegen im Add-on-Konfigurationsordner und sind über den Share erreichbar: `\\<host>\addon_configs\XXX_mypage`. Sie überleben Add-on-Updates, Neustarts und sogar eine Neuinstallation.
