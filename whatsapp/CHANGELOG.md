# Changelog

## [1.7.28] - 2026-07-03
- Fix: Eigene Nachrichten erschienen gelegentlich **doppelt im Chat** (Anzeige-Bug, nicht doppelt versendet) — `sendMsg()` löst nach dem Senden sofort `pollMessages()` aus, das mit dem parallel laufenden 2s-Intervall kollidieren konnte; beide riefen `renderMessages()` mit derselben Nachricht auf, bevor der Zeitstempel-Cursor aktualisiert war. Chat wechseln entfernte die Dopplung, weil dabei neu vom Server geladen wurde. `renderMessages()` prüft jetzt vor jeder neuen Bubble, ob die Nachrichten-ID schon im DOM steht

## [1.7.27] - 2026-06-29
- Fix: Die **Kategorie-Tabs** im neuen Emoji-Picker erschienen als unschöne **grüne Kreise** — die generische Senden-Button-Regel (`#send-bar button`, grün/rund) überschrieb die Tab-Buttons. Die Tabs sind jetzt korrekt unter `#emoji-tabs` gestylt (transparent, dezenter aktiver/Hover-Hintergrund wie bei Telegram)

## [1.7.26] - 2026-06-29
- Neu: **Emoji-Picker mit Kategorien wie auf dem Handy** — über 1000 Emojis in 8 Kategorie-Tabs (Smileys & Personen, Tiere & Natur, Essen & Trinken, Aktivitäten, Reisen & Orte, Objekte, Symbole, Flaggen), ein **Suchfeld** (deutsch/englisch, z.B. „herz" oder „laugh") und eine **„Zuletzt verwendet"**-Leiste, die die eigenen Emojis merkt (im Browser gespeichert). Ersetzt die bisherige flache Liste mit ~170 Emojis

## [1.7.25] - 2026-06-29
- Fix: Nachrichten wurden gelegentlich **doppelt versendet** — bei schnellem Doppel-Tap auf den Senden-Button oder doppeltem Enter lief `sendMsg()` zweimal los und schickte die Nachricht zweimal echt raus. Ein In-Flight-Guard verhindert jetzt, dass ein zweiter Versand startet, solange der erste noch läuft (gilt auch für Datei-/Medienversand)

## [1.7.24] - 2026-06-27
- Erwähnungen werden jetzt **als Name angezeigt** statt als Nummer — `@<nummer>` wird beim Rendern zu `@Name` aufgelöst und blau hervorgehoben, sowohl bei **eigenen gesendeten** als auch bei **eingehenden** Nachrichten. Gruppenmitglieder werden beim Öffnen des Chats vorgeladen; ist für eine Nummer kein Name bekannt, wird sie als `@+<nummer>` formatiert
- Erwähnungen funktionieren jetzt auch beim **Antworten** (Reply), nicht nur beim normalen Senden
- Namensauflösung der Gruppenmitglieder verbessert (zusätzlich `verifiedName`/`shortName`)

## [1.7.23] - 2026-06-27
- Neu: **@-Erwähnungen in Gruppen** — tippst du `@` in einem Gruppenchat, öffnet sich eine Mitglieder-Auswahl (Filtern beim Weitertippen, ▲▼/Enter/Tab zur Auswahl). Die gesendete Nachricht enthält eine echte Erwähnung, der Erwähnte wird benachrichtigt wie bei der App. Neuer Endpoint `/api/participants/:chatId`; `/api/send` akzeptiert jetzt `mentions`

## [1.7.22] - 2026-06-26
- Fix: Zwei `express-rate-limit`-ValidationErrors im Log behoben — der globale Limiter für schreibende Requests wird jetzt **einmal beim Start** erzeugt statt pro Request (`ERR_ERL_CREATED_IN_REQUEST_HANDLER`), und `trust proxy` ist auf `1` gesetzt, da das Add-on hinter dem HA-Ingress-Reverse-Proxy läuft (`ERR_ERL_UNEXPECTED_X_FORWARDED_FOR`)

## [1.7.21] - 2026-06-26
- Fix: Die Kontaktliste links aktualisiert Vorschau und Sortierung jetzt sofort, wenn im offenen Chat eine Nachricht ankommt oder gesendet wird — vorher hinkte sie bis zu 10 s hinterher (Chat-View pollt alle 2 s, Liste nur alle 10 s). `loadMessages` stößt bei neuen Nachrichten direkt ein `pollChats()` an

