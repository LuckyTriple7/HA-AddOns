# Changelog

## [1.0.29] - 2026-05-16

### Geändert
- Log-Format einheitlich: alle Meldungen folgen `[LEVEL] [HH:MM:SS] Nachricht`

## [1.0.28] - 2026-05-16

### Behoben
- Scroll-Position wurde beim automatischen Nachrichten-Refresh zurückgesetzt — beim Hochscrollen bleibt die Position jetzt erhalten; automatisches Runterscrollen erfolgt nur wenn man bereits am Ende war oder neue Nachrichten eintreffen

## [1.0.27] - 2026-05-16

### Neu
- Haken für gesendete Nachrichten: ✓ gesendet (grau), ✓✓ gelesen (blau) — Status aktualisiert sich in Echtzeit über `UpdateReadHistoryOutbox`
- Option `ha_notifications_skip_bots` (Standard: aus) — keine HA-Benachrichtigung wenn der Chat ein Bot ist

## [1.0.26] - 2026-05-16

### Geändert
- `SUPERVISOR_TOKEN`-Logik vollständig entfernt — Benachrichtigungen laufen ausschließlich über `ha_token` aus der Konfiguration; `hassio_api`/`homeassistant_api` aus config.yaml entfernt

## [1.0.25] - 2026-05-16

### Neu
- Option `ha_notifications_privacy` (Standard: aus) — Benachrichtigung zeigt nur „Telegram / Neue Nachricht" ohne Absender und Inhalt; alle Nachrichten überschreiben denselben Eintrag (`telegram_new_message`)

## [1.0.24] - 2026-05-16

### Neu
- Option `ha_token` — Long-Lived Access Token aus dem HA-Benutzerprofil; wird als Fallback verwendet wenn `SUPERVISOR_TOKEN` nicht verfügbar ist; Benachrichtigungen gehen dann direkt an `http://homeassistant:8123`

## [1.0.23] - 2026-05-16

### Behoben
- `homeassistant_api: true` in config.yaml ergänzt (für den Supervisor-Proxy zu `/core/api/`)
- Diagnose-Logging in run.sh: zeigt beim Start ob `SUPERVISOR_TOKEN` verfügbar ist oder nicht

## [1.0.22] - 2026-05-16

### Behoben
- `SUPERVISOR_TOKEN` war nicht verfügbar — `hassio_api: true` in config.yaml fehlte; der Supervisor injiziert das Token nur wenn diese Option gesetzt ist

## [1.0.21] - 2026-05-16

### Neu
- Option `ha_notifications` (Standard: aus) — bei neuen eingehenden Nachrichten wird eine persistente Benachrichtigung in Home Assistant erstellt; pro Chat wird immer nur eine Benachrichtigung angezeigt (Tag `telegram_<chatId>`), neuere Nachrichten überschreiben ältere

## [1.0.20] - 2026-05-16

### Behoben
- Internes `MAX_MSGS`-Limit von 200 auf 300 erhöht — passt jetzt zum erhöhten `fetch_messages_limit`-Maximum

### Geändert
- README aktualisiert — alle aktuellen Konfigurationsoptionen, REST-API-Endpunkte und Funktionen dokumentiert

## [1.0.19] - 2026-05-16

### Geändert
- `fetch_messages_limit` Maximum von 150 auf 300 erhöht

## [1.0.18] - 2026-05-16

### Neu
- Option `debug_mode` (Standard: aus) — einschalten für ausführliches Logging: NewMessage-Events, processMessage mit Typ/Inhalt, addMsg mit Duplikat-Erkennung, Webhook-Aufrufe, gesendete und gelöschte Nachrichten

## [1.0.17] - 2026-05-16

### Behoben
- Log-Spam „50 dialogs loaded" alle 60 Sekunden entfernt — wird jetzt nur einmalig beim Start ausgegeben

## [1.0.16] - 2026-05-16

### Neu
- Ungelesene-Nachricht-Badge in der Sidebar — blauer Kreis erscheint unter dem Zeitstempel wenn eine neue Nachricht eintrifft; verschwindet sobald der Chat geöffnet wird

## [1.0.15] - 2026-05-16

### Behoben
- Löschen-Button wurde beim Hovern nicht rot — CSS-Spezifität von `html.dark .del-btn` überschrieb `.del-btn:hover`; `!important` behebt den Vorrang

## [1.0.14] - 2026-05-16

