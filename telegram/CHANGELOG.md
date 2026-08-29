# Changelog

## [1.7.7] - 2026-08-29
- **REST-API auf eigenem Port mit Token-Pflicht.** Neue Optionen `api_enabled` (Standard: aus) und `api_token` starten einen zweiten Listener auf **17788**, der ausschliesslich `/api/*` bedient und jeden Aufruf ohne `Authorization: Bearer <Token>` mit `401` abweist
- **Breaking Change: Port 17778 wird nicht mehr veroeffentlicht.** Er gab Weboberflaeche und REST-API ohne jede Anmeldung an das ganze LAN heraus — wer die Adresse kannte, konnte mitlesen und senden. Beides liegt auf demselben Express-Server, und der UI-Port kann keinen Token verlangen: die Oberflaeche ruft ihre eigenen `/api/`-Routen aus dem Browser auf. Sein Schutz kann deshalb nur sein, ihn nicht freizugeben
- **Unveraendert erreichbar:** die Oberflaeche ueber das HA-Panel (Ingress, Anmeldung durch Home Assistant) und ueber das MessengerPortal, das das Add-on seit **1.2.20** ueber seinen Container-Namen anspricht und den Host-Port nicht mehr braucht
- **Was bricht:** alles, was `http://<HA-IP>:17778/api/...` oder `http://localhost:17778/api/...` aufruft. Umstellen auf **17788** mit Token; Beispiele stehen in DOCS.md. Wer 17778 unbedingt braucht, kann das Mapping unter *Netzwerk* von Hand wieder eintragen — dann aber wieder ohne Passwort fuer jedes Geraet im Netz
- Die Weboberflaeche wird ueber 17788 auch mit gueltigem Token **nicht** ausgeliefert (`404`) — sonst waere der Port ein zweiter, gleichwertiger Weg auf alles. Ist `api_enabled` an, aber kein Token gesetzt, startet der Port gar nicht
- Der Vergleich laeuft ueber `crypto.timingSafeEqual` statt `===`, damit die Laufzeit den Token nicht verraet. Abgewiesene Zugriffe landen mit Pfad und IP als WARN in der Konsole des Add-ons
- Der Watchdog laeuft jetzt ueber `tcp://[HOST]:17778` statt `tcp://[HOST]:[PORT:17778]`. Die alte Form loeste den **Host**-Port auf und waere ohne Mapping ins Leere gelaufen — das Add-on haette sich selbst als tot gemeldet und im Kreis neu gestartet
- `test-api.ps1` spricht jetzt 17788 an und schickt den Token mit. Er steht **nicht** im Skript — es liest `$env:TELEGRAM_API_TOKEN` oder fragt beim Start danach; Host und Port lassen sich ueber `TELEGRAM_HOST` und `TELEGRAM_API_PORT` uebersteuern
- Gleiches Muster wie im WhatsApp-Add-on ab 1.8.31

## [1.7.6] - 2026-08-28
- Fix: **In der Konsole fehlte bei vielen Zeilen die Uhrzeit.** Die still protokollierten Debug-Zeilen (`API GET …`) trugen keinen Zeitstempel, die echten Konsolenzeilen schon — jetzt haben alle einen, und zwar in Ortszeit statt UTC
- Feature: **Filter in der Konsole.** Vier Schalter fuer ERROR, WARN, INFO und DEBUG blenden Ebenen aus, ein Textfeld filtert zusaetzlich nach Inhalt. Der Zaehler rechts zeigt „sichtbar/gesamt". Ein Filterwechsel wirkt auch auf bereits eingetroffene Zeilen, weil die letzten 1500 Meldungen im Browser vorgehalten werden. Die Auswahl der Ebenen bleibt ueber einen Seitenwechsel hinweg erhalten
- Gleiche Funktion wie im WhatsApp-Add-on ab 1.8.0

