# Changelog

## [1.1.26] - 2026-05-16

### Behoben
- HA-Benachrichtigung kam nicht an — fehlender Response-Handler im HTTP-Request führte dazu dass der Socket nicht freigegeben wurde; außerdem wird der Versuch jetzt immer im Log sichtbar (`[INFO] Sending HA notification: …`) statt nur im Debug-Modus

## [1.1.25] - 2026-05-16

### Neu
- Option `ha_notifications` (Standard: aus) — bei neuen eingehenden Nachrichten wird eine persistente Benachrichtigung in Home Assistant erstellt; pro Chat wird immer nur eine Benachrichtigung angezeigt (Tag `whatsapp_<chatId>`), neuere Nachrichten überschreiben ältere

## [1.1.24] - 2026-05-16

### Geändert
- README aktualisiert — alle aktuellen Konfigurationsoptionen, REST-API-Endpunkte und Funktionen dokumentiert

## [1.1.23] - 2026-05-16

### Behoben
- Debug-Logs für eingehende Nachrichten fehlten — `message_create`-Event und `addMsg()` werden jetzt ebenfalls geloggt; deckt alle Nachrichtenpfade ab

## [1.1.22] - 2026-05-16

### Behoben
- Add-on startete nicht mit `debug_mode: true` — `DEBUG`-Variable wurde vor ihrer Deklaration verwendet (temporal dead zone); Log-Zeile an die richtige Stelle verschoben

## [1.1.21] - 2026-05-16

### Neu
- Option `debug_mode` (Standard: aus) — einschalten für ausführliches Logging: eingehende Nachrichten mit Typ/Absender/Vorschau, Media-Downloads, Webhook-Aufrufe, gesendete und gelöschte Nachrichten

## [1.1.20] - 2026-05-16

### Neu
- Ungelesene-Nachricht-Badge in der Sidebar — kleiner grüner Kreis erscheint unter dem Zeitstempel wenn eine neue Nachricht eintrifft; verschwindet sobald der Chat geöffnet wird

## [1.1.19] - 2026-05-16

### Behoben
- Löschen-Button wurde im Light Mode beim Hovern nicht rot — CSS-Spezifität von `html.light .del-btn` überschrieb `.del-btn:hover`; `!important` behebt den Vorrang

## [1.1.18] - 2026-05-16

### Behoben
- Löschen-Symbol im Dark Mode nicht sichtbar — Emoji 🗑 ignoriert CSS `color`; ersetzt durch `✕` mit expliziter Farbsteuerung (grau im Ruhezustand, rot beim Hovern)

## [1.1.17] - 2026-05-16

### Geändert
- Löschen-Button erscheint jetzt seitlich neben der Sprechblase (links bei gesendeten, rechts bei empfangenen Nachrichten) statt innerhalb der Blase

## [1.1.16] - 2026-05-16

### Neu
- Nachrichten löschen — Mülleimer-Symbol erscheint beim Hovern über eine Nachricht; löscht die Nachricht auf WhatsApp für alle (`msg.delete(true)`)

## [1.1.15] - 2026-05-16

### Behoben
- JavaScript-Syntax-Fehler durch unescapte Anführungszeichen im Foto-Rendering — `\'` in Template-Literal wurde zu `'` aufgelöst und zerstörte den Single-Quote-String im Browser; ganzes `<script>`-Tag lud nicht → QR-Code und Status-Polling funktionierten nicht

## [1.1.14] - 2026-05-16

### Behoben
- "Session zurücksetzen" und "Abmelden" taten nichts — `window.confirm()` ist in HA Ingress (iFrame) von modernen Browsern blockiert; Bestätigungsdialoge entfernt

## [1.1.13] - 2026-05-16

### Behoben
- Puppeteer-Frame-Fehler beim Start mit `download_media: true` — historische Nachrichten beim Startup-Laden werden nicht mehr heruntergeladen (Puppeteer kann das nicht parallel zu hunderten Nachrichten); Bilder werden nur noch für neu eingehende Nachrichten geladen

## [1.1.12] - 2026-05-16

### Neu
- Option `download_media` (Standard: aus) — einschalten damit empfangene Fotos und Sticker automatisch heruntergeladen und in der Chat-Ansicht angezeigt werden; Klick vergrößert das Bild
- Ohne die Option erscheint `📷 Foto` als Textplatzhalter statt des Bildes
- Bilder werden in `/data/media/` gespeichert und bleiben nach Neustart erhalten

## [1.1.11] - 2026-05-16

### Behoben
- Emoji-Picker: grüne Kreise um Emojis — WhatsApp's globaler `#send-bar button`-Stil überschrieb die Emoji-Buttons; spezifischere Selektoren verwenden

## [1.1.10] - 2026-05-16

### Behoben
- `dark_mode: false` hatte keinen Effekt — jq `//`-Operator behandelt `false` als leer und gab immer `true` zurück; explizites `if`-Statement verwendet

## [1.1.9] - 2026-05-16

### Neu
- Option `dark_mode` (Standard: ein = dunkler Hintergrund) in den Add-on-Einstellungen — ausschalten für helles Theme

## [1.1.8] - 2026-05-16

### Neu
- Emoji-Tastatur in der Chat-Eingabe — 😊-Button öffnet Picker mit ~100 Emojis; Klick fügt Emoji an der Cursor-Position ein

## [1.1.7] - 2026-05-16

### Behoben
- Kontakte ohne Telefonbucheintrag zeigten nur die Nummer — WhatsApp-Profilname (`pushname`) wird jetzt beim Start über `getContactById()` abgefragt

## [1.1.6] - 2026-05-16

