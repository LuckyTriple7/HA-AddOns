# Changelog

## [1.8.9] - 2026-08-28
- Fix: **Chats mit langem Verlauf brauchten lange zum Oeffnen und die Ansicht sprang herum**, besonders auf dem Handy. Der Browser holte den kompletten Verlauf und baute ihn in einem Rutsch auf — bei einem Chat mit 420 Nachrichten also alle 420. Jetzt kommen zuerst die **juengsten 50**, aeltere auf Abruf
- Oben im Chat steht dafuer „↑ Ältere Nachrichten laden · 50 von 420 geladen"; scrollt man ohnehin nach oben, laedt der naechste Schwung von selbst nach. Dabei bleibt die Blickposition erhalten — die Nachricht, die man gerade liest, bleibt an ihrem Platz
- Die Suche ueber alle Chats geht weiterhin punktgenau: liegt ein Treffer weiter zurueck, laedt der Sprung so lange nach, bis die Nachricht da ist
- `GET /api/messages` versteht dafuer `?limit=n` (juengste n, Antwort mit `more` und `total`) und `?before=<ts>` (die aelteren davor). Ohne `limit` bleibt es bei der vollstaendigen Liste

## [1.8.8] - 2026-08-28
- Feature: **Die laufende WhatsApp-Web-Fassung ist jetzt sichtbar.** Sie steht beim Verbinden im Log und in der Kopfzeile der Konsole, zusammen mit der Fassung von `whatsapp-web.js`: „⬛ CONSOLE — WhatsApp · WA Web 2.3000.… · lib 1.34.…". `GET /api/status` liefert sie als `waWeb` und `lib` mit
- Nuetzlich, weil sich daran festmachen laesst, wann ein Umbau bei WhatsApp etwas hier zerlegt hat — genau das war heute mehrfach die Ursache

## [1.8.7] - 2026-08-28
- Feature: **X zum Leeren im Suchfeld der Seitenleiste.** Erscheint nur, wenn etwas drinsteht, raeumt Feld und Filter weg und laesst den Cursor im Feld — auch im Kontakte-Reiter

