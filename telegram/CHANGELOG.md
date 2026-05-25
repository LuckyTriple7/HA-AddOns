# Changelog

## [1.2.0] - 2026-05-25
- Version auf 1.2.0 angehoben — stabile Version

## [1.1.26] - 2026-05-25
- Fix: Konfig-Log "Konfiguration", "gesetzt"/"nicht gesetzt" auf Englisch

## [1.1.25] - 2026-05-25
- UX: Emoji-Picker-Button (😊) wird ausgeblendet wenn bereits Reaktions-Badges vorhanden sind — Reaktion per Badge-Klick reicht aus; Button erscheint wieder wenn alle Reaktionen entfernt wurden

## [1.1.24] - 2026-05-25
- Neu: Chat-Statistik im Header — Gesamtnachrichten, ↑ gesendet, ↓ empfangen, 📷 Fotos, seit Datum (zweisprachig DE/EN)
- Entfernt: Hardcoded Nachrichten-Limit von 300 — Nachrichten werden unbegrenzt auf Disk gespeichert

## [1.1.23] - 2026-05-25
- Neu: Beim Start werden alle konfigurierten Optionen im Log ausgegeben (API-Credentials und HA-Token werden nur als "gesetzt"/"nicht gesetzt" angezeigt)

## [1.1.22] - 2026-05-24
- Neu: Chat-Export als HTML — 💾 Button im Chat-Header; Bilder inline eingebettet, Dokumente als 📄-Eintrag

## [1.1.21] - 2026-05-24
- Fix: Gesendete Dokumente (PDF etc.) zeigen jetzt 📄-Icon + Dateiname im Chat statt leerem Bubble

## [1.1.20] - 2026-05-24
- Fix: 📎-Button steht jetzt nach dem 😊-Button (wie bei WhatsApp)
- Fix: Gesendete Bilder/Dokumente erscheinen sofort als Vorschau im Chat (Message-Store wird nach Senden befüllt)

## [1.1.19] - 2026-05-24
- Neu: Datei-Upload über 📎-Button — Bilder und Dokumente direkt aus dem Browser senden (max. 64 MB)
- Dateien werden nur im RAM gehalten, kein Temp-Ordner; Bilder optional in /config/media gespeichert

## [1.1.18] - 2026-05-24
- Neu: Filter-Tabs „Alle / Privat / Gruppen / Kanäle / Bots" in der Chat-Sidebar
- Neu: Typ-Avatare — 👥 Gruppen, 📢 Kanäle, 🤖 Bots (privat weiterhin farbige Initialen)

## [1.1.17] - 2026-05-24
- Fix: Nachrichtenblasen breiter (max-width 65% → 80%) — verhindert zu frühe Zeilenumbrüche

## [1.1.16] - 2026-05-23

### Geändert
- **Datenspeicherung auf addon_config umgestellt** — Session, Chats, Nachrichten und Medien liegen jetzt unter `/config` (addon_config-Share, im Datei-Manager sichtbar) statt unter `/data`; bestehende Daten werden beim ersten Start automatisch migriert

## [1.1.15] - 2026-05-22

### Neu
- **GramJS Version im Log** — beim Start wird die installierte GramJS-Version geloggt: `[INFO] GramJS (telegram) v2.x.x`

## [1.1.14] - 2026-05-22

### Neu
- **Sprachauswahl Deutsch / Englisch** — `🌐 DE` / `🌐 EN` Button in der Topbar; Einstellung wird im Browser gespeichert (Standard: Deutsch)
- Alle UI-Texte übersetzt: Auth-Overlays, Buttons, Tooltips, Modals, Spinner, Datum/Uhrzeit-Format, Reactions, Fehlermeldungen

## [1.1.13] - 2026-05-21

### Neu
- URLs in Nachrichten (`https://`, `http://`, `www.`) werden automatisch als anklickbare Hyperlinks dargestellt (öffnen im neuen Tab)

## [1.1.12] - 2026-05-17

### Neu
- 🗑️-Button in der Topbar (nur bei `download_media: true`): löscht verwaiste Mediendateien die von keiner geladenen Nachricht mehr referenziert werden

### Geändert
- Foto-Toggle-Button zeigt jetzt 📷 (AN) bzw. 🚫 (AUS) statt Text; Zustand als Tooltip

## [1.1.11] - 2026-05-17

### Neu
- Video-Nachrichten zeigen jetzt `📹 Video` als Platzhalter-Text in der Blase (analog zu `📷 Foto` bei Bildern); hat das Video eine Bildunterschrift, wird stattdessen die Bildunterschrift angezeigt

## [1.1.10] - 2026-05-17

### Behoben
- Reaktionszahlen beim Laden von Nachrichten falsch — `processMessage` liest jetzt `rawMsg.reactions.results` aus dem GramJS-Objekt; historische Nachrichten zeigen damit direkt die echten Telegram-Zähler statt nur lokal gesetzte Werte
- `savedReactions` beim Reload nur noch als Fallback wenn Telegram keine Daten liefert (nicht mehr überschreibend)

## [1.1.9] - 2026-05-17

### Behoben
- Reaktionen verschwanden nach Chat-Reload — Refresh-Endpoint sichert `reactions`/`myReaction` aller Nachrichten vor dem Cache-Löschen und stellt sie nach dem Telegram-Refetch wieder her
- Reaktionen anderer Nutzer wurden nach AddOn-Neustart nicht gespeichert — `UpdateMessageReactions`-Handler ruft jetzt `scheduleSave()` auf