### Neu
- Mobiles Layout: auf schmalen Bildschirmen wechselt die Ansicht zwischen Chat-Liste und Konversation (wie WhatsApp auf dem Handy), mit Zurück-Button im Chat-Header

## [1.1.5] - 2026-05-16

### Geändert
- Abmelden/Reset startet den Prozess nicht mehr neu (`process.exit` entfernt) — der WhatsApp-Client wird stattdessen direkt im laufenden Prozess neu initialisiert; der Express-Server bleibt immer erreichbar, kein ERR_CONNECTION_REFUSED mehr möglich

## [1.1.4] - 2026-05-16

### Behoben
- Nach Abmelden blieb die verbundene Ansicht — `setInterval(refresh)` feuerte noch während der 500ms vor dem Server-Exit und überschrieb den Spinner; `refresh()` wird jetzt während des Neustarts blockiert (`restartPolling`-Flag)

## [1.1.3] - 2026-05-16

### Behoben
- Add-on startet nach Abmelden nicht neu — Chromium hinterlässt `SingletonLock` beim erzwungenen Exit; wird jetzt beim Start in `run.sh` gelöscht

## [1.1.2] - 2026-05-16

### Behoben
- Add-on startet nach Abmelden/Reset nicht neu — `process.exit(0)` durch `process.exit(1)` ersetzt damit s6 den Prozess als Absturz wertet und neu startet
- Poll-Wartezeit auf 8 Sekunden erhöht

## [1.1.1] - 2026-05-16

### Behoben
- ERR_CONNECTION_REFUSED nach "Session zurücksetzen" — doppelter Poll-Loop verhindert, `location.reload()` durch direktes `refresh()` ersetzt

## [1.1.0] - 2026-05-16

### Behoben
- Nach dem Abmelden blieb der Bildschirm schwarz — Add-on startet jetzt neu, Spinner wartet aktiv bis Server wieder erreichbar ist (kein fixer Timeout)
- Status `disconnected` zeigt jetzt den Spinner mit Text "Abgemeldet — starte neu…"

## [1.0.8] - 2026-05-16

### Behoben
- Session überlebt Neustart nicht — `addon_config`-Mount war auf dieser HA-Installation nicht zuverlässig; Session-Verzeichnis auf `/data/session` (immer persistenter Add-on-Datenpfad) umgestellt
- `addon_config:rw` aus `map` entfernt (nicht mehr benötigt)

## [1.0.7] - 2026-05-16

### Behoben
- Session wird nach Neustart nicht wiederhergestellt — `LocalAuth` ersetzt durch `NoAuth` + direktes `puppeteer.userDataDir`

## [1.0.6] - 2026-05-16

### Behoben
- Crash "No data found for resource" (Puppeteer ProtocolError) — wird jetzt abgefangen, Add-on bleibt stabil
- "auth timeout" auf langsamer Hardware (z.B. Raspberry Pi) — Auth-Timeout deaktiviert (`authTimeoutMs: 0`)
- Kein Abmelden-Button bei hängendem Start — neuer "Session zurücksetzen"-Button im Ladescreen (löscht Session-Dateien und startet neu)

### Neu
- Anzahl geladener Chats konfigurierbar (`initial_chats`, Standard: 30)
- Anzahl Nachrichten pro Chat beim Start konfigurierbar (`initial_messages`, Standard: 20)

## [1.0.4] - 2026-05-16

### Behoben
- Fehler "No LID for user" beim Senden — vollständige JID (`nummer@c.us`) wird jetzt übergeben

### Neu
- WhatsApp Web-Oberfläche: Chat-Liste links, Konversation rechts (wie WhatsApp Web)
- Nachrichten werden pro Chat gespeichert und angezeigt
- Avatar mit Initialen und Farbe pro Kontakt
- Chat auswählen → Nachrichten dieser Konversation sehen + antworten
- Suchfeld zum Filtern der Chat-Liste
- Neuer API-Endpoint: `GET /api/chats`

## [1.0.3] - 2026-05-15

### Behoben
- Nachrichten wurden beim Start nicht angezeigt — beim Verbinden werden jetzt die letzten 20 Nachrichten aus den 30 zuletzt aktiven Chats geladen
- Duplikat-Schutz für Nachrichten (Set mit gesehenen IDs)

## [1.0.2] - 2026-05-15

### Neu
- Chat-Ansicht: gesendete und empfangene Nachrichten als Sprechblasen (WhatsApp-Stil)
- Eigene Nachrichten (gesendet vom Handy) werden ebenfalls angezeigt
- Datums-Trennlinie zwischen Tagen
- Nachrichten-Feed scrollt automatisch nach unten
- `/api/messages` Endpoint für Nachrichtenhistorie

## [1.0.1] - 2026-05-15

### Behoben
- Chromium-Pfad wird jetzt automatisch erkannt (`/usr/bin/chromium-browser`, `/usr/bin/chromium`, etc.)
- `--disable-background-networking` entfernt — blockierte WhatsApp's WebSocket-Verbindung
- `--single-process` entfernt — verursachte Crashes mit neuerem Chromium
- Besseres Fehler-Logging beim Start
- Port als Umgebungsvariable konfigurierbar (Standard: 3000)
- Direkter Port-Zugriff (ohne Ingress) möglich

## [1.0.0] - 2026-05-15

### Erstveröffentlichung

- WhatsApp Web Session mit persistentem Login (QR-Code einmal scannen)
- Web-UI direkt in der HA-Sidebar (QR-Anzeige, Status, Nachricht senden)
- REST-API: `GET /api/status`, `POST /api/send`, `GET /api/qr`, `POST /api/logout`
- Webhook für eingehende Nachrichten (konfigurierbare URL)
- Webhook für gesendete Nachrichten (konfigurierbare URL)
- Session-Persistenz über Add-on-Updates hinweg