## [1.7.5] - 2026-08-25
- Fix: **Netzwerk-Aussetzer heilen sich jetzt von selbst.** Fiel die Verbindung zu Telegram mit einem Netzwerkfehler aus (z. B. `connect ENETUNREACH 149.154.167.50:443`), blieb das Add-on dauerhaft im Status `error` stehen und wartete auf einen manuellen Klick auf „Erneut verbinden". Ein neuer Auto-Retry-Timer prüft alle 10 Sekunden, ob der letzte Fehler ein Netzwerkfehler war (ENETUNREACH, EHOSTUNREACH, ECONNRESET, ETIMEDOUT, EAI_AGAIN, Timeout u. a.), und startet dann selbstständig einen neuen Verbindungsversuch mit exponentiellem Backoff (15 s, 30 s, 60 s … max. 5 Minuten). Nach erfolgreicher Verbindung wird der Backoff zurückgesetzt. Auth- und Konfigurationsfehler (falscher Code, fehlende `api_id`) werden bewusst **nicht** wiederholt, ebenso wenig wird erneut versucht, solange auf Code oder 2FA-Passwort gewartet wird

## [1.7.4] - 2026-08-13
- Neu: **Gesendete Nachrichten erscheinen sofort in der Chat-Ansicht** (optimistisches Rendern). Bisher wurde die Bubble erst gezeichnet, nachdem `client.sendMessage()` samt Telegram-Roundtrip fertig war und `loadMessages()` neu geladen hatte — je nach Verbindung mehrere Sekunden Verzögerung. Jetzt legt `sendMsg()` die Nachricht direkt in eine chatbezogene Pending-Liste (`_pendingSend`), die `renderMessages()` ausgegraut (55 % Deckkraft, 🕓 statt Häkchen, keine Antworten-/Weiterleiten-Buttons) ans Ende der Liste hängt; das Eingabefeld wird sofort geleert. Nach der Server-Antwort wird der Eintrag entfernt und die echte Nachricht per `loadMessages(chatId, true)` nachgeladen. Schlägt der Versand fehl, verschwindet der Platzhalter und der Text landet wieder im Eingabefeld. Gilt für normale Nachrichten und Antworten (inkl. Zitat-Block); Medienversand unverändert

## [1.7.3] - 2026-07-31
- map: `addon_config` → `app_config` (Home-Assistant-Supervisor hat `addon_config` seit 2026.07 als Legacy-Name markiert, neuer Name ist `app_config`).

## [1.7.2] - 2026-07-29
- Aufräumen: Verbliebene "GramJS"-Log-Labels (Keep-alive, downloadMedia, getMessages, msg-Debug) auf "teleproto" korrigiert — rein kosmetisch, keine Funktionsänderung

## [1.7.1] - 2026-07-29
- Fix: Add-on crashte beim Start mit `Cannot find module './node_modules/telegram/package.json'` — die 1.7.0-Migration hatte einen direkten Pfad-Require für die Versionsanzeige übersehen (nicht über das übliche `require('telegram...')`-Muster gefunden). Jetzt auf `teleproto` korrigiert

## [1.7.0] - 2026-07-29
- Migration: GramJS (npm-Paket `telegram`) ist EOL — Wechsel auf den aktiv gepflegten Fork **teleproto** (`sanyok12345/teleproto`). Bestehende Sessions bleiben gültig (Legacy-Sessionformat wird automatisch erkannt), keine Neuanmeldung nötig. Nur Paketname/Imports geändert, keine Verhaltensänderung

## [1.6.23] - 2026-07-09
- Fix: Add-on beendete sich bei jedem Stop/Update mit **Exit 137** (Hard-Kill nach Timeout) — der Node-Prozess lief ohne eigenes Init-System als PID 1 im Container, wodurch der Kernel das SIGTERM des Supervisors stillschweigend ignorierte. Jetzt `init: true` in `config.yaml` sowie ein expliziter `SIGTERM`/`SIGINT`-Handler in `server.js`, der ausstehende Speichervorgänge (Chats/Nachrichten) sofort flusht, die Telegram-Verbindung sauber trennt (`client.disconnect()`) und sich danach mit Exit 0 beendet