## [1.1.8] - 2026-05-17

### Behoben
- Weißer Rand um Bilder — Foto-Blasen bekommen Klasse `photo-bubble` mit `padding: 0` und `overflow: hidden`; Uhrzeit erscheint als halbdurchsichtiges Overlay unten rechts auf dem Bild (weißer Text auf dunklem Hintergrund); Bildunterschriften haben eigenes `photo-caption`-Div mit Innenabstand

## [1.1.7] - 2026-05-17

### Behoben
- Reactions-Bar erschien rechts neben der Blase statt darunter — neues `.bubble-stack`-Div (column-flex) umschließt Blase + Bar; `react-btn` und `del-btn` bleiben Geschwister davon in `.bubble-row-inner` (row-flex)
- 😊-Button erschien mittig im Foto bei Bildnachrichten — `bubble-row-inner` hat jetzt `align-items: flex-end`, Buttons erscheinen unten rechts/links neben der Blase, nie überlappend

## [1.1.6] - 2026-05-17

### Behoben
- Reactions-Bar erschien auf gleicher Zeile wie die Blase — `.bubble-row` ist jetzt Column-Flex, `.bubble-row-inner` übernimmt die horizontale Anordnung; Bar erscheint korrekt darunter
- Reaktionen verschwanden nach Chat-Reload — werden jetzt direkt in `renderMessages` aus den Message-Daten gerendert (`data-emoji`/`data-own`-Attribute + Event-Delegation, kein `\'`-Escaping-Problem mehr)

## [1.1.5] - 2026-05-17

### Behoben
- HA-Notifications feuerten beim Reload-Button für alle alten Nachrichten — `fetchMessages` löscht `seenMsgIds` und re-verarbeitet den ganzen Chat als "neu"; HA-Notifications werden jetzt ausschließlich bei echten Echtzeit-Nachrichten gesendet (`source = 'NewMessage'`), nie beim API-Nachladen

## [1.1.4] - 2026-05-17

### Geändert
- Debug-Logging erweitert — jedes `processMessage` zeigt jetzt `[source]` (NewMessage / fetchMessages), `class`, `action`, Reaktionsanzahl; HA-Notification-Check loggt `msgId`, `isBot`, `skipBot` und Inhalt; hilft die genaue Quelle unerwünschter Notifications zu identifizieren

## [1.1.3] - 2026-05-17

### Neu
- Nachrichten-Reaktionen — 😊-Button erscheint beim Hovern; Picker mit 👍 👎 ❤️ 🔥 😂 😮 😢 🙏; Badge unter der Blase zeigt Emoji + Anzahl; eigene Reaktion (blau umrandet) beim Klicken entfernen; Echtzeit-Updates via `UpdateMessageReactions`

## [1.1.2] - 2026-05-17

### Behoben
- Refresh-Button lud keine Nachrichten nach — `seenMsgIds` enthielt noch alle IDs; werden jetzt vor dem Cache-Reset entfernt

## [1.1.1] - 2026-05-17

### Neu
- Refresh-Button (↺) in der Topbar — lädt den aktuellen Chat neu von Telegram (löscht den In-Memory-Cache); nützlich wenn ein Bot eine Nachricht extern gelöscht hat; dreht sich während des Ladens

## [1.1.0] - 2026-05-17

### Behoben
- Löschen-Button (✕) erschien rechts neben empfangenen Blasen — `order: -1` jetzt auch für `.bubble-row.in .del-btn`; Hover-Layout ist jetzt `[✕][Blase]` für alle Nachrichten

### Geändert
- Bilder in der Chat-Ansicht größer — Thumbnail-Maxgröße von 240×300 auf 320×400 px erhöht
- Lightbox beim Klick auf ein Foto — schwarzer halbtransparenter Overlay, Bild zentriert in voller Fenstergröße (bis 92vw/92vh); Klick auf den Hintergrund oder Escape schließt die Lightbox

## [1.0.35] - 2026-05-17

### Neu
- Speicheranzeige in der Topbar — zeigt den belegten Speicher des Add-on-Datenverzeichnisses in MB (💾 12.3 MB); aktualisiert sich automatisch alle 60 Sekunden

## [1.0.34] - 2026-05-17

### Geändert
- Abmelden-Button als ⏻-Symbol (wie WhatsApp)

## [1.0.33] - 2026-05-17

### Neu
- Scroll-Buttons ↑ ↓ in der Topbar — springt direkt an den Anfang oder das Ende der Nachrichten

## [1.0.32] - 2026-05-16

### Geändert
- Foto-Toggle: Button zeigt jetzt „Fotos AN" (gedrückt = heller Hintergrund) bzw. „Fotos AUS" (gedimmt); Standard ist AN

## [1.0.31] - 2026-05-16

### Neu
- „📷 Fotos"-Schalter im Topbar neben dem Telegram-Schriftzug — blendet alle Fotos aus und zeigt stattdessen `📷 Foto` als Text; Zustand wird im Browser gespeichert (localStorage); erscheint nur wenn `download_media` aktiviert ist

## [1.0.30] - 2026-05-16

### Behoben
- Log-Format: Uhrzeit stand am Ende statt nach `[LEVEL]` — Regex trennt jetzt `[LEVEL]` vom Rest und fügt `[HH:MM:SS]` korrekt dazwischen ein

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