## [1.7.20] - 2026-06-26
- Performance: Polling pausiert jetzt, wenn der Browser-Tab im Hintergrund ist (`document.hidden`) — Nachrichten (2 s), Reaktionen (5 s), Chats (10 s) und Status (5 s) laufen nicht mehr 24/7 weiter; beim Zurückkehren wird sofort aktualisiert (`visibilitychange`)
- Performance: `/api/stats` wird nur noch abgefragt, wenn tatsächlich neue Nachrichten ankamen (vorher bei jedem Message-Poll alle 2 s)
- Performance: `/api/storage` cacht das Ergebnis 15 s — der rekursive Verzeichnis-Scan blockiert den Event-Loop nicht mehr bei häufigen Aufrufen
- Fix: `media_max_mb`-Limit greift jetzt auch beim automatischen Foto-/Medien-Download (gedrosselt alle 30 s), nicht mehr nur bei Video-Downloads
- Watchdog: Supervisor startet das Add-on bei nicht erreichbarem Port automatisch neu (`watchdog: tcp://[HOST]:[PORT:17776]`)
- Media-Responses mit `Cache-Control: immutable` (Dateiname ist über die stabile Message-ID eindeutig)

## [1.7.19] - 2026-06-26
- Fix: Weitergeleitete Bilder erscheinen jetzt zuverlässig als Bild statt „Foto"-Platzhalter. Ursache: das `message`-Objekt direkt nach dem Weiterleiten ist „stale" und liefert dauerhaft keine Mediendaten (erst nach Neustart sichtbar). Jetzt wird das Medium im Hintergrund über bis zu ~45 s mit einem **frisch via `getMessageById` geholten** Objekt nachgeladen; die Bubble tauscht den Platzhalter ohne Neustart in-place gegen das Bild (`mediaUpdatedAt` im `since`-Filter). Gilt für gesendete (weitergeleitete) und empfangene Fotos; nur bei `download_media: true`

## [1.7.18] - 2026-06-26
- Fix: erster Versuch, weitergeleitete Bilder statt „Foto"-Platzhalter zu laden (Retry mit demselben Objekt — wirkungslos, ersetzt durch 1.7.19)

## [1.7.17] - 2026-06-23
- HA-Benachrichtigungen: kein manueller `ha_token` mehr nötig — das Add-on nutzt jetzt `homeassistant_api` und den automatisch vom Supervisor bereitgestellten Token (wie MyPage). Option `ha_token` entfernt, Aufrufe laufen über `http://supervisor/core/api`
- AppArmor-Profil hinzugefügt (`whatsapp_addon`)

## [1.7.16] - 2026-06-10
- UI: Foto-Bubble auf max-width 280px begrenzt, Bild füllt Bubble-Breite (width:100%) — Caption und Bild haben immer dieselbe Breite, max-height 360px verhindert sehr hohe Bilder

## [1.7.15] - 2026-06-10
- Fix: Häkchen (✓ ✓✓) aktualisieren sich jetzt sofort — ackUpdatedAt-Timestamp wird im message_ack-Event gesetzt, im since-Filter berücksichtigt und das .time-Element in-place im DOM aktualisiert

## [1.7.14] - 2026-06-10
- UI: Foto-Thumbnail im Chat auf max 200×200px verkleinert (war 320×400 + width:100%); Klick öffnet weiterhin Vollbild-Lightbox

## [1.7.13] - 2026-06-10
- Fix: Selbst gesendete Videos erscheinen jetzt in Chatliste und Chat — bisher wurden sie im `message_create`-Handler übersprungen; Platzhalter mit Download-on-Demand wie bei empfangenen Videos

## [1.7.12] - 2026-06-10
- UI: Alle Emoji-Icons (🎬 🗑️ 💾 ↑↓ 🌐 🚮 😊 📎 📍 📄) durch konsistente SVG-Icons ersetzt — Topbar, Chat-Header und Sendeleiste einheitlich professionell

## [1.7.11] - 2026-06-08
- Fix: Such-Button als SVG-Icon (statt Emoji), passend zu den anderen Header-Buttons; grüne Hervorhebung wenn aktiv

## [1.7.10] - 2026-06-08
- Neu: 🔍 Nachrichtensuche im Chat — Button im Header öffnet Suchleiste mit Live-Highlighting und ▲▼-Navigation zwischen Treffern
- UX: Chat-Header-Buttons und Send-Bar auf Mobile kleiner und kompakter

## [1.7.9] - 2026-06-07