## [1.6.22] - 2026-06-29
- Neu: **Emoji-Picker mit Kategorien wie auf dem Handy** — über 1000 Emojis in 8 Kategorie-Tabs (Smileys & Personen, Tiere & Natur, Essen & Trinken, Aktivitäten, Reisen & Orte, Objekte, Symbole, Flaggen), ein **Suchfeld** (deutsch/englisch, z.B. „herz" oder „laugh") und eine **„Zuletzt verwendet"**-Leiste, die die eigenen Emojis merkt (im Browser gespeichert). Ersetzt die bisherige flache Liste mit ~170 Emojis

## [1.6.21] - 2026-06-26
- Suche: Die Nachrichtensuche durchsucht jetzt den **gesamten gecachten Verlauf** serverseitig (neuer Endpoint `/api/search`), nicht mehr nur die geladenen Bubbles — wichtig seit der Pagination. Ein Klick bzw. ▲▼ springt zum Treffer; liegt er außerhalb des aktuellen Fensters, wird automatisch ein Verlauf-Fenster um ihn geladen und hervorgehoben. Schließen der Suche kehrt zum Live-Modus zurück. Während der Verlauf-Ansicht pausiert der Live-Poll, damit das Fenster nicht überschrieben wird

## [1.6.20] - 2026-06-26
- Performance: Große Chats (tausende Nachrichten) öffnen jetzt sofort — der Server sendet initial nur die **neuesten 60** Nachrichten statt der kompletten Liste, das Frontend rendert also nicht mehr tausende Bubbles auf einmal (kein Spinner/Ruckeln mehr). Ältere Nachrichten werden beim **Hochscrollen** automatisch aus dem Cache nachgeladen und vorne angefügt, ohne die Scrollposition zu verlieren. Neue/geänderte Nachrichten im sichtbaren Bereich werden weiterhin live aktualisiert, bereits nachgeladene ältere bleiben erhalten

## [1.6.19] - 2026-06-26
- UX: Beim Chat-Wechsel wird das Chatfenster jetzt sofort geleert und die gecachten Nachrichten praktisch ohne Verzögerung angezeigt — vorher blieb der vorherige Chat stehen, bis der (bei Erstöffnung mehrere Sekunden dauernde) Live-Telegram-Fetch zurückkam. Ein Lade-Spinner erscheint nur noch, wenn wirklich nichts gecacht ist und der Server live von Telegram holt (>200 ms)

## [1.6.18] - 2026-06-26
- Fix: Zwei `express-rate-limit`-ValidationErrors im Log behoben — der globale Limiter für schreibende Requests wird jetzt **einmal beim Start** erzeugt statt pro Request (`ERR_ERL_CREATED_IN_REQUEST_HANDLER`), und `trust proxy` ist auf `1` gesetzt, da das Add-on hinter dem HA-Ingress-Reverse-Proxy läuft (`ERR_ERL_UNEXPECTED_X_FORWARDED_FOR`)

## [1.6.17] - 2026-06-26
- Performance: Polling pausiert, wenn der Browser-Tab im Hintergrund ist (`document.hidden`) — Status (2 s) und Chat-Liste/Nachrichten (5 s) laufen nicht mehr 24/7 weiter; beim Zurückkehren wird sofort aktualisiert (`visibilitychange` zieht Status + Chats nach)
- Performance: `/api/storage` cacht das Ergebnis 15 s — der rekursive Verzeichnis-Scan blockiert den Event-Loop nicht mehr
- Watchdog: Supervisor startet das Add-on bei nicht erreichbarem Port automatisch neu (`watchdog: tcp://[HOST]:[PORT:17778]`)
- Media-Responses mit `Cache-Control: immutable` (Dateiname ist über die stabile Message-ID eindeutig)

