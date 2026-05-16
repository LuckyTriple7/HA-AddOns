# Changelog

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