### Behoben
- Löschen-Symbol im Dark Mode nicht sichtbar — Emoji 🗑 ignoriert CSS `color`; ersetzt durch `✕` mit expliziter Farbsteuerung (grau im Ruhezustand, rot beim Hovern)

## [1.0.13] - 2026-05-16

### Geändert
- Löschen-Button erscheint jetzt seitlich neben der Sprechblase (links bei gesendeten, rechts bei empfangenen Nachrichten) statt innerhalb der Blase

## [1.0.12] - 2026-05-16

### Neu
- Nachrichten löschen — Mülleimer-Symbol erscheint beim Hovern über eine Nachricht; löscht die Nachricht auf Telegram für alle (revoke: true)

## [1.0.11] - 2026-05-16

### Behoben
- "Abmelden"-Button tat nichts — `window.confirm()` ist in HA Ingress (iFrame) von modernen Browsern blockiert; Bestätigungsdialog entfernt

## [1.0.10] - 2026-05-16

### Behoben
- `fetch_messages_limit` hatte keinen Effekt wenn bereits Nachrichten aus dem Disk-Cache geladen waren — Nachrichten werden jetzt von Telegram nachgeladen sobald weniger als das konfigurierte Limit vorhanden sind

## [1.0.9] - 2026-05-16

### Neu
- Option `fetch_messages_limit` (Standard: 50, Maximum: 150) — legt fest wie viele Nachrichten beim ersten Öffnen eines Chats von Telegram geladen werden

## [1.0.8] - 2026-05-16

### Geändert
- Sidebar-Icon zurück auf `phu:telegram`

## [1.0.7] - 2026-05-16

### Geändert
- Sidebar-Icon auf `mdi:message-text` geändert

## [1.0.6] - 2026-05-16

### Behoben
- Bilder wurden nach Neustart mit `download_media: false` noch angezeigt — `mediaFile`-Einträge werden jetzt beim Start aus `messages.json` entfernt, sodass Nachrichten korrekt als `📷 Foto`-Text erscheinen

## [1.0.5] - 2026-05-16

### Neu
- Beim Start mit `download_media: false` werden alle zuvor gecacheten Bilder aus `/data/media/` automatisch gelöscht — der Toggle räumt nun vollständig auf

## [1.0.4] - 2026-05-16

### Neu
- Option `download_media` (Standard: aus) — einschalten damit empfangene Fotos automatisch heruntergeladen und angezeigt werden; ohne die Option erscheint stattdessen `📷 Foto` als Text

## [1.0.3] - 2026-05-16

### Neu
- Bilder (Fotos) werden in der Chat-Ansicht angezeigt — werden beim Empfang heruntergeladen und in `/data/media/` gespeichert; Klick vergrößert das Bild
- Nachrichten die nur ein Bild enthalten (kein Text) wurden bisher ignoriert — jetzt korrekt dargestellt

## [1.0.2] - 2026-05-16

### Geändert
- Sidebar-Icon auf `phu:telegram` geändert (passend zum installierten Icon-Pack)

## [1.0.1] - 2026-05-16

### Behoben
- `node:20-alpine` Base-Image blockiert `/run.sh` durch eigenen ENTRYPOINT — auf `ghcr.io/home-assistant/${BUILD_ARCH}-base:latest` gewechselt

## [1.0.0] - 2026-05-16

### Erstveröffentlichung

- Telegram-Konto via MTProto API (GramJS) verbinden — kein QR-Code, sondern Telefonnummer + SMS/App-Code
- 2-Faktor-Authentifizierung (Cloud-Passwort) unterstützt
- Session wird persistent in `/data/session.txt` gespeichert — kein erneutes Anmelden nach Neustart
- Chat-Liste und Nachrichtenverlauf bleiben nach Neustart erhalten (`/data/chats.json`, `/data/messages.json`)
- Nachrichten senden und empfangen in Echtzeit (Event-basiert via GramJS)
- Emoji-Tastatur in der Eingabe
- Dark/Light-Mode umschaltbar (Standard: dunkel)
- REST-API: `GET /api/status`, `GET /api/chats`, `GET /api/messages/:id`, `POST /api/send`
- Webhook für eingehende Nachrichten (konfigurierbare URL)
- Responsives Design für Desktop und Handy
- Basiert auf [GramJS](https://github.com/gram-js/gramjs) (JavaScript MTProto-Implementierung)
