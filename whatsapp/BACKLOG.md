# Backlog — WhatsApp

Ideen, die nicht dringend sind. Kein Zeitplan.

Die Liste entstand aus einer Durchsicht des Add-ons am 28.08.2026. Vier
kleinere Befunde derselben Durchsicht sind mit 1.8.29 erledigt: die wirkungslose
Option `ha_notifications_skip_groups`, der nicht gespeicherte Spam-Löschvorgang,
`npm ci` statt `npm install` im Bau und die Port-Verwechslung in Testskript und
Doku. Was hier steht, ist der Rest — größer, riskanter oder mit einer
Entscheidung verbunden.

## REST-API ohne Authentifizierung

`app.listen(PORT)` am Ende von `server.js` bindet ohne Host-Angabe, also an alle
Schnittstellen, und `config.yaml` veröffentlicht `17776/tcp` per Vorgabe. Es gibt
keine Prüfung von Anmeldedaten — nur `mutatingRateLimit` (200 Anfragen pro
Minute) auf allem, was nicht GET ist. Wer im erreichbaren Netz steht, kann damit
Chats lesen, Nachrichten senden, Kontakte sperren, Datenschutzeinstellungen
ändern und über `/api/logout` bzw. `/api/reset` die Sitzung wegwerfen.

Der Ingress läuft auf demselben Port. Er ist also nicht der Schutzweg, sondern
nur ein zweiter Zugang — der veröffentlichte Host-Port umgeht die
Supervisor-Anmeldung vollständig.

Der kleine Schritt ist `ports: 17776/tcp: null` als Vorgabe: Home Assistant
zeigt den Port dann weiter in der Oberfläche an, veröffentlicht ihn aber erst,
wenn man ihn dort einträgt. Kostet nichts und schließt den Normalfall.

Der größere Schritt ist eine Option `api_token`: gesetzt, verlangt jede
`/api/`-Route einen `Authorization: Bearer`-Kopf; leer, bleibt alles wie
bisher. Ingress-Anfragen erkennt man am Kopf `X-Ingress-Path` und lässt sie
durch, sonst wäre die eigene Oberfläche ausgesperrt. Vergleich mit einem festen
Wert per `crypto.timingSafeEqual`, nicht mit `===`.

Beides zusammen bricht bestehende Automatisierungen, die den Port direkt
ansprechen. Deshalb gehört in DOCS/README ein Abschnitt, der beschreibt, wie man
den Port wieder öffnet und den Token einträgt — und die `curl`-Beispiele sowie
`test-api.ps1` brauchen dann den Kopf.

## Webhook-Adresse steht im Log

`server.js` gibt beim Start die vollständige `WEBHOOK_INCOMING`-Adresse aus.
Webhook-Adressen tragen ihr Geheimnis üblicherweise im Pfad oder in der
Abfrage — bei ntfy, Discord, Slack und HA-Webhooks ist genau das der Schlüssel.

Verschärfend: `console.log` ist umgeleitet und schreibt in `_logBuffer`, und
`GET /api/logs` gibt diesen Puffer ohne jede Prüfung heraus. Solange der
vorige Punkt offen ist, ist das Geheimnis damit netzweit abrufbar.

Die Behebung ist ein Einzeiler — statt der Adresse nur `new URL(WEBHOOK).origin`
ausgeben, oder schlicht `gesetzt`/`nicht gesetzt`. Hängt trotzdem hier im
Backlog, weil der Puffer noch andere Stellen enthalten kann, die eine Durchsicht
verdienen: `_logSilent`-Zeilen protokollieren Absender, Chat-Kennungen und die
ersten 60 Zeichen jeder eingehenden Nachricht, sobald `debug_mode` an ist.
Sinnvoll wäre, `/api/logs` an dieselbe Prüfung zu hängen wie den Rest.

## Verlauf wird als eine Datei geschrieben

`saveMsgs()` schreibt bei jeder Änderung — entprellt auf drei Sekunden — die
komplette `messages.json` neu, synchron und ohne Größengrenze. Dasselbe Muster
in `saveReactions()`, `saveStatusArchive()` und den übrigen Speicherfunktionen.
Mit wachsendem Verlauf steigen Blockierzeit und Schreiblast; bricht der Vorgang
mitten in `writeFileSync` ab, ist die ganze Datei hin, nicht nur der letzte
Eintrag.

Dazu kommt eine Lücke am Ende: `gracefulShutdown()` ruft `client.destroy()` und
danach `process.exit(0)`, ohne den offenen Drei-Sekunden-Zeitgeber abzufeuern.
Alles, was in den letzten drei Sekunden vor einem SIGTERM passiert ist, geht
verloren — bei einem Add-on-Update also regelmäßig.

Reihenfolge, wenn es angegangen wird:

1. **Abschluss beim Beenden.** In `gracefulShutdown()` die offenen Zeitgeber
   löschen und einmal synchron schreiben. Kleinster Schritt, sofort wirksam.
2. **Atomar schreiben.** In `<datei>.tmp` schreiben, dann `fs.renameSync` —
   auf demselben Dateisystem ist das unteilbar, ein Abbruch lässt die alte
   Fassung stehen.
3. **Aufbewahrungsgrenze.** Pro Chat auf eine Obergrenze kappen, als Option mit
   sicherer Vorgabe. Nicht hart verdrahten.
4. **SQLite.** Erst sinnvoll, wenn 1–3 nicht reichen. Bedeutet eine Migration
   der bestehenden JSON-Dateien und berührt jede Lesestelle.

## AppArmor-Profil ist sehr weit

`apparmor.txt` enthält in Zeile 12 ein pauschales `file,` — das erlaubt jeden
Dateizugriff und macht die darunter aufgeführten Pfadregeln (`/dev/* mrwkl`,
`/app/** rwix`, `/config/** rw`) wirkungslos, weil sie nichts mehr einschränken.
Zusammen mit `capability sys_admin` bleibt vom Profil wenig Schutzwirkung übrig.

Der Weg dorthin ist nicht „Regeln streichen und hoffen“, sondern:

1. `file,` entfernen, die vorhandenen Pfadregeln stehen lassen.
2. Add-on im Beschwerdemodus laufen lassen und die Verweigerungen im
   Kernel-Log einsammeln — Chromium greift auf mehr zu, als man vermutet
   (`/proc/*/`, `/sys/devices/system/cpu/`, Schriftarten, `/dev/shm`).
3. Die tatsächlich benötigten Pfade nachtragen, dann erneut prüfen.
4. `sys_admin` erst zuletzt anfassen. Chromium braucht die Berechtigung für
   seine eigene Sandbox; ob sie hier entbehrlich ist, hängt an den
   Puppeteer-Startargumenten und muss am laufenden Add-on geprüft werden.

Falsch beschnitten startet das Add-on nicht mehr oder verliert die Sitzung.
Also nichts, was man nebenbei mitnimmt.
