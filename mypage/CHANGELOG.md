# Changelog

## 0.1.6

- 🔧 **Fix Download-Fehler 500** im Mitglieder-Bereich: Downloads laufen jetzt über einen robusten Pfad (expliziter Datei-Check, kein Conditional-Handling auf CIFS); Fehlerursachen landen ab sofort im Add-on-Log
- 🔧 Fix: Dateien mit Kollisions-Suffix waren nicht herunterladbar/löschbar (Klammern überlebten die Namensprüfung nicht) — neue Uploads nutzen `name_1.ext`
- `/favicon.ico` liefert jetzt das eingestellte Favicon bzw. den Avatar (kein 404-Rauschen mehr in der Konsole)

## 0.1.5

- ✉ **„Zugangsdaten erneut senden"-Button** pro Benutzer: erzeugt ein neues Passwort und verschickt die Willkommens-Mail erneut (mit Sicherheitsabfrage; das alte Passwort wird ungültig)

## 0.1.4

- 📧 Willkommens-Mail: Login-Link nutzt die öffentliche URL aus dem Design-Tab (`https://deine-domain/bereich`); fehlt sie, wird die Zeile weggelassen statt ein verwirrendes „/bereich" zu zeigen
- ⚠ Warnung beim Benutzer-Anlegen/Passwort-Reset, wenn die öffentliche URL noch nicht gesetzt ist
- Mail-Text verständlicher formuliert („persönlicher Dateibereich")

## 0.1.3

- 🔧 Fix Ordner-Browser: Auswahl sprang nach dem Speichern auf die Basis zurück; jetzt bleibt der Browser im gewählten Ordner stehen und der **aktive Ordner** wird dauerhaft separat angezeigt

## 0.1.2

- 📁 **Admin kann Benutzern Dateien hinterlegen**: neuer „Dateien"-Button pro Benutzer (auflisten, hochladen, herunterladen, löschen)
- 🎲 **Passwortgenerator** beim Anlegen und Zurücksetzen (8 Zeichen, Groß/Klein/Zahlen, keine Sonderzeichen, keine verwechselbaren Zeichen)
- 📂 **Speicherort wählbar**: Ordner-Browser im Benutzer-Tab — Unterordner auf dem SMB-Share (oder lokal) festlegen
- 🔄 **SMB-Watchdog**: prüft jede Minute und verbindet nach FritzBox-/NAS-Neustart automatisch neu (`soft`-Mount gegen Hänger)
- 🚫 **Kein Fallback mehr auf lokalen Speicher**: Ist der SMB-Speicher weg, geht der Dateibereich offline — Benutzer und Admin sehen eine klare Meldung statt versehentlich lokal gespeicherter Dateien

## 0.1.1

- 🔧 **Fix SMB-Mount** („Permission denied"): eigenes AppArmor-Profil mit mount/umount-Rechten (wie bei FileBox)

## 0.1.0

- 🔐 **Persönlicher Bereich** (`/bereich`, Login-Link im Footer): Multi-User-Dateiablage zum einfachen Teilen
  - Benutzername = E-Mail-Adresse, Passwörter nur als scrypt-Hash gespeichert
  - Neuer Admin-Tab „Benutzer": anlegen, löschen, Passwort zurücksetzen, Speicher-Quota pro Benutzer
  - 📧 Automatische **Willkommens-Mail** mit Zugangsdaten beim Anlegen (wenn SMTP konfiguriert), ebenso bei Passwort-Reset
  - Jeder Benutzer sieht nur seine eigenen Dateien; Uploads zählen gegen die Quota; Downloads immer als Attachment (kein XSS)
  - Brute-Force-Schutz wie beim Admin-Login, eigene Session-Cookies
- 💾 **Optionaler SMB-Mount**: Mitglieder-Dateien auf eine Netzwerk-Freigabe legen statt auf die SD-Karte (`smb_server`, `smb_share`, `smb_user`, `smb_password`); bei Mount-Fehler automatischer Fallback auf lokalen Speicher
- Neue Option `user_upload_max_mb` (Standard 200) als Upload-Limit pro Datei

## 0.0.8

- 🌐 **Exakte Länder-Erkennung per GeoIP** (ipapi.is) — neue Optionen `geoip_lookup` (Standard: aus, da Besucher-IPs an den Dienst übertragen werden) und `geoip_api_key` (optional, ohne Key ~1.000 Lookups/Tag frei)
- Hintergrund-Worker mit IP-Cache (max. 20 Lookups/Minute, jede IP nur einmal), private IPs werden nie gesendet; bestehende Log-Einträge ohne Land werden nachgetragen

## 0.0.7

- 📧 **E-Mail-Benachrichtigung** bei neuen Kontaktnachrichten (SMTP, analog zu GitPulse) — neue Optionen `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_to`, `smtp_tls`
- Benachrichtigungen (Telegram + E-Mail) blockieren das Kontaktformular nicht mehr (Versand im Hintergrund)

## 0.0.6

- 🌍 **Länder-Statistik**: Verteilung mit Flagge und Ländername im Statistik-Tab, Flagge auch im Besucher-Log
- Erkennung über Cloudflare-Header (`CF-IPCountry`) oder näherungsweise über die Browser-Sprache (NGINX & Co., keine GeoIP-Datenbank nötig)

## 0.0.5

- GitHub-Import: Benutzername wird automatisch aus dem Profil vorbefüllt, neutrale Platzhalter

## 0.0.4

- 🔢 **Fix Besucherzähler**: Der öffentliche Zähler zeigt jetzt eindeutige Besucher (pro Tag dedupliziert) — ein Browser-Refresh zählt nicht mehr hoch
- 🎨 **Layout-Themes**: Projekte als Karten, Liste oder Minimal-Ansicht
- 📰 **Blog**: Beiträge mit Markdown unter `/blog`, die neuesten drei auf der Startseite — neuer Admin-Tab
- 🏠 **Home-Assistant-Sensoren**: Aufrufe/Besucher (gesamt + heute) als `sensor.mypage_*` in HA
- 📥 **README-Import**: Beim GitHub-Import optional das README als Detailtext übernehmen
- 🌗 **Auto-Theme**: folgt auf Wunsch der Systemeinstellung des Besuchers
- 🚫 **Eigene 404-Seite** im Seiten-Design
- 🔍 **SEO**: `sitemap.xml`, `robots.txt` mit Sitemap-Verweis, JSON-LD (Person + BlogPosting), Feld „Öffentliche URL"
- 📦 **Statischer Export**: komplette Seite als HTML-Paket (z. B. für GitHub Pages)
- 🖼 **Bild-Optimierung**: Uploads werden auf max. 1600 px verkleinert und als WebP gespeichert
- 📊 Statistik: neue Karte „Besucher gesamt"

## 0.0.3

- 🛠 **Wartungsmodus**: Schalter im neuen System-Tab — öffentliche Seite zeigt einen Hinweis (HTTP 503), Admin bleibt erreichbar
- 👁 **Live-Vorschau** der öffentlichen Seite im Design-Tab
- ✍️ **Markdown** in Bio, Projekt-Detailtexten und Wartungshinweis
- 🛡 **E-Mail-Schutz**: Adresse wird erst im Browser zusammengesetzt (Spam-Bots sehen sie nicht im HTML)
- ⭐ **Favicon-Upload** in den Design-Einstellungen
- 📚 **Neue Sektionen**: Skills (Chips), Werdegang (Timeline), Aktuelles (News-Liste) — neuer Tab „Inhalte"
- 📄 **Projekt-Detailseiten** (`/p/<id>`) mit Markdown-Text und Bilder-Galerie inkl. Lightbox
- 📊 **Statistik erweitert**: Top-Referrer und Browser-Verteilung, Pfad im Besucher-Log
- 💾 **Backup & Restore**: Inhalte, Statistik, Nachrichten und Uploads als ZIP sichern/einspielen
- 📨 **Kontaktformular** mit Honeypot-Spamschutz und Rate-Limit; Nachrichten im neuen Tab „Nachrichten", optional Telegram-Benachrichtigung (neue Optionen `telegram_bot_token`, `telegram_chat_id`)

## 0.0.2

- ⚖️ Neuer Tab „Rechtliches": Impressum und Datenschutzerklärung (DE/EN) pflegbar
- Links erscheinen automatisch im Footer der öffentlichen Seite (`/impressum`, `/datenschutz`), sobald Text eingetragen ist

## 0.0.1

- 🎉 Erstveröffentlichung
- Öffentliche Homepage auf Port 17760 (Profil, Projektkarten, Social-Links, DE/EN, Hell/Dunkel)
- Admin-Panel auf Port 17761 mit Login, Brute-Force-Schutz und HA-Ingress-Unterstützung
- GitHub-Import: Repos per Klick übernehmen, Sterne werden stündlich aktualisiert
- Design-Einstellungen: Akzentfarbe, Standard-Theme, Seitentitel, Footer
- Besucherzähler mit Tagesstatistik und Besucher-Log (Zeit, IP, Browser, Sprache, Referrer, Bot-Erkennung)
- Bild-Uploads für Avatar und Projekt-Screenshots
