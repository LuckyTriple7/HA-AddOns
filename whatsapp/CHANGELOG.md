# Changelog

## [1.3.13] - 2026-05-22

### Behoben
- **Reaktionszahl immer noch 2** — robusteres JID-Normalisieren: `normalizeJid()` extrahiert jetzt nur den Ziffern-Teil und setzt immer `@c.us` als Domain. WhatsApp liefert je nach Kontext `@c.us` oder `@s.whatsapp.net`; beide Varianten (plus Device-Suffix) wurden dadurch als unterschiedliche Sender gezählt. Außerdem: ungültige Sender ohne Ziffern (z. B. leerer String) werden im `message_reaction`-Handler verworfen; `connectedPhone` wird beim Login um Device-Suffix bereinigt.

## [1.3.12] - 2026-05-22

### Behoben
- **Reaktionszahl immer noch 2** — `reactions.json` enthielt aus v1.3.10 noch un-normalisierte JID-Duplikate; JIDs werden jetzt auch beim Einlesen aus der Datei bereinigt (`Set` + `normalizeJid`)

## [1.3.11] - 2026-05-22

### Behoben
- **Reaktionszahl doppelt** — Multi-Device-JIDs (`491512345:10@c.us`) wurden nicht mit der normalisierten JID (`491512345@c.us`) aus `/api/react` abgeglichen; Device-Suffix wird jetzt im `message_reaction`-Handler entfernt

## [1.3.10] - 2026-05-22

### Behoben
- **Reaktionen nach Neustart weg** — Reaktionen werden jetzt in `/data/reactions.json` persistiert und beim Start wiederhergestellt; WhatsApp lädt Nachrichten bei jedem Start neu und liefert dabei keine Reaktionsdaten

## [1.3.9] - 2026-05-22

### Behoben
- Erster (unvollständiger) Fix-Versuch für Reaktions-Persistenz — ersetzt durch v1.3.10

## [1.3.8] - 2026-05-22

### Geändert
- Sprachbutton zeigt jetzt `🌐 DE` / `🌐 EN` statt Flaggen-Emojis — Windows unterstützt keine Länder-Flaggen

## [1.3.7] - 2026-05-22

### Behoben
- **Leere Chats nach Sprachauswahl-Feature** — Temporal Dead Zone (TDZ) Bug: `const t` als lokale Variable in der Foto-Renderlogik kollidierte mit der globalen `t()`-Übersetzungsfunktion und warf `ReferenceError` für alle Chats mit Fotos; lokale Variable in `timeEl` umbenannt

## [1.3.6] - 2026-05-22

### Neu
- **Sprachauswahl Deutsch / Englisch** — Flaggen-Button 🇩🇪/🇬🇧 oben rechts in der Topbar; Einstellung wird im Browser gespeichert (Standard: Deutsch)
- Alle UI-Texte übersetzt: Buttons, Tooltips, Spinner, Modals, Statusmeldungen, Datum/Uhrzeit-Format, Weitergeleitet-Labels, Zitat-Blöcke, Fehlermeldungen

## [1.3.5] - 2026-05-21

### Neu
- Zitat-Blase beim Antworten — hover ↩-Button an jeder Nachricht öffnet Reply-Leiste über dem Eingabefeld; Antwort wird mit korrektem Zitat via `msg.reply()` gesendet; Zitat-Blöcke werden auch beim initialen Laden angezeigt
- URLs in Nachrichten werden automatisch zu anklickbaren Links (öffnen im neuen Tab); unterstützt `https://`, `http://` und `www.`-Links

## [1.3.4] - 2026-05-21

### Neu
- Nachrichten weiterleiten — beim Hovern über eine Nachricht erscheint ein ↪-Button; Klick öffnet eine Chat-Auswahl mit Suchfeld; Nachricht wird per `msg.forward()` an den gewählten Chat weitergeleitet

## [1.3.3] - 2026-05-21

### Geändert
- Versionsbump für HA-Update-Erkennung

## [1.3.2] - 2026-05-21

### Neu
- „🗑️ Spam löschen"-Button im Chat-Header — zählt häufig weitergeleitete Nachrichten (Score ≥ 5) im aktuellen Chat und löscht diese nach Bestätigung auf WhatsApp für alle

## [1.3.1] - 2026-05-21

### Neu
- Weitergeleitete Nachrichten werden mit `↪ Weitergeleitet` gekennzeichnet
- Häufig weitergeleitete Nachrichten (Kettenbriefe/Spam, Score ≥ 5) werden rot mit `↪↪ Häufig weitergeleitet` markiert

## [1.3.0] - 2026-05-20