## [1.6.16] - 2026-06-23
- HA-Benachrichtigungen: kein manueller `ha_token` mehr nötig — das Add-on nutzt jetzt `homeassistant_api` und den automatisch vom Supervisor bereitgestellten Token (wie MyPage). Option `ha_token` entfernt, Aufrufe laufen über `http://supervisor/core/api`
- AppArmor-Profil hinzugefügt (`telegram_addon`)

## [1.6.15] - 2026-06-10
- UI: Foto-Bubble auf max-width 280px begrenzt, Bild füllt Bubble-Breite (width:100%) — einheitlich mit WhatsApp und Signal

## [1.6.14] - 2026-06-10
- Fix: Häkchen-Update jetzt In-Place (kein Re-Render) — nur ackKey im Fingerprint geändert → updateAckMarksInPlace() aktualisiert nur .bubble-time, Video/Audio-Wiedergabe wird nicht unterbrochen

## [1.6.13] - 2026-06-10
- Fix: Häkchen (✓ ✓✓) aktualisieren sich jetzt sofort — ACK-Summe im msgFingerprint; Re-Render wird ausgelöst sobald sich ein Lesestatus ändert

## [1.6.12] - 2026-06-10
- UI: Foto-Thumbnail auf max 200×200px verkleinert (war 320×400); einheitlich mit WhatsApp und Signal

## [1.6.11] - 2026-06-10
- fix: Export-HTML-Button nutzt jetzt Download-Pfeil-Icon wie WhatsApp (statt Datenbank-Icon)

## [1.6.10] - 2026-06-10
- fix: Storage-Anzeige nutzt jetzt SVG-Icon statt 💾-Emoji (wie WhatsApp)

---

## [1.6.9] - 2026-06-10
- fix: Chat-Header-Buttons (Suche, Export, Löschen) auf einheitlichen Stil angeglichen — gleiche Border, Farbe und Padding wie WhatsApp

---

## [1.6.8] - 2026-06-10
- UI: Alle Emoji-Icons (🎬 🗑️ ↺ ↑↓ 🌐 💾 ✕ 😊 📎 📄 ↪ ↩) durch konsistente SVG-Icons ersetzt
- Feature: Nachrichtensuche in Chats — Suchleiste im Chat-Header mit Vorwärts-/Rückwärts-Navigation und Highlight

---

## [1.6.7] - 2026-06-07

