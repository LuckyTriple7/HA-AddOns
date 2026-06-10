# MyPage — Dokumentation

## Konfiguration

| Option | Beschreibung |
|---|---|
| `username` | Benutzername für das Admin-Panel (Direktzugriff über Port 17761) |
| `password` | Passwort für das Admin-Panel — **unbedingt ändern!** |
| `session_hours` | Gültigkeit der Login-Session in Stunden (Standard: 24) |
| `github_token` | Optional: GitHub-Token (erhöht das API-Limit für Import und Sterne-Updates) |
| `telegram_bot_token` | Optional: Bot-Token — neue Kontaktnachrichten werden per Telegram gemeldet |
| `telegram_chat_id` | Chat-ID für die Telegram-Benachrichtigungen |

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

### Projekte
- **GitHub-Import**: Benutzernamen eingeben → „Repos laden" → Repos anhaken → importieren. Forks werden ausgeblendet, bereits importierte Repos sind ausgegraut. Sterne-Zahlen importierter Projekte werden stündlich automatisch aktualisiert.
- **Manuell**: Projekte mit Titel, Beschreibung (DE/EN), Bild, Demo-Link, GitHub-Link, Tags und Sprache anlegen.
- **Detailseiten**: Mit Detailtext (Markdown) oder Galerie-Bildern bekommt ein Projekt eine eigene Unterseite (`/p/<id>`), die automatisch von der Karte verlinkt wird.
- Reihenfolge per ↑/↓-Buttons ändern.

### Nachrichten
Das Kontaktformular (im Design-Tab aktivierbar) speichert Nachrichten im Tab „Nachrichten". Spam-Schutz über ein unsichtbares Honeypot-Feld plus Rate-Limit (5 Nachrichten/Stunde pro IP). Mit Telegram-Bot-Token und Chat-ID in den Add-on-Optionen wirst du sofort benachrichtigt.

### System
- **Wartungsmodus**: Schalter, der die öffentliche Seite durch eine Hinweisseite ersetzt (HTTP 503, eigener Text in DE/EN, Markdown möglich). Das Admin-Panel bleibt erreichbar.
- **Backup**: Ein Klick lädt ein ZIP mit allen Inhalten, Statistiken, Nachrichten und Uploads herunter; über „Backup einspielen" wird es wiederhergestellt.

### Design
Seitentitel, Akzentfarbe (Farbwähler), Standard-Theme (hell/dunkel), Besucherzähler ein/aus, Footer-Text.

### Rechtliches
Impressum und Datenschutzerklärung als Freitext (DE/EN). Sobald Text eingetragen ist, werden `/impressum` und `/datenschutz` im Footer der öffentlichen Seite verlinkt. Vorlagen liefern z. B. der [Impressum-Generator von e-recht24](https://www.e-recht24.de/impressum-generator.html) und der [Datenschutz-Generator von Dr. Schwenke](https://datenschutz-generator.de) (für Privatpersonen kostenlos). Ein Cookie-Banner ist nicht nötig: MyPage setzt nur technisch notwendige Cookies (Sprachwahl nach Klick, Admin-Session) und keinerlei Tracking.

### Statistik
Aufrufe gesamt, Aufrufe und eindeutige Besucher heute, Verlauf der letzten 30 Tage. Eindeutige Besucher werden über gesalzene Tages-Hashes erkannt; bekannte Bots und Monitoring-Tools zählen nicht in die Statistik.

Zusätzlich zeigt das **Besucher-Log** die letzten 500 Aufrufe mit Zeit, IP-Adresse, Browser/User-Agent, Sprache und Referrer (Bots werden markiert). Hinweis: Wer die Seite öffentlich betreibt, sollte die IP-Speicherung ggf. in seiner Datenschutzerklärung erwähnen.

## Sicherheit

- Login mit Brute-Force-Schutz: nach 5 Fehlversuchen wird die IP 15 Minuten gesperrt
- Hinter Cloudflare wird die echte Besucher-IP (`CF-Connecting-IP`) verwendet
- Session-Cookies sind `HttpOnly` + `SameSite=Lax`
- Uploads: nur PNG/JPG/GIF/WebP, max. 8 MB, zufällige Dateinamen

## Veröffentlichen (Cloudflare Tunnel)

Im Tunnel nur `http://<host>:17760` als Ziel eintragen. Das Admin-Panel auf 17761 sollte nicht öffentlich erreichbar sein — falls doch nötig, schützt der Login mit Rate-Limit.

## Daten

Alle Inhalte (`site.json`, `stats.json`, `sessions.json`, `uploads/`) liegen im Add-on-Konfigurationsordner und sind über den Share erreichbar: `\\<host>\addon_configs\XXX_mypage`. Sie überleben Add-on-Updates, Neustarts und sogar eine Neuinstallation.