### Behoben
- Fotos nach App-Neustart verschwunden — nach dem initialen Laden der Nachrichten werden alle Fotos automatisch im Hintergrund heruntergeladen (nur wenn `download_media: true`)

## [1.2.9] - 2026-05-17

### Geändert
- Foto-Toggle-Button zeigt jetzt 📷 (AN) bzw. 🚫 (AUS) statt Text; Zustand als Tooltip

## [1.2.8] - 2026-05-17

### Behoben
- Backtick-Konflikt in cleanupMedia() behoben — Add-on startete nicht mehr (SyntaxError)

## [1.2.7] - 2026-05-17

### Neu
- 🗑️-Button in der Topbar (nur bei `download_media: true`): löscht verwaiste Mediendateien die von keiner geladenen Nachricht mehr referenziert werden

## [1.2.6] - 2026-05-17

### Behoben
- Avatar-Farben: Teal-Töne (`#128c7e`, `#075e54`) und UI-Grün (`#3cdb7c`) aus der Farbpalette entfernt — Avatare hatten die gleiche Farbe wie Header/Topbar

## [1.2.5] - 2026-05-17

### Geändert
- `webhook_url` aus config.yaml entfernt — war nie implementiert, nur `webhook_incoming` ist aktiv

## [1.2.4] - 2026-05-17

### Geändert
- „Verbunden"-Text aus der Topbar entfernt — Status-Punkt zeigt den Text jetzt als Mouse-Over-Tooltip (grün = verbunden, gelb = QR scannen, rot = getrennt/Fehler, grau = startet)

## [1.2.3] - 2026-05-17

### Geändert
- 💬-Icon oben links in der Topbar entfernt
- Grünton von `#25d366` auf `#3cdb7c` aufgehellt (Status-Dot, Sende-Button, Reaktions-Badges, Foto-Toggle, Unread-Dot)

## [1.2.2] - 2026-05-17

### Geändert
- Bilder in der Chat-Ansicht größer — Thumbnail-Maxgröße von 240×300 auf 320×400 px erhöht
- Lightbox beim Klick auf ein Foto — schwarzer halbtransparenter Overlay, Bild zentriert in voller Fenstergröße (bis 92vw/92vh); Klick auf den Hintergrund oder Escape schließt die Lightbox

## [1.2.1] - 2026-05-17

### Behoben
- Empfangene Nachrichten zu schmal — `.bubble-row-inner` hatte kein `width: 100%` für `.in`; `max-width: 65%` berechnete sich gegen die geschrumpfte Containerbreite statt gegen die volle Chat-Breite; Blasen sind jetzt gleich breit wie gesendete
- Löschen-Button (✕) erschien rechts neben empfangenen Blasen — `order: -1` jetzt auch für `.in .del-btn`; Hover-Layout ist jetzt `[✕][Blase][😊]` für alle Nachrichten

## [1.2.0] - 2026-05-17

### Geändert
- Gruppen-Mitgliederzahl im Chat-Header — zeigt bei Gruppen die Anzahl der Mitglieder an
- „Zuletzt gesehen"-Funktion entfernt — WhatsApp Web v1.26+ legt `window.Store` nicht mehr global ab; Presence-Subscription ist über die verfügbare API nicht zugänglich

## [1.1.48] - 2026-05-17

### Behoben
- Weißer Rahmen um empfangene Fotos — Foto-Bubbles haben jetzt padding:0 + overflow:hidden; die Bubble selbst stellt die abgerundeten Ecken bereit; Beschriftungen und Uhrzeit behalten eigenes Padding

## [1.1.47] - 2026-05-17

### Neu
- „📥 Fotos nachladen"-Button im Chat-Header (nur wenn `download_media` aktiv) — lädt die letzten 20 Fotos des aktuellen Chats nach; Fotos werden mit 600ms Abstand geladen um WhatsApp/Puppeteer nicht zu überlasten; Button zeigt Fortschritt und aktualisiert die Ansicht alle 2 Sekunden

## [1.1.46] - 2026-05-17

### Neu
- Nachrichten-Reaktionen (👍 ❤️ 😂 😮 😢 🙏) — beim Hovern über eine Nachricht erscheint ein 😊-Button; Klick öffnet den Reaktions-Picker; eigene Reaktion durch erneuten Klick entfernen
- Reaktionen anderer werden in Echtzeit empfangen und als kleine Badges unter der Sprechblase angezeigt
- Eigene Reaktionen sind grün hervorgehoben

## [1.1.45] - 2026-05-17

### Behoben
- Speicheranzeige nicht sichtbar — WhatsApp verwendet relative URLs (`api/storage`), kein `api()`-Helper wie Signal/Telegram