### Security
- Format-String: `chatId` aus `console.error` in `fetchMessages` entfernt (CodeQL: js/tainted-format-string #73)

---

## [1.6.6] - 2026-06-07

### Security
- Globaler Rate-Limiter (200 Req/min) für alle API-Endpunkte via `app.use()` (CodeQL: Missing rate limiting #83, #65)

---

## [1.6.5] - 2026-06-07

### Security
- `express-rate-limit` statt eigener Implementierung: CodeQL-erkannte Rate-Limiting-Lösung (#113, #114)

---

## [1.6.4] - 2026-06-07

### Security
- Rate Limiting für `/api/delete-video`, `/api/messages/:chatId/:msgId` (DELETE) und `/api/cleanup-media` eingebaut: verhindert Missbrauch destruktiver Endpunkte (CodeQL: Missing rate limiting)

---

## [1.6.3] - 2026-06-07

### Security
- Path-Traversal-Schwachstelle in `/api/media/:filename` behoben: `path.resolve()` + Boundary-Check (CodeQL: Uncontrolled data used in path expression)
- `path`-Modul importiert

---

## [1.6.2] - 2026-06-07

### Security
- `multer` von `^1.4.5-lts.1` auf `^2.1.1` aktualisiert — behebt Denial-of-Service-Schwachstelle durch unkontrollierte Rekursion beim Parsen von Feldnamen

---

## [1.6.1] - 2026-06-07
### Added
- Disconnect-Erkennung: `visibilitychange` (Tab/Laptop-Aufklappen), `online`/`offline`-Events, `navigator.onLine`-Check beim Start
- Offline-Banner: abdunkelndes Overlay mit animiertem 📡, i18n (DE/EN via LANG-Objekt + `data-i18n`) und „Neu laden"-Button

## [1.6.0] - 2026-06-06
### Added
- Sprachnachrichten: Download als .ogg, abspielbarer Audio-Player im Chat (erfordert `download_media: true`)
- Video-Support: Auto-Download bei Neueingängen, On-Demand per Klick auf 📹-Platzhalter, 🗑️-Button, Optionen `video_max_mb` + `media_max_mb`
- Album-Fotos (gleiche groupedId) als kompaktes Foto-Grid (140×140 px) in einer Bubble
- Profilbilder als echte Avatare (auch für Gruppen, Kanäle, Bots); Klick → Kontaktinfo-Modal mit Foto, Name, @username, Telefon, Bio
- Nachrichten weiterleiten (↪ Forward-Modal mit Suchfeld) und beantworten (↩ Zitat-Block in der Bubble)
- Multi-Select-Löschmodus: ✕-Button in der Toolbar, Batch-Löschen mit Bestätigungsdialog (DE/EN)
- Dark/Light-Mode-Toggle (☀️/🌙) im Header
- In-App Console: Doppelklick auf „Telegram" öffnet draggbares Floating-Window mit GramJS-Debug-Logs
- Speicher-Tooltip auf 💾: Medienordner-Größe, Limit und % bis Auto-Delete
### Improved
- HTML-Export vollständig lokalisiert (DE/EN); Videos und Sprachnachrichten als Platzhalter
- renderMessages nur bei geändertem Fingerprint → Video-Wiedergabe wird nicht mehr durch Poll unterbrochen

## [1.5.51] - 2026-06-06
- Neu: In-App Console (Doppelklick auf "Telegram") — draggbares Floating-Window mit GramJS-spezifischen Debug-Logs: alle API-Requests, processMessage, getMessages, downloadMedia (KB/ms), Keep-alive OK, stille Logs nur in Console (nicht im HA-Log)

## [1.5.50] - 2026-06-06
- Fix: type-Feld fehlte in lastReceivedMsg beim Startup-Init — video/voice/photo werden jetzt korrekt übergeben

## [1.5.49] - 2026-06-06
- Fix: Album-Reactions wurden von pollReactions gelöscht — data-albumids im DOM, updateReactionsInDOM mergt Reactions aller Album-Fotos

## [1.5.48] - 2026-06-06
- Fix: Reactions bei Album-Fotos fehlten — Reactions aller Album-Nachrichten werden jetzt zusammengeführt und unter dem Grid angezeigt

## [1.5.47] - 2026-06-06
- Fix: Forward sofort sichtbar (3. Versuch) — nach forwardMessages() direkt getMessages({limit:1}) aufrufen statt aus TypeUpdates zu extrahieren (GramJS verarbeitet Updates asynchron)

## [1.5.46] - 2026-06-06
- Fix: Weitergeleitete Nachricht sofort sichtbar (2. Versuch) — TypeUpdates korrekt ausgewertet (UpdateNewMessage.message extrahiert), processMessage() danach, Client loadMessages()

## [1.5.45] - 2026-06-06
- Neu: ☀️/🌙-Button neben "Telegram" zum Umschalten Dark/Light Mode; Auswahl per localStorage (tg_theme) gespeichert

## [1.5.44] - 2026-06-06
- Fix: Weitergeleitete Nachricht erscheint jetzt sofort — nach erfolgreichem Forward ?refresh=1 (frischer Telegram-Abruf) statt Cache

## [1.5.43] - 2026-06-06
- Fix: Weitergeleitete Nachricht erschien nicht sofort in der App — Server verarbeitet das Forward-Ergebnis via processMessage(), Client lädt den aktiven Chat neu

## [1.5.42] - 2026-06-06
- Fix: Gesendete Nachrichten nicht mehr rechts anliegend — Hover-Buttons bei out-Nachrichten per order:-1 links der Bubble platziert statt rechts

## [1.5.41] - 2026-06-06
- Fix: Bubble verschiebt sich beim Hover — Buttons nutzen jetzt opacity statt display:none, belegen immer Platz
- Neu: Album-Fotos (gleiche groupedId) werden als Foto-Grid (140×140 px) in einer Bubble dargestellt statt gestapelt

## [1.5.40] - 2026-06-06
- Neu: Multi-Select-Löschmodus — ✕-Button in der Toolbar, Nachrichten anklicken zum Markieren (rote Hervorhebung), 🗑️-Button löscht alle markierten mit Bestätigungsdialog (DE/EN); Escape oder Chat-Wechsel bricht Modus ab

## [1.5.39] - 2026-06-06
- Neu: HTML-Export vollständig lokalisiert (DE/EN) — Datum, Uhrzeit, Labels und Platzhalter folgen der gewählten UI-Sprache

## [1.5.38] - 2026-06-06
- Fix: HTML-Export brach bei Videos/Sprachnachrichten ab — base64-Einbettung entfernt, werden jetzt als Platzhalter (📹/🎵) angezeigt

## [1.5.37] - 2026-06-06
- Fix: Keine Bubble-Umrandung bei Audionachrichten — Audio-Player steht frei ohne Hintergrund

## [1.5.36] - 2026-06-06
- Fix: Audio-Player kollabierte auf minimale Breite — feste Breite 260px mit max-width als Grenze statt width:100%

## [1.5.35] - 2026-06-06
- Fix: Audio-Player ragte über Bubble-Rahmen hinaus — min-width entfernt, player passt sich per width:100% der Bubble an

## [1.5.34] - 2026-06-06
- Fix: Speicheranzeige aktualisiert sich jetzt auch nach Video-Löschen sofort

## [1.5.33] - 2026-06-06
- Fix: Unhandled rejection "not found" — promise.finally() erzeugte zweite rejecting Promise ohne catch; ersetzt durch .then(del, del)

## [1.5.32] - 2026-06-06
- feat: media_max_mb/video_max_mb im Startup-Log

## [1.5.31] - 2026-06-06
- Fix: Reload-Button ersetzte heruntergeladene Videos durch Placeholder — mediaFile und videoSize werden beim Refresh jetzt wie Reactions gespeichert und wiederhergestellt

## [1.5.30] - 2026-06-06
- Fix: Chat-Wechsel zeigte leeres Fenster — openChat() löscht Fingerprint damit loadMessages() immer neu rendert

## [1.5.29] - 2026-06-06
- Speicheranzeige aktualisiert sich nach Video-Download

## [1.5.28] - 2026-06-06
- Fix: videoTooBig-Text zeigte hardcodiert "max 10 MB" statt konfiguriertem video_max_mb-Wert

## [1.5.27] - 2026-06-05
- Fix: Video-Wiedergabe wurde alle 2s durch pollMessages-Re-Render unterbrochen — renderMessages nur noch bei geändertem Nachrichten-Fingerprint (Anzahl + IDs + Video-mediaFile)

## [1.5.26] - 2026-06-05
- Neu: video_max_mb Option (Standard 50 MB) — ersetzt hardcoded 10 MB Limit für Video-Downloads

## [1.5.25] - 2026-06-05
- Fix: MEDIA_MAX_MB fehlte in run.sh → Limit zeigte immer 500 MB statt konfiguriertem Wert

## [1.5.24] - 2026-06-05
- Video-Placeholder: "⬇ Video herunterladen · X.X MB" statt doppeltem "Video"; Body nur anzeigen wenn Video geladen; DE+EN

## [1.5.23] - 2026-06-05
- Kritischer Fix: messages.GetHistory FloodWait — /api/messages rief bei jedem pollMessages (2s) fetchMessages() auf wenn Chat < FETCH_LIMIT hatte; jetzt nur noch beim ersten Öffnen (wenn Chat nie geladen)

## [1.5.22] - 2026-06-05
- Fix: Video-Download > 10 MB trennt Verbindung — Limit auf 10 MB reduziert, Timeout 25s, Größe im Placeholder "(X.X MB)", zu-groß-Videos grau ohne Klick

## [1.5.21] - 2026-06-05
- Neu: 🗑️-Button neben dem Video-Player — löscht Datei von Disk, zeigt 📹 Video Placeholder wieder an

## [1.5.20] - 2026-06-05
- Kritisch: Videos werden nur noch bei echten Neueingängen auto-geladen (source=NewMessage), nie beim Reload — verhindert FloodWait-Kaskadenausfall
- Neu: Klick auf 📹 Video Placeholder → on-demand Download mit ⏳ Sanduhr (/api/fetch-video)
- Entfernt: video_max_per_chat Option (mit on-demand unnötig)
- Avatar-Concurrency auf 1 reduziert (weniger upload.GetFile-Druck)

## [1.5.19] - 2026-06-05
- Fix: Video-Limit prüft VOR dem Download ob Platz ist (nicht danach) — verhindert nutzlose Downloads die sofort wieder gelöscht werden
- Neu: DE+EN Übersetzungen für media_max_mb und video_max_per_chat in config.yaml

## [1.5.18] - 2026-06-05
- Neu: video_max_per_chat Option (Standard 20) — älteste Videos pro Chat werden automatisch gelöscht wenn das Limit überschritten wird

## [1.5.17] - 2026-06-05
- 📷→🎬 Button umbenannt: "Fotos AN/AUS" → "Medien AN/AUS"; blendet jetzt auch Videos aus (body.hide-photos video)

## [1.5.16] - 2026-06-05
- Fix: FloodWait beim Video-Download — downloadMedia workers:1 verhindert parallele upload.GetFile-Requests

## [1.5.15] - 2026-06-05
- Speicher-Tooltip: Mouseover auf 💾 zeigt Medienordner-Größe, Limit und % bis Auto-Delete (DE+EN)

## [1.5.14] - 2026-06-05
- Neu: media_max_mb Config (Standard 500 MB) — bei Überschreitung werden automatisch die ältesten Mediendateien gelöscht (LRU)

## [1.5.13] - 2026-06-05
- Neu: Videos anzeigen — Download (max 50 MB, mp4/webm), <video controls> im Chat und im HTML-Export

## [1.5.12] - 2026-06-05
- Fix: Kontaktinfo-Modal und Profilbilder jetzt auch für Gruppen, Kanäle und Bots

## [1.5.11] - 2026-06-05
- Neu: Profilbilder als Avatare (downloadProfilePhoto, lazy, 2 parallel); Klick auf Header-Avatar → Kontaktinfo-Modal mit Foto, Name, @username, Telefon, Bio

## [1.5.10] - 2026-06-05
- Neu: Nachrichten weiterleiten (↪, via forwardMessages) und beantworten (↩, via replyTo); Hover-Buttons, Forward-Modal mit Suchfeld, Zitat-Block in der Bubble

## [1.5.9] - 2026-06-05
- Neu: Sprachnachrichten (voice) werden empfangen, als .ogg gespeichert und als abspielbarer Audio-Player angezeigt (erfordert download_media: true); Erkennung via DocumentAttributeAudio.voice

## [1.5.8] - 2026-06-05
- Neu: `type`-Feld in `GET /api/last-received` und Webhook-Payload (text/photo/document/voice)

## [1.5.7] - 2026-06-05
- Neu: Bilder aus der Zwischenablage direkt ins Chat-Eingabefeld einfügen (Strg+V / Cmd+V)

## [1.5.6] - 2026-06-05
- feat: Chat-ID per Mouse-Over auf dem eigenen Namen im Header anzeigen

## [1.5.5] - 2026-06-04
- fix: Datum in Log-Zeitstempel ergänzt — war nur Uhrzeit, jetzt vollständig

## [1.5.4] - 2026-06-04
- Log-Ausgaben mit Datum und Uhrzeit: `[INFO] [YYYY-MM-DD HH:MM:SS] Nachricht`

## [1.5.3] - 2026-06-03
- Fix: python3/make/g++ für GramJS-Compilation hinzugefügt, nach npm install wieder entfernt

## [1.5.2] - 2026-06-03
- Build: Image wird jetzt via GitHub Actions auf GHCR gebaut (ghcr.io/luckytriple7/telegram)
- Build: Basis-Image auf node:lts-alpine umgestellt, run.sh auf #!/bin/sh

## [1.5.1] - 2026-06-03

### Fixed
- Verbindungsabbrüche wurden nicht erkannt: TCP-Verbindung zu Telegram kann nach Netzwerk-Flaps oder NAT-Timeouts still abbrechen, `status` blieb 'connected' → Chats luden nicht mehr. Fix: Keep-Alive-Ping (`getMe()`) alle 30s mit 10s Timeout — schlägt er fehl, wird automatisch reconnectet
- `loadDialogs()` hatte keinen Timeout — konnte hängen und blockierte Node.js-Event-Loop. Fix: 15s Timeout via `Promise.race`

## [1.5.0] - 2026-05-30
- Docs: ha_token-Admin-Anforderung dokumentiert — kein Admin-Benutzer erforderlich

## [1.2.10] - 2026-05-30
- Fix: Zurück-Pfeil linksbündig, restliche Topbar-Elemente rechtsbündig (margin-right: auto)

## [1.2.9] - 2026-05-30
- UX: Mobile Navigation — App-Name im Topbar ausgeblendet wenn Chat offen, stattdessen eleganter Zurück-Pfeil (SVG Chevron); Avatar-Klick-Navigation entfernt

## [1.2.8] - 2026-05-30
- Neu: Sicherheitsabfrage beim Abmelden — Popup mit Ja/Nein-Buttons (DE/EN)

## [1.2.7] - 2026-05-30
- Fix: Chat-Header Mobile — Zurück-Pfeil ausgeblendet, Avatar-Klick navigiert zurück zur Chat-Liste
- Fix: Stats-Zeile bricht auf Mobile um statt abgeschnitten zu werden

## [1.2.6] - 2026-05-30
- Fix: visualViewport-JS-Fix + viewport-fit=cover — verhindert dass Android-Navigationsleiste die Eingabeleiste im Vollbildmodus verdeckt

## [1.2.5] - 2026-05-29
- Fix: Benutzername im Topbar auf Mobile ausgeblendet

## [1.2.4] - 2026-05-29
- Fix: Logout-Button ersetzt ⏻ Unicode durch SVG-Icon — rendert auf allen Mobile-Browsern korrekt (identisch mit CardBoard-Fix)

## [1.2.3] - 2026-05-29
- Neu: Sprache wird automatisch anhand der Browsersprache erkannt (DE/EN) — kein manuelles Umschalten mehr nötig beim ersten Start
- Fix: Sprach-Umschalter (🌐) in der mobilen Ansicht ausgeblendet, bleibt in der Desktop-Ansicht sichtbar
- Fix: Logout-Button auf Mobile korrekt dargestellt (flex-shrink verhindert Quetschen, kleinerer Gap im Topbar)

## [1.2.2] - 2026-05-29
- Fix: `GET /api/last-received` ignoriert jetzt Bot-Nachrichten wenn `ha_notifications_skip_bots` aktiv ist — konsistentes Verhalten mit HA-Benachrichtigungen

## [1.2.1] - 2026-05-29
- Neu: REST-Endpoint `GET /api/last-received` — liefert Zeitpunkt, Chat, Kontakt und Vorschau der zuletzt empfangenen Nachricht; optional mit `?chat=<chatId>` für einen bestimmten Chat; wird beim Start aus den gespeicherten Nachrichten initialisiert
- Doku: HA-Sensor-Beispiel für `configuration.yaml` ergänzt

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
