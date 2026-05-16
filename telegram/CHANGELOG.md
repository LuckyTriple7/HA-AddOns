# Changelog

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