## [1.8.6] - 2026-08-28
- Feature: **Pruefen, ob eine Rufnummer bei WhatsApp ist** — ohne sie zu speichern und ohne ihr zu schreiben. Das kann die WhatsApp-App nicht. Tippt man in der Seitenleiste etwas, das nach einer Rufnummer aussieht, erscheint die Zeile „📱 „…" bei WhatsApp prüfen"; im Kontakte-Reiter steht ausserdem unten ein Knopf dafuer
- Bei einem Treffer nennt das Ergebnis die Nummer, den gespeicherten Namen (oder „nicht im Adressbuch") und den Info-Text; ein Knopf oeffnet direkt den Chat — auch wenn es bisher keinen gab
- Die Anfrage geht an WhatsApps Server, deshalb hoechstens 20 Abfragen je Minute. Neu: `GET /api/check-number?number=<nr>`

## [1.8.5] - 2026-08-28
- Feature: **Suche über alle Chats.** Tippt man in der Seitenleiste, erscheint darueber die Zeile „🔍 „…" in allen Nachrichten suchen" — ein Klick oder Enter oeffnet die Trefferliste. Jeder Treffer nennt Chat, bei Gruppen zusaetzlich den Absender, Datum und Uhrzeit sowie einen Textausschnitt mit hervorgehobenem Suchwort. Ein Klick springt in den Chat direkt zur Nachricht und hebt sie fuenf Sekunden lang hervor
- Zwei Quellen: der eigene Nachrichtenspeicher, wo punktgenaues Anspringen moeglich ist, und **WhatsApps eigene Suche**, die auch aelteres findet, was hier nie gespeichert wurde. Solche Treffer sind als „nicht im lokalen Verlauf" gekennzeichnet und oeffnen nur den Chat. Die Fusszeile nennt beide Zahlen
- Neu: `GET /api/search?q=<text>`; ab zwei Zeichen, hoechstens 80 Treffer (`?limit=`), `?remote=0` beschraenkt auf den eigenen Verlauf

## [1.8.4] - 2026-08-28
- Aenderung: **Das Schloss bei blockierten Kontakten ist jetzt deutlich zu sehen.** Das schmale Band am unteren Rand ging auf Fotos unter — stattdessen liegt ein dunkler Schleier ueber dem ganzen Profilbild, mit grossem Schloss in der Mitte. Im Kontaktfenster entsprechend groesser

## [1.8.3] - 2026-08-28
- Feature: **Gemeinsame Gruppen im Kontaktfenster.** Darunter stehen die Gruppen, in denen ihr beide seid — ein Klick oeffnet die jeweilige Gruppe direkt
- Feature: **Anzahl verknuepfter Geraete.** Die zeigt die WhatsApp-App nirgends an. Ein normales Konto mit einer Web-Sitzung meldet zwei (Telefon und Web), mehr Geraete entsprechend mehr
- Beides laeuft ueber einen eigenen Endpunkt `GET /api/contact/:chatId/extra` und wird nachgelagert geladen, damit das Kontaktfenster genauso schnell aufgeht wie bisher. Bei Gruppen und ohne Treffer bleiben die Zeilen ausgeblendet

## [1.8.2] - 2026-08-28
- Feature: **Blockierte Kontakte sind auf einen Blick zu erkennen.** In der Chat- und in der Kontaktliste traegt das Profilbild ein rotes Band mit Schloss am unteren Rand, im Kontaktfenster ebenso. Die Liste der blockierten Kontakte wird beim Verbinden geladen, danach alle fuenf Minuten aufgefrischt und sofort nach jedem Blockieren oder Aufheben
- Der Abgleich laeuft ueber ID **und** Rufnummer: WhatsApp fuehrt blockierte Kontakte unter der Adressbuch-ID, die Chats teils unter `@lid` — ohne den zweiten Weg fehlte das Schloss genau dort, wo es hingehoert
- `GET /api/blocked` haelt sein Ergebnis eine Minute vor, weil die Anzeige es staendig braucht; `?refresh=1` umgeht das

## [1.8.1] - 2026-08-28
- Feature: **Kontakte blockieren und entblocken.** Im Kontaktfenster — erreichbar ueber das Profilbild — steht unten ein Knopf dafuer. Ist jemand blockiert, sagt das eine rote Zeile, und der Knopf heisst „Blockierung aufheben". Beide Richtungen fragen vorher nach, mit Namen und einem Satz dazu, was das bedeutet
- Gruppen lassen sich nicht blockieren, dort bleibt der Knopf verborgen
- Neu: `GET /api/blocked` listet die blockierten Kontakte, `POST /api/contact/:chatId/block` und `.../unblock` schalten um. `GET /api/contact/:chatId` liefert zusaetzlich `isBlocked`

## [1.8.0] - 2026-08-28
- Fix: **In der Konsole fehlte bei vielen Zeilen die Uhrzeit.** Die still protokollierten Debug-Zeilen (`API GET …`) trugen keinen Zeitstempel, die echten Konsolenzeilen schon — jetzt haben alle einen, und zwar in Ortszeit statt UTC
- Feature: **Filter in der Konsole.** Vier Schalter fuer ERROR, WARN, INFO und DEBUG blenden Ebenen aus, ein Textfeld filtert zusaetzlich nach Inhalt. Der Zaehler rechts zeigt „sichtbar/gesamt". Ein Filterwechsel wirkt auch auf bereits eingetroffene Zeilen, weil die letzten 1500 Meldungen im Browser vorgehalten werden. Die Auswahl der Ebenen bleibt ueber einen Seitenwechsel hinweg erhalten

Diese Fassung buendelt die Arbeit der letzten Runde:

- Eigene Statusmeldungen senden — Text mit Hintergrundfarbe und Schrift, Bild und Video, Vorlagen, Zuruecknahme, Info-Text im Profil (1.7.59 bis 1.7.69)
- Bilder werden vor jedem Upload im Browser verkleinert, auch bei Chat-Anhaengen (1.7.66, 1.7.67)
- „Zuletzt online" im Kontaktfenster und als Uebersicht ueber alle Kontakte, mit optionalem Rundlauf im Hintergrund (1.7.70 bis 1.7.74)
- Die Gespraechs-Statistik ist von der Chat-Kopfzeile ins Kontaktfenster gewandert (1.7.73)

## [1.7.74] - 2026-08-28
- Feature: **Zuletzt-online-Übersicht ueber alle Kontakte.** Im Reiter „Kontakte" fuehrt unten ein Knopf zu einer Tabelle mit Name, letztem Zeitpunkt und wann zuletzt geprueft wurde — online zuerst, dann nach Zeitpunkt sortiert. „Jetzt aktualisieren" startet einen Rundlauf von Hand
- Ein Rundlauf abonniert die Praesenz aller bekannten Einzelkontakte (hoechstens 300, in Haeppchen zu 25), wartet einmal neun Sekunden auf die asynchronen Antworten und liest dann alle Modelle aus — eine Runde statt einer Abfrage je Kontakt
- Neue Option **`presence_scan_minutes`** (Standard 0 = aus) fuer den automatischen Rundlauf im Hintergrund; 15 bis 60 Minuten sind sinnvolle Werte. Bewusst standardmaessig aus, weil man sich fuer die Dauer eines Rundlaufs als verfuegbar meldet und so lange fuer die Kontakte online erscheint — es sei denn, `presence_mode` steht auf `off`
- Die Daten ueberleben einen Neustart (`/config/presence.json`). Liefert WhatsApp zu einem Kontakt nichts, bleibt der alte Zeitpunkt stehen, statt von Leere ueberschrieben zu werden

## [1.7.73] - 2026-08-28
- Aenderung: **Die Gespraechs-Statistik ist von der Chat-Kopfzeile ins Kontaktfenster gewandert** — dorthin, wo man ueber das Profilbild hinkommt. Die Kopfzeile zeigt jetzt nur noch Name und Rufnummer, die Statistik steht unter dem Info-Text: Anzahl der Nachrichten, gesendet, empfangen, Fotos und seit wann
- Bei Kontakten ohne Chatverlauf entfaellt die Zeile ganz, statt eine Null anzuzeigen

## [1.7.72] - 2026-08-28
- Feature: **Dauerhaft online sein ist nicht mehr noetig.** Die Verfuegbarkeit wird jetzt nur noch fuer die Dauer einer Abfrage gemeldet und danach wieder abgemeldet. Man erscheint also hoechstens fuer die paar Sekunden online, in denen man ein Kontaktfenster oeffnet
- Die Option `presence_announce` (an/aus) weicht dafuer `presence_mode` mit drei Werten: `temporary` (Standard, kurz melden und wieder abmelden), `always` (dauerhaft, wie bisher) und `off` (nie melden — „zuletzt online" bleibt dann meist leer). Wer `presence_announce` gesetzt hatte, stellt bitte `presence_mode` neu ein
- Parallele Abfragen zaehlen mit, damit sie sich nicht gegenseitig abmelden, und nach der letzten wird mit zwei Sekunden Karenz abgemeldet — schnelles Durchklicken schaltet so nicht dauernd an und aus

## [1.7.71] - 2026-08-28
- Fix: **„Zuletzt online" meldete immer „keine Angabe".** Das Debug-Log zeigte `hasData:false` bei leerem `chatstate` — es kam nie eine Praesenz-Aktualisierung. Grund: `model.subscribe()` ist im Presence-Modell nur ein `collection.find()` und sendet gar kein Abo. Das erledigt `WAWebSendPresenceSubscriptionJob.sendUserPresenceSubscription(wid)`, das jetzt aufgerufen wird; `model.subscribe()` bleibt als Rueckfall. Die Wartezeit stieg von 3,5 auf 6 Sekunden
- Neue Option **`presence_announce`** (Standard: aus). WhatsApp liefert fremde Praesenz nur an Geraete, die sich selbst als verfuegbar melden. Die Option macht das — mit der Nebenwirkung, dass man fuer seine Kontakte als online erscheint, solange das Add-on laeuft. Deshalb bewusst abschaltbar und standardmaessig aus
- `GET /api/presence/:chatId?announce=1` erzwingt die Meldung fuer einen einzelnen Test, `?announce=0` unterdrueckt sie

## [1.7.70] - 2026-08-28
- Feature: **„Zuletzt online" im Kontaktfenster.** `whatsapp-web.js` kann fremde Praesenz nicht lesen — nur die eigene senden. WhatsApp Web fuehrt sie aber in der `PresenceCollection`: das Modell hat `subscribe()`, `isOnline` und darunter `chatstate` mit `type`, `t` (Zeitpunkt) und `deny`. Das Add-on abonniert die Praesenz beim Oeffnen des Kontakts und zeigt eines von vier Ergebnissen: „online" (gruen), „zuletzt online: Heute, 08:53", „zuletzt online: nicht sichtbar" (der Kontakt erlaubt es nicht) oder „zuletzt online: keine Angabe"
- Ohne Abo liefert WhatsApp nichts, und die Antwort kommt asynchron — deshalb steht bis zu dreieinhalb Sekunden „wird geprueft" da. Fuer Gruppen entfaellt die Anzeige
- Neu: `GET /api/presence/:chatId` liefert `online`, `lastSeen` (Millisekunden) und `denied`; im Debug-Modus zusaetzlich die Rohwerte aus WhatsApp Web

## [1.7.69] - 2026-08-28
- Feature: **„Auswahl entfernen" im Bild-Reiter.** Ein gewaehltes Bild liess sich bisher nur durch Auswahl eines anderen ersetzen. Der Knopf erscheint, sobald etwas gewaehlt ist — auch waehrend das Bild noch verkleinert wird — und raeumt Vorschau, Dateifeld und Bildunterschrift weg
- Fix: **Der Editor merkte sich alles ueber „Abbrechen" hinweg.** Beim naechsten Oeffnen stand noch das zuletzt gewaehlte Bild da und liess sich versehentlich ein zweites Mal posten. Beim Oeffnen wird jetzt zurueckgesetzt: Text, Bild, Bildunterschrift, Farbe, Schrift und der Vorlagenname
- Nach erfolgreichem Posten raeumt sich der Editor ebenfalls auf — die Erfolgsmeldung bleibt stehen

## [1.7.68] - 2026-08-28
- Fix: **Bild-Status scheiterte mit „Cannot read properties of undefined (reading 'id')".** Der Fehler kam aus WhatsApps eigenem Code. Der Quelltext des Bundles zeigt, warum: die Aktion erwartet ein Objekt — `sendStatusMediaMsgAction({ beforeSend, funnelContext, mediaMsgData })` — und liest daraus `mediaMsgData.id.fromMe`. `whatsapp-web.js` ruft sie dagegen als `(msgModel, mediaUpdate)` auf, womit `mediaMsgData` undefiniert ist. Vor dem Versand wird die Aktion jetzt umhuellt: die alte Aufrufform wird in die erwartete umgesetzt, ein bereits richtiger Aufruf geht unveraendert durch
- Die Umhuellung greift nur, wenn die Aktion hoechstens einen Parameter nimmt. Sollte WhatsApp wieder auf zwei Parameter wechseln, bleibt sie unangetastet und das Log sagt es
- Zum Vergleich: der Text-Versand war nie betroffen — dort ist der zweite Parameter nur der `funnelContext` fuer die Statistik

## [1.7.67] - 2026-08-28
- Feature: **Auch Bildanhaenge im Chat werden vor dem Hochladen verkleinert**, nicht nur Status-Bilder — die Groessengrenze auf dem Weg trifft jeden Upload. Die Anhang-Leiste zeigt es an: „582.2 KB · verkleinert aus 4.8 MB". Wer sofort auf Senden klickt, laedt trotzdem die verkleinerte Fassung hoch, weil der Versand auf die Umrechnung wartet
- Fix: Schlaegt ein Anhang im Chat fehl, nennt die Meldung jetzt den echten Grund statt pauschal „Netzwerkfehler" — bei einer HTML-Antwort von einem Proxy davor also Statuscode und Herkunft

## [1.7.66] - 2026-08-28
- Feature: **Bilder werden vor dem Hochladen im Browser verkleinert.** Kamerafotos mit 2 bis 10 MB scheiterten an einer Groessengrenze im Proxy vor dem Add-on — die laesst sich von hier aus nicht anheben. Bilder werden jetzt auf hoechstens 1920 Pixel an der laengeren Kante gebracht und als JPEG auf rund 700 KB gedrueckt (Qualitaet stufenweise von 85 % abwaerts, nur so weit wie noetig). Ein Testfoto mit 4032x3024 und 4,8 MB geht damit als 582 KB raus
- Der Editor zeigt die Verkleinerung an: „Bild verkleinert: 4,8 MB → 582 KB (1920×1440 Pixel)". Kleine Bilder bleiben unangetastet, Videos lassen sich im Browser nicht verkleinern — ab 2 MB weist ein Hinweis darauf hin, dass grosse Uploads unterwegs abgewiesen werden koennen
- Bildvorlagen speichern ebenfalls die verkleinerte Fassung
- Die Obergrenze im Auswahldialog liegt jetzt bei 64 MB statt 16 MB — nach dem Verkleinern zaehlt sie nur noch fuer Videos

## [1.7.65] - 2026-08-28
- Diagnose: **„Unexpected token '<', "<!DOCTYPE "..." beim Bild-Status verriet nichts.** Im Add-on-Log taucht dazu kein einziger Eintrag auf — die Anfrage erreicht das Add-on also gar nicht, die HTML-Antwort kommt von einer Stelle davor (Ingress-Proxy). Der Status-Editor wertet Antworten jetzt so aus, dass er bei Nicht-JSON den echten Statuscode, den Inhaltstyp und den Anfang der Antwort anzeigt, bei Uploads zusaetzlich die Dateigroesse. Statt des Parser-Fehlers steht dort dann z.B. `HTTP 413 Payload Too Large [text/html] …`

## [1.7.64] - 2026-08-28
- Fix: **Bild-Status meldete „Unexpected token '<', "<!DOCTYPE "... is not valid JSON".** Fehler aus Middleware — etwa Multer bei einem abgelehnten Upload — liefen in Express' HTML-Fehlerseite, im Frontend kam davon nur der Parser-Fehler an, ohne jeden Hinweis auf die Ursache. Alle `/api/`-Pfade antworten jetzt auch im Fehlerfall mit JSON, und der Grund landet zusaetzlich als `[ERROR]` im Log
- Fix: **Vom Server abgelehnte Statusmeldungen (`ack = -1`) standen als „laufend" in der Liste.** Sie bleiben in der WhatsApp-Web-Sammlung liegen, sind aber nie bei jemandem angekommen — sie werden jetzt uebersprungen. Ebenso Eintraege mit gesetztem `revokeTimestamp`
- Hinweis: Eine auf dem Handy geloeschte Statusmeldung kann hier weiter auftauchen, solange WhatsApp Web die Loeschung nicht mitbekommen hat — die Rohdaten tragen dann keinerlei Kennzeichnung. Sie verschwindet spaetestens nach 24 Stunden von allein; der Papierkorb in der Liste raeumt sie sofort weg

## [1.7.63] - 2026-08-28
- Fix: **Auf dem Handy geloeschte Statusmeldungen standen weiter in „Meine laufenden Statusmeldungen".** Zurueckgezogene Eintraege (`type: revoked` bzw. `isRevoked`) werden jetzt uebersprungen, ebenso Eintraege, die aelter als 24 Stunden sind — ein Status laeuft nach dieser Zeit ohnehin ab
- `GET /api/my-status/diag` gibt jetzt die Rohfelder der eigenen Statusmeldungen aus (Typ, Zeitstempel, Ack und alle vorhandenen Feldnamen). Falls WhatsApp eine Loeschung anders kennzeichnet als erwartet, laesst sich der Filter daran ohne Raterei nachziehen
- `GET /api/my-status/diag?deep=1` durchsucht die geladenen WhatsApp-Web-Bundles nach dem Quelltext von `sendStatusTextMsgAction`. Der normale Weg ueber `toString()` zeigt nur den Babel-Mantel `function C(e,t){…}` — immerhin verraet der, dass die Aktion einen zweiten, von `whatsapp-web.js` nie genutzten Parameter hat (vermutlich fuer Link-Vorschauen)

## [1.7.62] - 2026-08-28
- Fix: **„Meine laufenden Statusmeldungen" blieb leer, obwohl der Status auf dem Handy zu sehen war.** WhatsApp fuehrt den eigenen Status unter der LID des Kontos (`…@lid`), abgefragt wurde er unter der Rufnummer (`…@c.us`). Die richtige ID kommt jetzt aus `Status.getMyStatus()`, die Rufnummer bleibt als Rueckfall
- Neu: `GET /api/my-status/diag` meldet, welche Felder die WhatsApp-Status-Aktionen annehmen, die Status-Feature-Schalter des Kontos und unter welcher ID der eigene Status laeuft — Grundlage fuer weitere Statusfunktionen, ohne im Trueben zu fischen
- Die ausfuehrliche Rueckmeldung der Sendeaktion steht jetzt nur noch im Debug-Log statt bei jedem Statusversand im normalen Log

## [1.7.61] - 2026-08-28
- Fix: **Text-Status wurde als gesendet gemeldet, erschien aber auf keinem Geraet.** Das Log zeigte `message_ack: true_status@broadcast_… → -1` — der WhatsApp-Server lehnte die Nachricht ab. Ursache: `whatsapp-web.js` baut fuer Status ein eigenes Msg-Modell samt Absender-Identitaet (bei LID-Konten die falsche), uebergibt der WhatsApp-Aktion `sendStatusTextMsgAction` aber ohnehin nur `{ color, font, text }` und wirft deren Rueckgabewert weg. Text-Status geht jetzt direkt an diese Aktion, WhatsApp baut die Nachricht selbst — und ihr Ergebnis landet im Log. Fehlt die Aktion (kuenftige Umbenennung), greift weiterhin der Bibliotheksweg
- Fix: Ein abgelehnter Status (`ack = -1`) wird jetzt als Warnung geloggt statt nur als Debug-Zeile. Vorher sah ein fehlgeschlagener Versand von aussen wie ein Erfolg aus

## [1.7.60] - 2026-08-28
- Fix: **Status-Versand brach mit `canCheckStatusRankingPosterGating is not a function` ab.** `whatsapp-web.js` ruft beim Posten eines Status `window.require('WAWebStatusGatingUtils').canCheckStatusRankingPosterGating()` auf — in aktuellen WhatsApp-Web-Versionen gibt es diese Funktion nicht mehr, und der Versand scheiterte sowohl bei Text- als auch bei Bild-Status. Vor jedem Statusversand wird `window.require` jetzt fuer genau dieses Modul umhuellt und die fehlende Funktion ergaenzt (Ergebnis `false`, entspricht dem Normalfall ohne Gating-Pruefung). Andere Module bleiben unberuehrt, der Eingriff ist idempotent und wird nach einem Reconnect erneut gesetzt. Beim ersten Mal landet eine Warnung mit den tatsaechlich vorhandenen Modul-Exporten im Log

## [1.7.59] - 2026-08-28
- Feature: **Eigene Statusmeldungen senden.** Im Reiter „Kontakte" steht ganz oben ein neuer Eintrag „Mein Profil". Ein Klick öffnet einen Status-Editor mit vier Reitern:
  - **Text** — Text schreiben, Hintergrundfarbe aus 15 Vorschlägen oder frei per Farbwähler, eine von acht WhatsApp-Schriften, mit Live-Vorschau
  - **Bild / Video** — Datei hochladen (max. 16 MB), Vorschau, optionaler Text zum Bild
  - **Vorlagen** — Entwürfe mit Namen speichern, später laden, ändern und löschen; eine Vorlage merkt sich Text, Farbe, Schrift und – bei Bildvorlagen – die Bilddatei
  - **Profil** — Info-Text des Profils bearbeiten und die eigenen laufenden Statusmeldungen sehen und einzeln zurückziehen
- Feature: Neue REST-Endpunkte `GET /api/me`, `POST /api/me/about`, `GET /api/my-status`, `POST /api/my-status/text`, `POST /api/my-status/media`, `POST /api/my-status/revoke` sowie `GET/POST /api/status-templates` und `POST /api/status-templates/:id/delete` — damit lassen sich Statusmeldungen auch aus Home-Assistant-Automationen heraus posten
- Vorlagen liegen in `/config/status_templates.json`, Vorlagenbilder in `/config/status_templates/`

## [1.7.58] - 2026-08-25
- Fix: **Stille Verbindungsabbrüche fielen bis zu 10 Minuten lang nicht auf.** Der Keep-alive prüfte `client.getState()` nur alle 600 Sekunden — bis dahin meldete `/api/status` weiter `connected`, das MessengerPortal zeigte grün „Online" und Sendeversuche liefen ins Leere. Intervall auf 60 Sekunden verkürzt
- Fix: `client.getState()` lief ohne Timeout. Bei eingefrorenem Puppeteer kehrte der Aufruf nie zurück, der Keep-alive-Durchlauf endete nie und der Ausfall blieb dauerhaft unbemerkt. Jetzt bricht ein `Promise.race` nach 30 Sekunden ab und löst einen Reconnect aus
- Fix: **Nach einem fehlgeschlagenen Reconnect blieb das Add-on für immer auf `error` stehen.** Scheiterte `client.initialize()`, versuchte es nichts mehr — nur ein Add-on-Neustart half. Neuer Auto-Retry-Timer verbindet aus `error` und `disconnected` heraus mit exponentiellem Backoff neu (15 s, 30 s, 60 s … max. 5 Minuten) und setzt den Backoff nach Erfolg zurück. `waiting_for_scan` und `auth_failed` werden bewusst nicht wiederholt — dort muss der Nutzer den QR-Code scannen
- Fix: Blieb ein Reconnect selbst hängen (`initialize()` kehrt nie zurück), sperrte das `_reconnecting`-Flag jeden weiteren Versuch dauerhaft. Ein Watchdog hebt die Sperre nach 3 Minuten wieder auf

## [1.7.57] - 2026-08-25
- Security: CodeQL-Alert #208 (`js/polynomial-redos`, high) — `chatId.replace(/@.*$/, '')` in `resolveArchiveName()` läuft auf Werten aus `req.params`, und `@.*$` braucht bei vielen `@` polynomiale Zeit (ReDoS-Risiko über einen präparierten Chat-Parameter). Alle sechs Vorkommen dieses Musters durch `split('@')[0]` ersetzt — gleiches Ergebnis in allen Fällen (mehrere `@`, kein `@`, leerer String), aber garantiert lineare Laufzeit

## [1.7.56] - 2026-08-24
- Fix: **Jeder Kontakt stand doppelt in der Liste** (285 Einträge statt 142) — WhatsApp liefert zu jeder Person mehrere Contact-Objekte mit derselben `@c.us`-ID; in 1.7.54 war der Dedupe-Schlüssel von der ID auf die Rufnummer umgestellt worden, und weil eines der Objekte die LID im Feld `number` trägt, entstanden zwei Schlüssel pro Person. Dedupliziert wird wieder über die ID; bei mehreren Objekten gewinnt das mit brauchbarer Rufnummer
- Fix: **Angezeigte Nummern waren zum Teil LIDs** (`+69050273165504`, `+5858385784864`) — `contact.number` enthält seit der LID-Umstellung oft die LID statt der Rufnummer. Neuer Helfer `contactNumber()` nimmt bei `@c.us` den Teil vor dem `@` (das ist per Definition die Rufnummer), akzeptiert nur 7–15 Ziffern und verwirft alles, was der LID der ID entspricht; `contact.number` dient nur noch als Rückfall. Greift auch in `resolveChatNumbers()` und beim Laden der Chats, sodass die Nummer unter dem Chatnamen stimmt oder fehlt, statt falsch zu sein
- Getestet gegen die echten Live-Rohdaten des Add-ons: 285 Objekte ergeben 142 Kontakte, alle Nummern 11–13 Stellen, keine einzige LID-artige (≥14 Stellen) mehr; aufgelöster LID-Chat liefert die Rufnummer, ein unaufgelöster liefert leer statt falsch

## [1.7.55] - 2026-08-24
- Fix: **Unter dem Chatnamen stand eine erfundene Nummer wie „+127…"** — dieselbe Ursache wie 1.7.54: `chat.id.user` ist bei `@lid`-Chats die interne LID (13–18 Stellen), nicht die Rufnummer, wurde aber als `phone` gespeichert und angezeigt. Neuer Helfer `phoneForChat()` lässt eine LID nie als Rufnummer durch: entweder die über `getContactById()` aufgelöste echte Nummer oder gar keine. `upsertChat()` korrigiert bereits gespeicherte LID-Nummern, löscht eine gültige Nummer aber nie (nach einem Neustart ist der Auflösungs-Cache leer, die Nummer aus `chats.json` trotzdem richtig)
- Neu: Die Auflösung läuft jetzt von selbst, nicht erst beim Öffnen des Kontakte-Tabs: Der Start-Handler nimmt die Nummer aus dem ohnehin geholten Kontakt mit, und `/api/chats` stößt offene LID-Auflösungen im Hintergrund an (mit Reentranz-Schutz, No-op sobald alles bekannt ist). Korrigierte Nummern landen in `chats.json`
- Getestet: Unit-Test über `phoneForChat()`/`upsertChat()` mit den echten ID-Formaten — LID ohne Auflösung ergibt keine Nummer, mit Auflösung die richtige, gespeicherte Nummern überleben den Neustart, alte LID-Nummern werden ersetzt

## [1.7.54] - 2026-08-24
- Fix: **Im Kontakte-Tab stand bei praktisch allen Einträgen „noch kein Chat"** — WhatsApp führt Chats inzwischen unter `@lid`-IDs (hier 49 von 53), das Adressbuch dagegen unter `@c.us`. Die Zahl vor dem `@` ist bei `@lid` eine interne LID und keine Rufnummer, deshalb passte weder ID noch Nummer zusammen und `hasChat` war fast immer `false` (an den Live-Daten nachgemessen: 1 von 142 Kontakten wurde erkannt). Neuer `resolveChatNumbers()` löst die LID pro Chat einmalig über `client.getContactById()` zur Rufnummer auf und merkt sie sich; `buildChatIndex()` legt Chat-ID, Rufnummer und `phone` als Schlüssel auf die Chat-ID. Ergebnis mit denselben Daten gegengeprüft: 44 von 50 Einzelchats werden jetzt zugeordnet — die übrigen 6 sind Chats mit Leuten, die gar nicht im Adressbuch stehen
- Fix: `hasChat` wird nicht mehr mit der 5-Minuten-Cache-Antwort eingefroren, sondern bei jedem Aufruf frisch bestimmt. Sonst blieb ein direkt nach dem Start geöffneter Kontakte-Tab minutenlang bei „noch kein Chat", weil `chatMap` in dem Moment noch leer war
- Neu: Jeder Kontakt trägt jetzt `chatId` (die zugehörige Chat-ID oder `null`). Ein Klick öffnet damit den echten Chat inklusive Verlauf statt einer leeren Ansicht unter der falschen ID
- Neu: Die Logzeile beim Laden des Adressbuchs nennt die ID-Formate (`@c.us`/`@lid`), die Trefferzahl und die Größe des Chat-Index — damit lässt sich so eine Format-Umstellung künftig direkt am Log ablesen

## [1.7.53] - 2026-08-24
- Fix: **Kopfleiste lief auf dem Handy rechts aus dem Bild** — mit dem neuen Archiv-Button passten die Schaltflächen nicht mehr in eine Zeile, Flexbox quetschte sie zusammen und die letzten (Abmelden, Scroll-Buttons) waren nicht erreichbar. Unter 768 px ist die Leiste jetzt horizontal scrollbar (`overflow-x:auto`, `flex-shrink:0` auf allen Elementen, damit gescrollt statt gestaucht wird; Scrollbalken ausgeblendet). Buttons und Speicheranzeige sind dort außerdem etwas kompakter
- Neu: Weicher Verlauf am rechten Rand der Leiste, solange noch etwas außerhalb liegt (`updateTopbarFade()` bei Scroll, Resize und nach dem Verbinden) — verschwindet, sobald ans Ende gescrollt wurde
- Getestet mit Playwright bei 360/390/768/1200 px: unter 768 px scrollt die Leiste und der letzte Button wird erreichbar, ab 768 px unverändert ohne Scroll; im geöffneten Chat (Titel und Status ausgeblendet) passt weiterhin alles ohne Scroll

## [1.7.52] - 2026-08-24
- Fix: **Web-UI startete nicht mehr** (`Uncaught SyntaxError: Invalid regular expression: /^+/: Nothing to repeat`, Ingress-Seite blieb leer) — der Nummernfilter der neuen Kontaktliste war als `/^\+/` geschrieben. Der gesamte Client-Code steckt in einem Template-Literal in `server.js`, und darin ist `\+` kein bekanntes Escape: der Backslash fällt beim Ausliefern weg, im Browser kam `/^+/` an und das Skript brach komplett ab. Filter nutzt jetzt `q.startsWith('+') ? q.slice(1) : q` statt einer Regex
- Fix: Aus demselben Grund war die Rufnummer unter dem Chatnamen faktisch nie sichtbar — `/^\d{7,15}$/` in `openChat()` kam im Browser als `/^d{7,15}$/` an und traf nur den Literaltext „ddddddd". Backslash verdoppelt; die Nummer erscheint jetzt wieder in der Kopfzeile des Chats
- Intern: Test-Harness bildet die Escape-Regeln des Template-Literals jetzt exakt nach und prüft das tatsächlich ausgelieferte Client-Skript mit `node --check`; der bisherige Harness hatte den Backslash zu früh aufgelöst und den Fehler dadurch nicht gesehen

## [1.7.51] - 2026-08-24
- Neu: **Tab „Kontakte" in der Seitenleiste** — zeigt das komplette WhatsApp-Adressbuch, also auch Kontakte ohne (mehr) Chatverlauf, die in der Chatliste naturgemäß fehlen. Zeile zeigt Name, Rufnummer und bei fehlendem Verlauf den Hinweis „noch kein Chat"; ein Klick öffnet den (leeren) Chat, sodass man direkt schreiben kann. Existiert bereits ein Chat, wird dessen echtes Chat-Objekt geöffnet (Ungelesen-Markierung, Zeitstempel bleiben korrekt). Die Suchleiste filtert hier nach Name **und** Nummer, die Fußzeile nennt Gesamtzahl und Anzahl ohne Chat und bietet „↻ Adressbuch neu laden"
- Neu: Endpoint `GET /api/contacts` — liefert `id`, `name`, `number`, `hasChat` für alle Adressbuch-Kontakte (`isMyContact`), Gruppen/Broadcasts/Channels gefiltert, Doppel-Einträge über `@c.us`/`@lid` nach Nummer dedupliziert. `client.getContacts()` ist teuer, daher 5-Minuten-Cache; `?refresh=1` erzwingt den Neuaufbau
- Intern: `renderChatList()` delegiert im Kontakte-Tab an `renderContactList()`, damit die 5-Sekunden-Poll-Updates die Adressbuch-Ansicht nicht überschreiben

## [1.7.50] - 2026-08-24
- Fix: **Archiv-Übersicht zeigte bei manchen Kontakten nur die Rufnummer statt des Namens** — die Namen kamen bisher ausschließlich aus `chatMap`, und die kennt nur Kontakte mit echtem Chatverlauf. Wer nur Statusmeldungen postet (oder wo der Chat gelöscht bzw. sehr alt ist), stand deshalb als nackte Nummer da, obwohl der Kontakt im Telefonadressbuch steht. Neuer Helfer `resolveArchiveName()` fragt in diesem Fall über `client.getContactById()` den gespeicherten Namen (bzw. `shortName`/`pushname`) ab und merkt ihn sich im Cache; greift auch für den Titel der Export-ZIP. Konnte nicht aufgelöst werden (keine Verbindung, unbekannter Kontakt), bleibt die Nummer stehen und wird beim nächsten Aufruf erneut versucht
- Neu: In der Übersicht steht die Rufnummer als Unterzeile unter dem Namen, sofern beide sich unterscheiden — erleichtert das Zuordnen bei mehreren gleichnamigen Kontakten

## [1.7.49] - 2026-08-24
- Neu: **Gesamtübersicht über alle Status-Archive** — neuer Button (Archiv-Symbol) in der Kopfzeile öffnet eine Tabelle mit allen Kontakten, die archivierte Statusmeldungen haben: Anzahl Einträge (davon abgelaufen bzw. ohne Medium), belegter Speicher, Zeitraum. Spalten sind per Klick auf die Überschrift sortierbar (Standard: größter Speicherbedarf oben), pro Zeile lässt sich das Archiv öffnen, als ZIP exportieren oder löschen; die Fußzeile zeigt die Summe über alle Kontakte und bietet „Alle Archive leeren". Bisher war der Speicherbedarf nur kontaktweise über das Kontakt-Fenster sichtbar
- Neu: Endpoints `GET /api/status-archive-overview` (Kontakt, Anzahl, Bytes, ältester/neuester Eintrag; 10 s Cache, da der Scan pro Mediendatei ein `statSync` macht) und `POST /api/status-archive-clear-bulk` (leert die Archive der übergebenen `chatIds`, ohne Angabe alle). Die Löschlogik aus `/api/status-archive/:chatId/clear` liegt jetzt in `clearArchiveForChat()` und meldet freigewordene Dateien und Bytes zurück

## [1.7.48] - 2026-08-13
- Neu: **Gesendete Nachrichten erscheinen sofort in der Chat-Ansicht** (optimistisches Rendern). Bisher wurde die Bubble erst gezeichnet, nachdem `client.sendMessage()` den WhatsApp-Web-Roundtrip abgeschlossen hatte und der nächste Poll lief — je nach Verbindung mehrere Sekunden Verzögerung. Jetzt legt `sendMsg()` die Bubble direkt beim Absenden an: ausgegraut (`.bubble-wrap.pending`, 55 % Deckkraft) mit 🕓 statt Häkchen, Eingabefeld wird sofort geleert. Sobald der Server den Versand bestätigt, bekommt der Wrap die echte Message-ID, die Ausgrauung verschwindet und das ✓ erscheint — die Dedupe-Prüfung in `renderMessages()` verhindert dabei eine zweite Bubble aus dem Poll. Schlägt der Versand fehl oder bricht das Netz weg, wird der Platzhalter entfernt und der Text zurück ins Eingabefeld geschrieben. Gilt für normale Nachrichten und Antworten (inkl. Zitat-Block); Medienversand bleibt unverändert

## [1.7.47.1] - 2026-08-09

chore(deps): bump js-yaml from 4.3.0 to 4.3.1 in /whatsapp


## [1.7.47] - 2026-07-31
- Neu: **„🧹 Fehlerhafte aufräumen"-Button im Status-Archiv-Fenster** — neuer Endpoint `POST /api/status-archive/:chatId/cleanup` entfernt dauerhaft nur die Einträge ohne ladbares Medium (kein `mediaFile` oder Datei nicht mehr auf Platte). Hat der Eintrag eine Bildunterschrift, wird er zu einem reinen Text-Eintrag statt gelöscht. Danach stimmen Badge-Zähler und tatsächlich angezeigte Kacheln wieder überein — im Gegensatz zu „Archiv leeren" bleibt der Rest der Historie erhalten

## [1.7.46] - 2026-07-31
- Fix: Platzhalter-Text aus 1.7.45 („Medien-Download war deaktiviert") behauptete fälschlich eine Ursache — Option `download_media` war beim Nutzer durchgehend aktiv, Fehlschlag lag am eigentlichen Download (abgelaufener Status, Netzwerkfehler o.ä.), nicht an der Einstellung. Text auf neutral „Medium nicht verfügbar" geändert (analog zur Export-ZIP-Formulierung „Datei nicht mehr vorhanden"), zusätzlich Debug-Log in `captureStatuses()` ergänzt, um künftig die tatsächliche Ursache (kein `hasMedia` vs. Downloadfehler) unterscheiden zu können

## [1.7.45] - 2026-07-31
- Security: CodeQL/Dependabot-Alert #37 (`brace-expansion` <=5.0.7, GHSA-mh99-v99m-4gvg, DoS via unbounded expansion length) — transitiv über `archiver` → `glob`/`readdir-glob` → `minimatch@9.0.9`/`5.1.9`, die beide noch die alte `brace-expansion@2.x`-API referenzierten. Direktes Überschreiben von `brace-expansion` auf `^5.0.8` brach `minimatch` (API-Bruch: `brace-expansion@5` hat keinen CJS-Default-Export mehr, nur noch named `expand`). Stattdessen `overrides.minimatch: "^10.2.2"` gesetzt — diese Minimatch-Version deklariert bereits `brace-expansion@^5.0.8` korrekt, dedupliziert alle Pfade auf `minimatch@10.2.6`/`brace-expansion@5.0.9`. `npm audit` danach 0 Findings, minimatch/glob/archiver funktional gegengetestet (Brace-Pattern-Match, Glob, ZIP-Erstellung)
- Fix: **Status-Archiv zeigte weniger Bilder im Grid als der „N abgelaufene Statusmeldungen"-Button meldete** — Ursache: Foto-/Video-Status ohne `mediaFile` (typisch wenn `download_media` zum Erfassungszeitpunkt aus war) wurden von `renderArchiveItem()` im Web-UI-Grid komplett übersprungen (leerer String), zählten aber weiterhin in `sd.msgs.length` fürs Badge mit. Die Export-ZIP-Route hatte für exakt diesen Fall schon einen Platzhalter-Text — das Web-UI-Grid jetzt ebenso: zeigt „📷/📹 Medien-Download war deaktiviert" statt den Eintrag stillschweigend zu verschlucken

## [1.7.44] - 2026-07-31
- map: `addon_config` → `app_config` (Home-Assistant-Supervisor hat `addon_config` seit 2026.07 als Legacy-Name markiert, neuer Name ist `app_config`).

## [1.7.43] - 2026-07-30
- Fix: Abhängigkeit von `carlosalaniz/whatsapp-web.js` (Stand vor der `id._serialized`→`id.$1`-Umbenennung durch WhatsApp, siehe 1.7.41) auf `lindionez/whatsapp-web.js#3733802` gewechselt — aktiv gepflegter Fork, der genau diesen Fix ("fix(client): add fallback for WhatsApp id._serialized renamed to id.$1", 2026-07-15) sowie weitere aktuelle Community-Fixes (Duplicate-Ready-Events bei SPA-Re-Injection, Big-File-Streaming-Downloads) schneller übernimmt als der offizielle Upstream

## [1.7.42] - 2026-07-26
- Fix: **Eigene Reaktion (❤️👍…) im Web-UI unsichtbar**, kam aber korrekt aufs Handy an — `/api/react` sendete die Reaktion nur an WhatsApp (`msg.react()`) und trug sie in `myReactions` ein, aber nicht in `msg.reactions`/`reactionsCache` (das, was `/api/reactions/:chatId` fürs Web-UI ausliest). Das passierte bisher nur über das `message_reaction`-Echo-Event der Lib — das aktuelle `whatsapp-web.js` emittiert dieses Event für **eigene** Reaktionen offenbar nicht mehr zuverlässig. Reaktions-Logik in gemeinsame Funktion `recordReaction()` ausgelagert, `/api/react` wendet die eigene Reaktion jetzt sofort lokal an, statt aufs Echo zu warten

## [1.7.41] - 2026-07-25
- Fix: **Nachrichten senden schlug erneut mit 500 fehl** (`sendMessage returned no result`) — WhatsApp hat im Juli-2026-Update die Nachrichten-ID-Property `_serialized` in `$1` umbenannt. `whatsapp-web.js@1.34.7` (aus v1.7.40) kennt das noch nicht: `sendMessage` lieferte serverseitig `undefined` statt eines Message-Objekts, obwohl die Nachricht beim Empfänger tatsächlich ankam (Bug ausschließlich im Rückgabewert der Library, nicht in der eigentlichen Zustellung). Betraf ausnahmslos jeden Chat. Offizieller Fix noch nicht auf npm veröffentlicht (mehrere offene, ungeprüfte Community-PRs im Upstream-Repo, Maintainer-Merge steht seit Wochen aus) — Abhängigkeit übergangsweise auf einen einzelnen geprüften Commit eines Community-Forks gepinnt (`carlosalaniz/whatsapp-web.js#5b6bb00`, minimaler Diff nur in `Injected/Utils.js`, manuell auf unerwünschten Code geprüft), bis der offizielle Fix released ist

## [1.7.40] - 2026-07-25
- Fix: **Nachrichten senden schlug mit 500 fehl** (`Cannot set properties of undefined (setting '__logged')`) — WhatsApp rollt `@lid`-IDs aus (versteckte Telefonnummern in Gruppen), die alte `whatsapp-web.js@1.26.0` konnte damit nicht umgehen und lieferte bei `sendMessage`/`.reply()` teils `undefined` statt eines Ergebnisses zurück. Abhängigkeit auf `^1.34.7` angehoben (aktuelle Version mit lid-Unterstützung), zusätzlich Null-Checks nach `sendMessage`/`.reply()` ergänzt, damit bei künftigen Fehlschlägen ein sauberer 500 mit Fehlermeldung statt ein Crash kommt

## [1.7.39] - 2026-07-09
- Fix: **Add-on beendete sich bei jedem Stop/Update mit Exit-Code 137/143** statt sauber mit 0 — `Dockerfile` basiert auf `node:lts-alpine` ohne eigenes Init-System, `run.sh` macht den Node-Prozess per `exec` zu PID 1. Ohne eigenen Signal-Handler ignoriert der Kernel bei PID 1 unbehandelte Signale wie SIGTERM, der Supervisor musste nach Timeout hart per SIGKILL beenden (137). `init: false` → `init: true` in `config.yaml` sorgt für ein echtes Mini-Init als PID 1, das Signale korrekt durchreicht — zusätzlich neuer `SIGTERM`/`SIGINT`-Handler in `server.js`, der vor dem Exit sauber `client.destroy()` aufruft (nicht `client.logout()`!), damit Puppeteer/Chromium ordentlich geschlossen wird statt mitten im Betrieb gekillt zu werden. Das verhinderte bisher schon mal korrupte Chromium-Profile (`SingletonLock` u. Ä. im Session-Ordner) und im schlimmsten Fall einen erzwungenen erneuten QR-Scan beim nächsten Start

## [1.7.38] - 2026-07-06
- Fix: **UI blieb nach Update gelegentlich hängen** (Senden von Text/Bild ging nicht mehr, nur Hard-Refresh half) — Root-Route `/` lieferte keinen `Cache-Control`-Header, wodurch Browser/Ingress veraltetes Frontend-JS zwischenspeichern konnten. Jetzt `Cache-Control: no-store` gesetzt

## [1.7.37] - 2026-07-04
- Fix: **ZIP-Export lieferte 500** (`TypeError: archiver is not a function`) — `archiver@8.0.0` (npm `latest`) hat die klassische Aufruf-API (`archiver('zip', opts)`) entfernt und exportiert jetzt stattdessen Klassen (`Archiver`, `ZipArchive`, …). Abhängigkeit auf `^7.0.1` gepinnt, wo die im Code verwendete API noch funktioniert. Diesmal lokal tatsächlich ausgeführt (nicht nur `node --check`) — echter Testlauf mit `archiver@7.0.1` erzeugt eine valide ZIP ohne Fehler

## [1.7.36] - 2026-07-04
- Neu: **Status-Archiv als ZIP exportieren** — im Archiv-Fenster gibt's jetzt „⬇ Als ZIP exportieren" (`GET /api/status-archive/:chatId/export`, neue Abhängigkeit `archiver`). Enthält alle Fotos/Videos als echte Dateien (chronologisch nummeriert und mit Zeitstempel benannt) plus eine `archiv.html`, die alle Einträge inkl. Text und Medien-Vorschau als kleine Galerie zeigt (relative Pfade in die mitgepackten Dateien, kein Base64-Aufblähen)

## [1.7.35] - 2026-07-04
- Fix: **Archiv zeigte auch Status <24h**, die noch gar nicht abgelaufen waren und in der Live-Sektion parallel auftauchten. `GET /api/status-archive/:chatId` filtert jetzt Einträge raus, die jünger als 24h sind
- Neu: **Archiv öffnet in eigenem, größerem Fenster** statt im winzigen Profil-Popup — dort steht jetzt nur noch ein Button „🗄 N abgelaufene Statusmeldung(en) ansehen", der ein separates Modal mit Grid-Layout (mehrspaltig, bis zu 640px breit, 82vh hoch) öffnet, „Archiv leeren" liegt jetzt im Kopf dieses Fensters
- Entfernt: `check-frontend-syntax.js` wurde wieder aus dem Repo genommen (CodeQL meldete Findings auf dem Dev-Tool-Skript) — Prüfung läuft ab jetzt nur noch lokal/manuell, nicht mehr als committetes Skript

## [1.7.34] - 2026-07-04
- Fix: **UI blieb erneut bei „Verbinde mit WhatsApp…" hängen**, gleiche Ursache wie 1.7.33 an anderer Stelle — der „Archiv leeren"-Button baute sein `onclick`-Attribut per String-Verkettung mit escapten Anführungszeichen (`\'`), die vom äußeren Template-String in `server.js` verschluckt wurden und im Browser zu `Uncaught SyntaxError: Unexpected string` führten. Behoben durch Verzicht auf inline-`onclick` mit eingebetteten Werten — der Button bekommt seinen Klick-Handler jetzt per `addEventListener` (gleiches Muster wie die Lightbox-Klicks direkt daneben), keine Anführungszeichen-Verschachtelung mehr nötig
- Neu: Test-Skript, das den kompletten eingebetteten Frontend-`<script>`-Block aus `server.js` extrahiert und mit `node --check` prüft (`node --check` allein sieht nur `server.js` als Ganzes, nicht den Inhalt des Template-Strings) — wird ab jetzt vor jedem Push geprüft, der den Web-UI-Code ändert

## [1.7.33] - 2026-07-04
- Fix: **UI blieb dauerhaft bei „Verbinde mit WhatsApp…" hängen** — der englische Text für `archiveClearConfirm` enthielt ein escaptes Apostroph (`contact\'s`). Da der komplette Web-UI-Code in `server.js` selbst in einem JS-Template-String steckt, frisst dessen äußeres Escaping das `\'` weg, bevor es den Browser erreicht — im Browser blieb ein unescaptes `'` mitten im String übrig, was den kompletten eingebetteten `<script>`-Block zum Absturz brachte (`Uncaught SyntaxError: Unexpected identifier 's'`), noch bevor der Status-Poll überhaupt laufen konnte. Text umformuliert, keine Apostrophe mehr in eingebetteten UI-Strings

## [1.7.32] - 2026-07-04
- Fix: `captureStatuses()` (Status-Archiv-Hintergrund-Job) loggte bisher nichts sichtbar — Erfolg gar nicht, Fehler nur im Debug-Modus. Jetzt `[INFO]`-Zeile im normalen Log, wenn neue Statusmeldungen archiviert wurden, und `[WARN]` bei Fehlern (z.B. `getBroadcasts()` schlägt fehl)

## [1.7.31] - 2026-07-04
- Neu: **Status-Archiv pro Kontakt** — abgelaufene Statusmeldungen (WhatsApp löscht sie nach 24h) bleiben jetzt dauerhaft im Profil-Popup sichtbar (Datum/Uhrzeit inklusive), solange die Add-on-Option **„Gelöschte Nachrichten behalten"** aktiv ist. Ein Hintergrund-Job (`captureStatuses()`, alle 15 Min. + sofort nach Verbindungsaufbau) sammelt neue Status aller Kontakte über `client.getBroadcasts()` ein und speichert sie in `/config/status_archive.json`. Pro Kontakt gibt's einen „🗑 Archiv leeren"-Button. `api/cleanup-media` (verwaiste Mediendateien löschen) berücksichtigt archivierte Medien jetzt ebenfalls, damit sie dabei nicht versehentlich gelöscht werden
  - Bekannte Grenze: ein Status, der innerhalb der 15-Minuten-Lücke gepostet und wieder gelöscht wird, kann verpasst werden
  - Kein Größenlimit auf `status_archive.json` selbst (bewusst, da unbegrenzte Aufbewahrung gewünscht) — nur die Mediendateien unterliegen wie gehabt dem Speicherlimit

## [1.7.30] - 2026-07-04
- Neu: **Status-Ring in der Kontaktliste** — Kontakte mit aktiven Statusmeldungen bekommen einen pulsierenden grünen Ring ums Profilbild. Neuer Endpoint `GET /api/statuses-available` (`client.getBroadcasts()`) wird alle 30s abgefragt, direkt nach Verbindungsaufbau einmal sofort

## [1.7.29] - 2026-07-04
- Neu: **Statusmeldungen von Kontakten ansehen** — im Profil-Popup (Klick auf Profilbild im Chat) werden jetzt die aktuellen WhatsApp-Status-Updates des Kontakts angezeigt (Text, Foto, Video mit Zeitpunkt). Nutzt `client.getBroadcastById()` aus whatsapp-web.js über neuen Endpoint `GET /api/status/:chatId`. Medien respektieren den bestehenden „Medien AN/AUS"-Schalter. Rein lesend — kein eigenes Senden von Status, keine sonstigen Änderungen am Popup

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