## [1.1.44] - 2026-05-17

### Neu
- Speicheranzeige in der Topbar — zeigt den belegten Speicher des Add-on-Datenverzeichnisses in MB (💾 12.3 MB); aktualisiert sich automatisch alle 60 Sekunden

## [1.1.43] - 2026-05-17

### Behoben
- Gesendete Nachrichten: bubble-row-inner auf width:100% + justify-content:flex-end — garantiert rechtsbündig unabhängig von Nachrichtenlänge

## [1.1.42] - 2026-05-17

### Behoben
- Gesendete Nachrichten zuverlässig rechtsbündig via margin-left: auto

## [1.1.41] - 2026-05-17

### Behoben
- Gesendete Nachrichten liegen jetzt korrekt am rechten Rand an (bubble-wrap fehlte width: 100%)

## [1.1.40] - 2026-05-17

### Behoben
- Scroll-Buttons ↑ ↓ verwendeten falschen Element-ID (`msgList` statt `messages`) — Buttons funktionierten nicht

## [1.1.39] - 2026-05-17

### Neu
- Scroll-Buttons ↑ ↓ in der Topbar — springt direkt an den Anfang oder das Ende der Nachrichten

## [1.1.38] - 2026-05-16

### Behoben
- WhatsApp-Channels aus dem "Aktuelles"-Tab (`@newsletter` JIDs) erschienen als Chats — `isFilteredChat()` filtert jetzt `@broadcast` und `@newsletter` an allen vier Stellen (Startup-Loop, `message`-Event, `message_create`-Event)

## [1.1.37] - 2026-05-16

### Neu
- „Fotos AN/AUS"-Schalter im Topbar neben dem WhatsApp-Logo — blendet Fotos aus und zeigt `📷 Foto` als Text; nur sichtbar wenn `download_media` aktiv; Zustand wird in localStorage gespeichert

## [1.1.36] - 2026-05-16

### Behoben
- Log-Format: Uhrzeit stand am Ende statt nach `[LEVEL]` — Regex trennt jetzt `[LEVEL]` vom Rest und fügt `[HH:MM:SS]` korrekt dazwischen ein

## [1.1.35] - 2026-05-16

### Behoben
- Status-Updates (Stories) und Nachrichten aus dem „Aktuelles"-Tab (`status@broadcast`, `@broadcast`) wurden als Chats angezeigt und lösten HA-Benachrichtigungen aus — werden jetzt vollständig ignoriert

## [1.1.34] - 2026-05-16

### Geändert
- Log-Format einheitlich: alle Meldungen folgen `[LEVEL] [HH:MM:SS] Nachricht`

## [1.1.33] - 2026-05-16

### Geändert
- `SUPERVISOR_TOKEN`-Logik vollständig entfernt — Benachrichtigungen laufen ausschließlich über `ha_token` aus der Konfiguration; `hassio_api`/`homeassistant_api` aus config.yaml entfernt

## [1.1.32] - 2026-05-16

### Neu
- Haken für gesendete Nachrichten: ✓ gesendet (grau), ✓✓ zugestellt (grau), ✓✓ gelesen (blau) — Status aktualisiert sich in Echtzeit über das `message_ack`-Event

## [1.1.31] - 2026-05-16

### Neu
- Option `ha_notifications_privacy` (Standard: aus) — Benachrichtigung zeigt nur „WhatsApp / Neue Nachricht" ohne Absender und Inhalt; alle Nachrichten überschreiben denselben Eintrag (`whatsapp_new_message`)

## [1.1.30] - 2026-05-16

### Behoben
- Uhrzeit in Sprechblasen wurde umgebrochen (`12:54` → `12:5` / `4`) — `white-space: nowrap` verhindert den Zeilenumbruch

## [1.1.29] - 2026-05-16

### Neu
- Option `ha_token` — Long-Lived Access Token aus dem HA-Benutzerprofil; wird als Fallback verwendet wenn `SUPERVISOR_TOKEN` nicht verfügbar ist; Benachrichtigungen gehen dann direkt an `http://homeassistant:8123`

## [1.1.28] - 2026-05-16

### Behoben
- `homeassistant_api: true` in config.yaml ergänzt (für den Supervisor-Proxy zu `/core/api/`)
- Diagnose-Logging in run.sh: zeigt beim Start ob `SUPERVISOR_TOKEN` verfügbar ist oder nicht

## [1.1.27] - 2026-05-16

### Behoben
- `SUPERVISOR_TOKEN` war nicht verfügbar — `hassio_api: true` in config.yaml fehlte; der Supervisor injiziert das Token nur wenn diese Option gesetzt ist

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