### Security
- Globaler Rate-Limiter (200 Req/min) für alle API-Endpunkte via `app.use()` (CodeQL: Missing rate limiting #487–#490)

---

## [1.7.8] - 2026-06-07

### Security
- `express-rate-limit` statt eigener Implementierung: CodeQL-erkannte Rate-Limiting-Lösung (#115)

---

## [1.7.7] - 2026-06-07

### Security
- Rate Limiting für `/api/delete-video` eingebaut: max. 30 Anfragen/Minute pro IP — behebt CodeQL-Alert "Missing rate limiting" (#91)

---

## [1.7.6] - 2026-06-07

### Security
- Path-Traversal-Schwachstelle in Write-Endpunkten behoben: `downloadWAMedia` und Send-Media-Upload verwenden jetzt `path.resolve()` + Boundary-Check um Path-Injection bei `writeFileSync` zu verhindern (CodeQL: Uncontrolled data used in path expression)

---

## [1.7.5] - 2026-06-07

### Security
- Path-Traversal-Schwachstelle in `/api/media/:filename` behoben: `path.resolve()` + Boundary-Check stellt sicher dass der aufgelöste Pfad innerhalb von `MEDIA_DIR` bleibt (CodeQL: Uncontrolled data used in path expression)

---

## [1.7.4] - 2026-06-07

### Security
- `multer` von `^1.4.5-lts.1` auf `^2.1.1` aktualisiert — behebt Denial-of-Service-Schwachstelle durch unkontrollierte Rekursion beim Parsen von Feldnamen (Dependabot Alert #31)

---

## [1.7.3] - 2026-06-07
### Fixed
- Nach Page-Reload im Offline-Zustand (z.B. Browser-Cache via Service Worker) erschien der Banner erst nach 15 Sek.: `navigator.onLine`-Check beim Start zeigt Banner sofort

## [1.7.2] - 2026-06-07
### Fixed
- Offline-Banner verschwand fälschlicherweise trotz WLAN-Aus (gecachte Fetch-Antwort): `navigator.onLine`-Check vor `hideOfflineBanner()`
- Offline-Banner-Texte hardcoded Deutsch: `data-i18n`-Attribute + EN-Keys (`Connection lost / Reconnecting… / Reload`)

## [1.7.1] - 2026-06-07
### Added
- Disconnect-Erkennung: `visibilitychange`-Event aktualisiert Tab sofort beim Aufklappen des Laptops / Tab-Wechsel
- `online`/`offline`-Events: sofortiges Polling bei Netzwerk-Reconnect, sofortiger Banner bei Netzwerk-Verlust
- Offline-Banner: abdunkelndes Overlay mit animiertem 📡, „Verbindung unterbrochen"-Text und „Neu laden"-Button (erscheint nach 3 aufeinanderfolgenden fehlgeschlagenen Status-Polls)
### Fixed
- Banner verschwand fälschlicherweise bei gecachter Fetch-Antwort trotz aktivem Offline-Status: `navigator.onLine`-Check vor `hideOfflineBanner()` verhindert das

## [1.7.0] - 2026-06-06
### Added
- Standort empfangen (📍 Google-Maps-Link) und senden (📍-Button mit GPS-Abfrage oder manueller Lat/Lng/Name-Eingabe)
- Video-Support: Auto-Download bis video_max_mb (Standard 50 MB), On-Demand-Download per Klick auf Platzhalter, 🗑️-Button löscht Datei; neue Option `video_max_mb`
- Profilbilder als echte Avatare (lazy-load, 1h-Cache); Klick → Kontaktinfo-Modal mit Foto, Name, Nummer, About
- Multi-Select-Löschmodus: ✕-Button in der Toolbar, Nachrichten markieren, Batch-Löschen mit Bestätigungsdialog
- Dark/Light-Mode-Toggle (☀️/🌙) im Header, wird in localStorage gespeichert
- In-App Console: Doppelklick auf „WhatsApp" öffnet draggbares Floating-Window mit farbkodierten Logs (DEBUG/INFO/WARN/ERROR); stille Debug-Logs für API-Requests, Medien-Downloads und Events
- Option `media_max_mb` (Standard 500 MB): älteste Mediendateien werden automatisch gelöscht bei Überschreitung; Speicher-Tooltip auf 💾 zeigt Limit und Auslastung
### Improved
- HTML-Export vollständig lokalisiert (DE/EN); Sprachnachrichten als 🎵-Platzhalter
- Sprachnachrichten zuverlässig: MIME-Type-Fix (ogg), Auto-Download beim Start, min-width für Audio-Player

## [1.6.48] - 2026-06-06
- Revert: Filter/Export-Versuche zurückgesetzt, Console auf stabilem v1.6.39-Stand

## [1.6.39] - 2026-06-06
- Fix: Console als frei draggbares Floating-Window (560×340px, resize:both) statt festem Bottom-Panel — blockiert Sendeleiste nicht mehr; Header ziehen zum Verschieben

## [1.6.38] - 2026-06-06
- Fix: Console-Shortcut Ctrl+Shift+L → Doppelklick auf "WhatsApp" im Header

## [1.6.37] - 2026-06-06
- Neu: Stille Debug-Logs nur in der In-App Console (nicht im HA-Log): alle API-Requests mit Antwortzeit, eingehende Nachrichten mit Typ+Preview, message_ack (sent/received/read/played), call/group_join/group_leave/contact_changed Events, downloadWAMedia Start+Dauer+Größe, Keep-alive OK alle 10 Min

## [1.6.36] - 2026-06-06
- Neu: In-App Console — Ctrl+Shift+L öffnet/schließt Log-Panel (nur Desktop); zeigt alle server-seitigen Log-Meldungen farbkodiert (INFO grün / WARN gelb / ERROR rot / DEBUG grau); GET /api/logs?since= Endpoint mit Circular Buffer (300 Einträge)

## [1.6.35] - 2026-06-06
- Fix: Medien-Log-Meldung auf Englisch (photo/voice message/video on disk)

## [1.6.34] - 2026-06-06
- Fix: Unhandled rejection 'no pic' — promise.finally() durch .then(del,del) ersetzt (Avatar-Endpoint)
- Neu: Startup-Log zeigt Medien-Breakdown: X Foto(s), Y Sprachnachricht(en), Z Video(s) auf Disk

## [1.6.33] - 2026-06-06
- Fix: type-Feld fehlte in lastReceivedMsg beim Startup-Init; preview für location/video/voice fehlte im Init und Runtime

## [1.6.32] - 2026-06-06
- Fix: 🎬 Medien-Button blendet jetzt auch Videos aus (nicht nur Fotos) — Icon 📷→🎬, Label Fotos→Medien (DE/EN)

## [1.6.31] - 2026-06-06
- Fix: 🗑️-Button beim Video funktionierte nicht — JSON.stringify(m.id) brach das onclick-Attribut durch eingebettete Anführungszeichen; ersetzt durch data-msgid + this.dataset.msgid

## [1.6.30] - 2026-06-06
- UX: Sendeleisten-Buttons (😊 📎 📍) in einer Gruppe ohne Gap — liegen jetzt dicht beieinander

## [1.6.29] - 2026-06-06
- Fix: enforceMediaLimit fehlte in WhatsApp — Funktion hinzugefügt
- Fix: Auto-Download von Videos verursachte 'no pic'-Fehler — Videos werden jetzt immer als Platzhalter angezeigt und nur on-demand heruntergeladen

## [1.6.28] - 2026-06-06
- Fix: 📍-Button in der Sendeleiste wurde grün und rund wie der Send-Button — CSS-Override für #location-btn wie bei #attach-btn
- Fix: Standort-Preview zeigte WhatsApp-interne Zeichen — type='location' wird vor msg.body geprüft, zeigt immer '📍 Standort' oder '📍 Name'

## [1.6.27] - 2026-06-06
- Neu: Video-Support — neue Videos werden automatisch geladen (wenn ≤ video_max_mb), ältere als Platzhalter mit Klick-Download; 🗑️-Button löscht Datei von Disk; Speicheranzeige aktualisiert sich sofort
- Neu: video_max_mb Option (Standard 50 MB) in config.yaml und Translations (DE/EN)

## [1.6.26] - 2026-06-06
- Neu: Standort empfangen — wird als klickbarer 📍 Google-Maps-Link angezeigt (DE/EN, inkl. HTML-Export)
- Neu: Standort senden — 📍-Button in der Sendeleiste öffnet Modal mit GPS-Button und manueller Lat/Lng/Name-Eingabe

## [1.6.25] - 2026-06-06
- Fix: Hover-Buttons verschieben gesendete Nachrichten — opacity statt display:none, order:-1 für out-Nachrichten (Buttons erscheinen links der Bubble)

## [1.6.24] - 2026-06-06
- Fix: Hover-✕-Button zum Löschen entfernt — Löschen läuft jetzt ausschließlich über den Multi-Select-Modus

## [1.6.23] - 2026-06-06
- Fix: Multi-Löschen überspringt Nachrichten — neuer Batch-Endpoint verarbeitet Löschungen sequenziell mit 400ms Delay, WhatsApp Web.js kommt mit schnellen parallelen delete()-Aufrufen nicht klar

## [1.6.22] - 2026-06-06
- Neu: ☀️/🌙-Button neben "WhatsApp" zum Umschalten Dark/Light Mode; Auswahl wird per localStorage gespeichert

## [1.6.21] - 2026-06-06
- Fix: Multi-Löschen löschte nur erste Nachricht auf dem Handy — Promise.all durch sequenzielle Schleife ersetzt, WhatsApp Web.js verarbeitet delete() nicht parallel

## [1.6.20] - 2026-06-06
- Neu: Multi-Select-Löschmodus — ✕-Button in der Toolbar, Nachrichten anklicken zum Markieren (rote Hervorhebung), 🗑️-Button löscht alle markierten mit Bestätigungsdialog (DE/EN); Escape oder Chat-Wechsel bricht Modus ab
- Fix: Spam-Delete-Button von 🗑️ auf 🚮 geändert um Verwechslung mit Löschmodus zu vermeiden

## [1.6.19] - 2026-06-06
- Fix: HTML-Export brach bei Sprachnachrichten ab — base64-Einbettung entfernt, werden als Platzhalter (🎵) angezeigt
- Fix: Sprachnachrichten mit mediaFile wurden fälschlich als Foto exportiert
- Neu: HTML-Export vollständig lokalisiert (DE/EN)

## [1.6.18] - 2026-06-06
- Neu: media_max_mb im Startup-Log ausgeben

## [1.6.17] - 2026-06-06
- Fix: SyntaxError durch \\n in Template-Literal — Tooltip-Strings verwendeten \\n (Literal-Newline) statt \\\\n (Escape-Sequenz)

## [1.6.16] - 2026-06-06
- Neu: media_max_mb Option (Standard 500 MB) + Speicher-Tooltip (Mouseover auf 💾 zeigt Medienordner-Größe, Limit und % bis Auto-Delete, DE+EN)

## [1.6.15] - 2026-06-05
- Revert auf stabile Basis v1.6.10 (Version-Bump für HA-Update-Erkennung)

## [1.6.10] - 2026-06-05
- Kontaktinfo-Modal: savedName (Telefonbuch) als Hauptname, waName (WhatsApp-Profilname) als Label wenn abweichend; shortName als Fallback

## [1.6.9] - 2026-06-05
- Fix: Telefonnummer im Kontaktinfo-Modal war falsch (contact.number liefert Müll); jetzt contact.id.user aus der chatId extrahiert

## [1.6.8] - 2026-06-05
- Lade-Reihenfolge: Kontakte sofort (Initialen) → Nachrichten → Avatare nachgelagert (max 2 parallel, 200ms Verzögerung); renderChatList blockiert keine HTTP-Slots mehr

## [1.6.7] - 2026-06-05
- Fix: api() in WhatsApp-Client nicht definiert → ReferenceError brach renderChatList-Schleife ab; alle Avatar/Kontakt-Pfade auf direkte Relative-URL umgestellt

## [1.6.6] - 2026-06-05
- Fix: Leere Chat-Liste nach Avatar-Update — renderChatList feuerte bei jedem Poll-Zyklus N parallele getContactById-Requests; jetzt einmaliger Load pro Chat mit client-seitigem State-Cache und server-seitigem Request-Dedup

## [1.6.5] - 2026-06-05
- Neu: Profilbilder als echte Avatare (lazy-load, 1h-Cache server+Browser); Klick auf Header-Avatar öffnet Kontaktinfo-Modal mit Foto, Name, Nummer und About

## [1.6.4] - 2026-06-05
- Neu: `type`-Feld in `GET /api/last-received` und Webhook-Payload (text/photo/document/voice)

## [1.6.3] - 2026-06-05
- Fix: Audio-Player zu schmal — Chrome zeigte nur Drei-Punkte-Menü statt voller Controls; min-width:220px gesetzt

## [1.6.2] - 2026-06-05
- Fix: Sprachnachrichten nicht abspielbar — Media-Endpoint lieferte .ogg als image/jpeg; MIME-Type für ogg + mp3 ergänzt

## [1.6.1] - 2026-06-05
- Fix: Ältere Sprachnachrichten werden beim Start automatisch nachgeladen (Auto-Download auf voice erweitert)
- Fix: Audio-Player-Darstellung korrigiert (feste Höhe entfernt, Browser rendert Controls vollständig)
- Fix: Log-Meldungen für Auto-Download auf photo+voice verallgemeinert

## [1.6.0] - 2026-06-05
- Fix: Sprachnachrichten wurden im Chat nicht angezeigt — Voice-Rendering fehlte im Client-seitigen Render-Zweig; Audio-Player und Fallback-Text jetzt korrekt

## [1.5.9] - 2026-06-05
- Neu: Sprachnachrichten (ptt/audio) werden empfangen, als .ogg auf Disk gespeichert und im Chat als abspielbarer Audio-Player angezeigt; Fallback-Platzhalter wenn Download fehlschlägt

## [1.5.8] - 2026-06-04
- fix: Datum in Log-Zeitstempel ergänzt — war nur Uhrzeit, jetzt vollständig

## [1.5.7] - 2026-06-04
- Log-Ausgaben mit Datum und Uhrzeit: `[INFO] [YYYY-MM-DD HH:MM:SS] Nachricht`

## [1.5.6] - 2026-06-03
- Fix: run.sh Shebang auf #!/bin/sh — node:lts-alpine hat kein bash

## [1.5.5] - 2026-06-03
- Build: Image wird jetzt via GitHub Actions auf GHCR gebaut (ghcr.io/luckytriple7/whatsapp)
- Build: Basis-Image auf node:lts-alpine umgestellt (multi-arch, kein lokaler HA-Build mehr nötig)

## [1.5.4] - 2026-06-03
- Neu: Auto-Reconnect bei Verbindungsabbruch — `disconnected`-Event löst nach 5s automatischen Reconnect aus; Keep-Alive-State-Check alle 10 Minuten erkennt hängende Puppeteer-Instanzen; `_intentionalDisconnect`-Flag verhindert ungewollten Reconnect bei Logout/Reset

## [1.5.3] - 2026-06-02
- Fix: Kein Unread-Dot für eigene gesendete Nachrichten — lastFromMe-Flag verhindert falsches Unread-Indikator

## [1.5.2] - 2026-05-31
- Fix: Backtick im Paste-Handler durch String-Verkettung ersetzt (Template-Literal-Konflikt → Crash beim Start)

## [1.5.1] - 2026-05-31
- Neu: Bilder aus der Zwischenablage direkt ins Chat-Eingabefeld einfügen (Strg+V / Cmd+V)

## [1.5.0] - 2026-05-30
- Docs: ha_token-Admin-Anforderung dokumentiert — kein Admin-Benutzer erforderlich

## [1.4.30] - 2026-05-30
- Fix: Zurück-Pfeil linksbündig, restliche Topbar-Elemente rechtsbündig (margin-right: auto)

## [1.4.29] - 2026-05-30
- UX: Mobile Navigation — App-Name im Topbar ausgeblendet wenn Chat offen, stattdessen eleganter Zurück-Pfeil (SVG Chevron); Avatar-Klick-Navigation entfernt

## [1.4.28] - 2026-05-30
- Neu: Sicherheitsabfrage beim Abmelden — Popup mit Ja/Nein-Buttons (DE/EN)

## [1.4.27] - 2026-05-30
- Fix: Reactions nach Neustart sofort sichtbar — beim Disk-Load wird applyReactionsToMsg() aufgerufen, sodass reactionsCache direkt auf die geladenen Nachrichten angewendet wird (bisher fehlte dieser Schritt, Reactions kamen erst nach erneutem Sync vom WA-Server)

## [1.4.26] - 2026-05-30
- Neu: DE/EN-Übersetzungen für Option `ha_notifications_skip_groups` ergänzt

## [1.4.25] - 2026-05-30
- Neu: Option `ha_notifications_skip_groups` (Standard: aus) — unterdrückt HA-Benachrichtigungen und REST-API-Updates für Gruppenchats (analog zu Telegram `ha_notifications_skip_bots`)

## [1.4.24] - 2026-05-30
- Fix: Gruppennachrichten lösen jetzt HA-Benachrichtigungen und REST-API-Updates aus — msg.getChat() schlägt für Gruppen oft fehl; Fallback auf chatMap-Cache wenn Chat bekannt ist

## [1.4.23] - 2026-05-30
- Fix: Chat-Header Mobile — Zurück-Pfeil ausgeblendet, Avatar-Klick navigiert zurück zur Chat-Liste
- Fix: Stats-Zeile im Chat-Header bricht auf Mobile um (white-space: normal, 10px) statt abgeschnitten zu werden
- Fix: #ch-info Wrapper erhält flex:1; min-width:0 damit Stats-Bereich korrekt schrumpft

## [1.4.22] - 2026-05-30
- Fix: JavaScript `visualViewport`-Fix für Android WebViews — setzt `--app-height` dynamisch auf die tatsächlich sichtbare Viewport-Höhe; verhindert zuverlässig dass Navigationsleiste die Eingabeleiste verdeckt, auch in Apps die `env(safe-area-inset-bottom)` nicht unterstützen

## [1.4.21] - 2026-05-30
- Fix: `viewport-fit=cover` + `padding-bottom: env(safe-area-inset-bottom)` auf `#send-bar` — verhindert, dass Android-Navigationsleiste die Eingabeleiste im Vollbildmodus verdeckt

## [1.4.20] - 2026-05-30
- Fix: `height: 100dvh` statt `100vh` — verhindert auf Android Chrome, dass die Eingabeleiste hinter der Adressleiste verschwindet

## [1.4.19] - 2026-05-29
- Fix: Logout-Button ersetzt ⏻ Unicode durch SVG-Icon — rendert auf allen Mobile-Browsern korrekt (identisch mit CardBoard-Fix)

## [1.4.18] - 2026-05-29
- Neu: Sprache wird automatisch anhand der Browsersprache erkannt (DE/EN) — kein manuelles Umschalten mehr nötig beim ersten Start
- Fix: Sprach-Umschalter (🌐) in der mobilen Ansicht ausgeblendet, bleibt in der Desktop-Ansicht sichtbar
- Fix: Logout-Button auf Mobile korrekt dargestellt (flex-shrink verhindert Quetschen, kleinerer Gap im Topbar)

## [1.4.17] - 2026-05-29
- Neu: REST-Endpoint `GET /api/last-received` — liefert Zeitpunkt, Chat, Kontakt und Vorschau der zuletzt empfangenen Nachricht; optional mit `?chat=<chatId>` für einen bestimmten Chat; wird beim Start aus den gespeicherten Nachrichten initialisiert
- Doku: HA-Sensor-Beispiel für `configuration.yaml` und Dashboard-Karte ergänzt

## [1.4.16] - 2026-05-27
- Fix: Absendername zeigt Adressbuch-Name (name) statt WhatsApp-Profilname (pushname) — pushname nur als Fallback wenn kein Adressbucheintrag

## [1.4.15] - 2026-05-26
- Fix: Port 3000 war in run.sh und Dockerfile noch hardcoded (17776 funktioniert jetzt vollständig)

## [1.4.14] - 2026-05-26
- Change: Standard-Port von 3000 auf 17776 geändert (Konflikt mit anderem Add-on vermieden)

## [1.4.13] - 2026-05-25
- Fix: Zitat-Text in Chatblasen besser lesbar (höherer Kontrast, dunklerer Hintergrund)

## [1.4.12] - 2026-05-25
- Entfernt: "Fotos nachladen"-Button — Auto-Download beim Start mit Disk-Persistenz macht ihn überflüssig

## [1.4.11] - 2026-05-25
- Fix: Konfig-Log "Konfiguration", "gesetzt"/"nicht gesetzt" auf Englisch

## [1.4.10] - 2026-05-25
- Fix: Alle Log-Meldungen auf Englisch vereinheitlicht

## [1.4.9] - 2026-05-25
- UX: Header-Buttons (📥 💾 🗑️) zeigen nur Icon — Text entfällt, Tooltip bleibt per Mouseover sichtbar; passt jetzt auch in der mobilen Ansicht
- Neu: Log beim Start zeigt wie viele Fotos bereits auf Disk sind und kein Download nötig ist

## [1.4.8] - 2026-05-25
- Fix: Heruntergeladene Foto-Pfade (mediaFile) wurden nach dem Auto-Download beim Start nicht auf Disk gespeichert — Fotos wurden bei jedem Neustart erneut heruntergeladen

## [1.4.7] - 2026-05-25
- Fix: Kritischer Bug — Disk-Loading schlug beim Start lautlos fehl (ReferenceError: trimmed is not defined), alle Nachrichten gingen bei jedem Neustart verloren

## [1.4.6] - 2026-05-25
- Entfernt: Option `max_messages_per_chat` — Nachrichten werden unbegrenzt auf Disk gespeichert und überleben Neustarts; kein RAM-Limit mehr nötig

## [1.4.5] - 2026-05-25
- Fix: Chat-Statistik jetzt zweisprachig (DE/EN) über i18n-System

## [1.4.4] - 2026-05-25
- Neu: Chat-Statistik im Header — Gesamtnachrichten, ↑ gesendet, ↓ empfangen, 📷 Fotos, seit [Datum der ersten Nachricht]

## [1.4.3] - 2026-05-25
- Neu: Beim Start werden alle konfigurierten Optionen im Log ausgegeben (HA-Token wird nur als "gesetzt"/"nicht gesetzt" angezeigt)

## [1.4.2] - 2026-05-25
- Neu: `keep_deleted=true` zeigt originalen Nachrichteninhalt + kleines 🚫-Badge — Antworten/Weiterleiten/Emoji-Buttons werden ausgeblendet
- Fix: Gelöschte Nachrichten in Echtzeit in der UI aktualisiert (Poll-Endpoint liefert deletedAt-Nachrichten; vorhandener Bubble wird in-place ersetzt statt dupliziert)
- Fix: Translations aktualisiert — `keep_deleted`-Beschreibung angepasst (beide Modi erklärt)

## [1.4.1] - 2026-05-25
- Neu: Option `keep_deleted` (Standard: false) — bei true wird das Lösch-Event ignoriert, Nachricht bleibt unverändert sichtbar (kein 🚫, alle Buttons bleiben aktiv)

## [1.4.0] - 2026-05-25
- Fix: "Nachricht wurde gelöscht" Text besser lesbar (Kontrast 0.45 → 0.75, Light-Mode-Unterstützung)
- Fix: MAX_MESSAGES_PER_CHAT fehlte in run.sh → Option wurde ignoriert

## [1.3.32] - 2026-05-24
- Fix: Eigene gelöschte Nachrichten werden jetzt sofort als "🚫 gelöscht" in der UI markiert (vorher blieben sie sichtbar wenn delete(true) fehlschlug)
- Fix: message_revoke_everyone Handler robuster + immer geloggt; message_revoke_me als Fallback ergänzt
- Fix: Server-seitiges delete(true) schlägt nicht mehr fehl wenn Nachricht nicht mehr in WA-Cache

## [1.3.31] - 2026-05-24
- Neu: Gelöschte Nachrichten werden als „🚫 Diese Nachricht wurde gelöscht" angezeigt statt entfernt (funktioniert für eingehende und eigene gelöschte Nachrichten)

## [1.3.30] - 2026-05-24
- Neu: Nachrichten-Persistenz — Chats und Nachrichten werden in `/config/chats.json` und `/config/messages.json` gespeichert und überleben Neustarts
- Fix: `initial_messages`-Hinweis in Translations ergänzt (WhatsApp Web Cache-Begrenzung)

## [1.3.29] - 2026-05-24
- Neu: `max_messages_per_chat` konfigurierbar (Standard 200) — maximale Nachrichten im RAM-Puffer pro Chat

## [1.3.28] - 2026-05-24
- Fix: Export-Button funktionierte nicht (undefinierte `api()`-Funktion; relativer Pfad verwendet)

## [1.3.27] - 2026-05-24
- Neu: Chat-Export als HTML — 💾 Export-Button im Chat-Header; Bilder werden inline eingebettet (base64)

## [1.3.26] - 2026-05-24
- Fix: Gruppen-Avatar war zu dunkel (#2a3942 → #25D366 WhatsApp-Grün)

## [1.3.25] - 2026-05-24
- Neu: Filter-Tabs „Alle / Privat / Gruppen" in der Chat-Liste
- Neu: Gruppen-Chats zeigen 👥-Avatar statt Initialen

## [1.3.24] - 2026-05-24
- Fix: Klammer-Button hatte ungewollten grünen Kreis (CSS-Spezifität korrigiert)

## [1.3.23] - 2026-05-24
- Neu: Datei-Upload über 📎-Klammer-Button — Bilder und Dokumente (PDF, Word usw.) direkt aus dem Browser an WhatsApp-Chats senden
- Neu: Eingehende Dokument-Nachrichten werden mit Dateiname angezeigt
- Abhängigkeit multer für Multipart-Upload hinzugefügt

## [1.3.22] - 2026-05-23
- Fix: Chromium-Cache auf 50 MB begrenzt (--disk-cache-size) — verhindert unbegrenztes Speicherwachstum
- Fix: Cache-Verzeichnisse (Cache, Cache2, Code Cache, GPUCache) werden beim Start bereinigt

## [1.3.21] - 2026-05-23
- Session, Media, Reaktionen nach /config (addon_config Share) verschoben — im Dateimanager sichtbar und sicherbar
- Migration: vorhandene /data/session wird einmalig automatisch kopiert (kein QR-Scan nötig)

## [1.3.20] - 2026-05-22

### Neu
- **whatsapp-web.js Version im Log** — beim Start wird die installierte API-Version geloggt: `[INFO] whatsapp-web.js v1.26.x`

## [1.3.19] - 2026-05-22

### Behoben
- **Eigene Reaktion konnte nicht entfernt werden** — Alle vorherigen Fixes versuchten `isOwn` über JID-Vergleich zu ermitteln (`senderId` aus `message_reaction` vs. `connectedPhone`). Dieser Vergleich schlug in dieser HA-Installation immer fehl, weil WhatsApp intern unterschiedliche JID-Formate für den Sender und die verbundene Nummer verwendet. Lösung: JID-Vergleich vollständig entfernt. Eigene Reaktionen werden jetzt direkt in `/api/react` in einer `myReactions`-Map gespeichert (msgId → Emoji). `own` wird in `/api/reactions` aus dieser Map gelesen — kein JID-Abgleich mehr nötig. Die Map wird in `/data/ownreactions.json` persistiert.

## [1.3.18] - 2026-05-22

### Behoben
- **Reaktion konnte nicht entfernt werden** — `renderMessages` renderte Reaktions-Badges mit `isOwn = false` (client-seitiger JID-Vergleich); `updateReactionsInDOM` korrigierte das erst beim nächsten Poll (bis zu 5 s später). Fix: Reaktions-Bars werden nicht mehr in `renderMessages` erstellt. Stattdessen wird nach jedem `renderMessages`-Aufruf sofort `pollReactions()` aufgerufen, das `updateReactionsInDOM` mit dem server-seitigen `own`-Flag ausführt.

## [1.3.17] - 2026-05-22

### Behoben
- **Reaktion konnte nicht entfernt werden** — Client-seitiger JID-Vergleich (`senders.includes(myJid)`) war grundsätzlich fehleranfällig. Lösung: `/api/reactions` berechnet `isOwn` jetzt serverseitig und gibt `{ count, own }` pro Emoji zurück. Der Client vergleicht keine JIDs mehr.

## [1.3.16] - 2026-05-22

### Behoben
- **Reaktion konnte nicht entfernt werden** — `isOwn`-Erkennung schlug fehl weil der Client `myPhone + "@c.us"` selbst zusammenbaute, was nicht mit der vom Server normalisierten JID übereinstimmte. Lösung: `/api/status` liefert jetzt `myJid` (fertig normalisiert), der Client verwendet diese direkt für den `senders.includes(myJid)`-Vergleich.

## [1.3.15] - 2026-05-22

### Behoben
- **Reaktionszahl springt nach kurzer Zeit auf 2** — Ursache in v1.3.14: Der 3s-Fallback-Timer in `/api/react` wurde nicht gecancelt wenn `message_reaction` mit einem JID eintraf der nicht exakt mit `myJid` übereinstimmte (z. B. andere Schreibweise). Dadurch wurden beide Einträge gespeichert. Fix: Fallback-Timer und lokales Update komplett entfernt. Nur `message_reaction` aktualisiert Reaktionen (wie vor v1.3.10, wo es funktionierte). Die Persistenz in `reactions.json` bleibt erhalten da `message_reaction` weiterhin in den Cache schreibt.

## [1.3.14] - 2026-05-22

### Behoben
- **Reaktionszahl immer noch 2** — Grundursache: `/api/react` und `message_reaction`-Event aktualisierten Reaktionen beide gleichzeitig. `message_reaction` ist jetzt der **einzige** Updater; `/api/react` ruft nur noch `msg.react()` auf und setzt einen 3-Sekunden-Fallback-Timer (für den seltenen Fall dass das Event nicht feuert). Der Timer wird sofort gecancelt wenn `message_reaction` für die eigene Nachricht eintrifft. Poll-Delay nach Reaktion von 800 ms auf 1500 ms erhöht damit das Event sicher vorher eintrifft.

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
