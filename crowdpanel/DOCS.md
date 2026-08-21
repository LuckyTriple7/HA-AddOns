# CrowdPanel

Weboberfläche für eine laufende CrowdSec-Installation: nachsehen, wer gesperrt ist,
eine Adresse von Hand sperren, eine versehentlich gesperrte Adresse wieder freigeben,
Alarme durchsehen und einzelne IP-Adressen nachschlagen — alles, wofür sonst
`cscli` auf der Kommandozeile nötig wäre.

CrowdPanel bringt selbst kein CrowdSec mit. Es setzt eine bestehende Installation
voraus, zum Beispiel das CrowdSec-Add-on, und spricht mit deren lokaler API.

---

## Was CrowdPanel kann — und was nicht

Alles läuft über die lokale CrowdSec-API (LAPI). Damit geht:

- aktive Sperren auflisten, filtern und aufheben
- neue Sperren anlegen: einzelne IP, CIDR-Bereich, ganzes Land oder ein ganzes Netz (AS)
- Alarme der letzten Stunden bis Wochen ansehen, samt Ereignissen und Quelle
- eine IP-Adresse nachschlagen: aktive Sperren, Alarmverlauf, Allowlist-Treffer
- Allowlists ansehen

Bewusst **nicht** enthalten, weil die LAPI es nicht hergibt: `cscli bouncers list`,
`cscli machines list`, `cscli metrics` und `cscli hub list`. Diese Befehle lesen die
lokale Datenbank von CrowdSec, nicht die API. Ein Zugriff darauf würde bedeuten, das
Home-Assistant-Konfigurationsverzeichnis in dieses Add-on zu mappen — dafür ist der
Nutzen zu klein. Ebenso außen vor bleibt die Home-Assistant-eigene Sperrliste
`ip_bans.yaml`; die wird nur beim Start von Home Assistant gelesen und hat mit
CrowdSec nichts zu tun.

---

## Einrichtung

### Schritt 1 — Maschinen-Zugang in CrowdSec anlegen

CrowdPanel meldet sich bei der LAPI wie `cscli` selbst an, nämlich als **Maschine**.
Ein Bouncer-Schlüssel reicht nicht: Bouncer dürfen Entscheidungen nur lesen, nicht
anlegen oder löschen.

Zuerst den Namen des CrowdSec-Containers herausfinden:

```sh
docker ps --format '{{.Names}}' | grep -i crowdsec
```

Dann den Zugang anlegen. `CFG` zeigt auf die Konfigurationsdatei des CrowdSec-Add-ons:

```sh
CS=app_xxxxxxxx_crowdsec
CFG=/config/.storage/crowdsec/config/config.yaml
PW=$(openssl rand -hex 22)
docker exec $CS cscli -c $CFG machines add crowdpanel --password "$PW" -f -
echo "$PW"
```

> **Das `-c $CFG` ist Pflicht.** Ohne diese Angabe schreibt `cscli` nach
> `/etc/crowdsec` — das ist eine andere, leere Datenbank. Der Zugang würde dort
> angelegt, die laufende LAPI kennt ihn nicht, und CrowdPanel bekommt trotz
> korrektem Passwort ein „auth_failed".

> **Das `-f -` ist ebenso Pflicht, und `--force` ist die falsche Antwort.**
> Ohne `-f` will `cscli` die neuen Zugangsdaten nach
> `local_api_credentials.yaml` schreiben und bricht ab, weil es die Datei schon
> gibt. Diese Datei ist die Anmeldung, mit der CrowdSec selbst an seiner eigenen
> LAPI hängt — sie mit `--force` zu überschreiben hängt den lokalen Agenten an
> den neuen Zugang und bricht die Log-Verarbeitung. `-f -` schreibt die
> Zugangsdaten stattdessen auf die Standardausgabe und lässt die Datei in Ruhe.

`openssl rand -hex 22` liefert 44 Zeichen ohne `+`, `/` oder `=`, damit beim
Kopieren nichts verlorengeht.

Prüfen, ob der Zugang angekommen ist:

```sh
docker exec $CS cscli -c $CFG machines list
```

`crowdpanel` muss mit einem Haken bei „Validated" auftauchen.

### Schritt 2 — LAPI-Adresse herausfinden

`http://127.0.0.1:8080` funktioniert nur, wenn CrowdSec seine Ports auf dem Host
veröffentlicht. Läuft CrowdSec als Add-on im eigenen Container, ist dessen
**Hostname** die richtige Adresse:

```sh
docker inspect -f '{{.Config.Hostname}}' $CS
```

Ergebnis ist etwas wie `424ccef4-crowdsec`, die LAPI also
`http://424ccef4-crowdsec:8080`. Der vordere Teil ist die Kennung des
Add-on-Repositorys und unterscheidet sich von Installation zu Installation —
den Wert also wirklich auslesen und nicht abschreiben.

> **Keine IP-Adresse eintragen.** Die Container-IP (`172.30.33.x`, zu finden mit
> `docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' $CS`)
> funktioniert nur bis zum nächsten Neustart. Docker vergibt sie bei jedem Start
> neu, und ein Neustart von Home Assistant startet alle Add-on-Container neu.
> Danach zeigt `lapi_url` ins Leere und CrowdPanel meldet „LAPI nicht erreichbar".
> Der Hostname bleibt dagegen stabil.

### Schritt 3 — Optionen setzen

| Option | Wert |
|---|---|
| `lapi_url` | `http://424ccef4-crowdsec:8080` |
| `machine_id` | `crowdpanel` |
| `machine_password` | das Passwort aus Schritt 1 |
| `password` | ein eigenes Passwort statt `changeme123` |

Add-on starten. Im Protokoll steht dann:

```
[INFO] CrowdSec LAPI reachable at http://424ccef4-crowdsec:8080 (7 ms)
```

Steht dort stattdessen eine Warnung, hilft die Tabelle unter [Fehlersuche](#fehlersuche).

---

## Zugang und Anmeldung

CrowdPanel ist auf zwei Wegen erreichbar, mit unterschiedlichem Schutz:

**Über die Home-Assistant-Seitenleiste (Ingress).** Home Assistant hat den Benutzer
bereits angemeldet, bevor die Anfrage überhaupt beim Add-on ankommt. CrowdPanel
fragt deshalb nicht noch einmal nach Benutzername und Passwort.

**Über den direkten Port 17797.** Hier meldet CrowdPanel selbst an, mit
`username` und `password` aus den Optionen. Nach fünf Fehlversuchen innerhalb von
zehn Minuten ist die Anmeldung 15 Minuten lang gesperrt.

### Zwei-Faktor-Anmeldung

Unter *Einstellungen* lässt sich für den direkten Port ein zweiter Faktor
einschalten (TOTP, wie bei jeder Authenticator-App).

1. *Einschalten* drücken — es erscheint ein QR-Code
2. QR-Code in der Authenticator-App scannen, oder das Geheimnis abtippen
3. den angezeigten Code eintragen und bestätigen
4. die zehn Backup-Codes notieren — sie werden **nur dieses eine Mal** angezeigt

Der QR-Code wird im Add-on selbst erzeugt. Das Geheimnis verlässt den Server nie
und geht an keinen fremden Dienst.

Jeder Backup-Code funktioniert genau einmal. Beim Anmelden kann statt des
Zeitcodes auch ein Backup-Code eingegeben werden. „Diesem Gerät 30 Tage vertrauen"
überspringt den zweiten Schritt auf diesem Browser; der dafür gesetzte Cookie ist
signiert.

Über Ingress wirkt der zweite Faktor nicht — dort meldet Home Assistant an.

---

## Die Reiter

### Übersicht

Zahl der aktiven Sperren, Alarme der letzten 24 Stunden, Verteilung nach Art und
Herkunft, häufigste Länder und Szenarien.

### Übersicht

Zahl der aktiven Sperren, Erkennungen der letzten 24 Stunden, Blocklisten-Updates,
Verteilung nach Art, Herkunft, Land und Szenario.

Dazu zwei Anzeigen, die den Zustand statt einer Momentaufnahme zeigen:

**Verlauf** — ein Balken je Tag über den Zeitraum aus `history_days` (Vorgabe
sieben). Der helle Anteil sind Erkennungen, der graue die Blocklisten-Updates.
„134 Erkennungen in 24 Stunden" sagt für sich genommen nichts; erst neben den
Vortagen wird sichtbar, ob gerade etwas anrollt.

**Bouncer** — wer die Entscheidungen abholt und wann zuletzt. Das ist die
wichtigste Betriebsfrage überhaupt: Ein Bouncer, der seit Minuten nichts mehr
geholt hat, setzt auch nichts mehr durch. Liegt der letzte Abruf über zehn
Minuten zurück oder ist der Zugang gesperrt, färbt sich die Zeile rot. Die
Maschinen stehen aus Platzgründen unter *Einstellungen*.

Beides liest CrowdPanel aus der SQLite-Datei von CrowdSec, standardmäßig
`data/crowdsec.db` neben dem Konfigurationsverzeichnis; abweichende Pfade über
`crowdsec_db`. Geöffnet wird sie ausschließlich lesend, und ausgeliefert werden
nur Name, Art, Version, Adresse und Zeitstempel — **Schlüssel und Passwörter
verlassen den Server nicht**, die Spalten werden gar nicht erst gelesen.

Wird die Datenbank nicht gefunden, bleibt der Rest der Übersicht davon
unberührt.

### Angriffskarte

Auf der Übersicht steht eine Weltkarte mit einem Punkt je Quelladresse der
letzten 24 Stunden. Die Punktgröße folgt der Zahl der Erkennungen, der
Mauszeiger zeigt Adresse, Land, Netz und das häufigste Szenario. Ein Klick
springt in die Alarmliste, gefiltert auf genau diese Adresse.

Gezeichnet wird aus echten Koordinaten. CrowdSec führt in jedem Alarm
`latitude` und `longitude`, gefüllt vom Parser **`crowdsecurity/geoip-enrich`**
in der Stufe `s02-enrich`. Fehlt der, bleibt die Karte leer und sagt das auch:

```sh
docker exec $CS cscli -c $CFG parsers install crowdsecurity/geoip-enrich
```

Es ist ein **Parser**, keine Collection — `collections install` antwortet mit
`can't find … in collections`.

Danach CrowdSec neu starten. Bereits vorhandene Alarme bekommen rückwirkend
keine Koordinaten; die Karte füllt sich mit den Erkennungen, die danach
hinzukommen.

Nicht auf der Karte landen:

- **Blocklisten-Synchronisierungen.** Ein einzelner Sync bringt Zehntausende
  Einträge ohne Ortsbezug und würde alles andere erschlagen.
- **Koordinaten `0/0`.** Die schreibt CrowdSec, wenn das Enrichment nichts
  gefunden hat. Ein Punkt im Golf von Guinea wäre eine Erfindung.
- **Mehr als 400 Adressen.** Darüber wird nach Zahl der Erkennungen gekürzt; die
  Fußzeile nennt dann, wie viele gezeigt werden.

Die Umrisse liegen als `static/world.svg` im Image, erzeugt aus Natural Earth
1:110m (Public Domain, siehe [LICENSE.md](LICENSE.md)). Nachgeladen wird nichts
aus dem Internet. Projiziert wird in Web Mercator — dieselbe Projektion wie bei
jeder Online-Karte und damit die, die das Auge erwartet. Die Umrechnung bleibt
trotzdem eine Zeile, sodass die Karte ohne Kartenbibliothek auskommt; dieselbe
Formel steht im Erzeugerskript und im Frontend.

### Sperren

Die Tabelle zeigt jede aktive Entscheidung mit Wert, Bereich, Art, Szenario,
Herkunft, Land, Netz und Restlaufzeit.

- **Suchen** filtert die angezeigten Zeilen über Wert, Szenario, Land und Netz.
- **Bereich**, **Art** und **Herkunft** werden direkt an die LAPI weitergegeben.
- **Entsperren** hebt genau diese eine Entscheidung auf.
- **Alle gefilterten aufheben** hebt genau die angezeigten Zeilen auf, einzeln und
  nacheinander. Es wird nie mehr gelöscht als auf dem Bildschirm steht — das ist
  Absicht, damit ein Filter nicht versehentlich die halbe Sperrliste mitnimmt.
  Über 200 Einträge lehnt CrowdPanel ab und bittet um einen engeren Filter.

Ein Klick auf eine Spaltenüberschrift sortiert, ein zweiter dreht die Richtung
um. Auf schmalen Bildschirmen fallen Bereich, Szenario, Herkunft und Netz weg,
damit Wert, Art, Land, Restlaufzeit und die Schaltfläche ohne seitliches Scrollen
lesbar bleiben.

Die Tabelle zeigt höchstens so viele Zeilen, wie `page_size` erlaubt; daneben
steht immer die Gesamtzahl. Das ist keine Schikane: Wer die Community-Blocklisten
abonniert hat, kommt schnell auf 30.000 aktive Entscheidungen, und die gehören
nicht alle gleichzeitig in eine Tabelle. Mit **Herkunft** lässt sich das sofort
sortieren — `crowdsec` sind die von dieser Instanz selbst erkannten Angriffe,
`cscli` die von Hand angelegten, `CAPI` und `lists` kommen von außen.

> Zum Entsperren gibt es zwei Wege mit unterschiedlicher Reichweite. Die
> Schaltfläche in der Zeile benutzt die Entscheidungs-Kennung und trifft genau
> diesen einen Eintrag. Wird stattdessen über eine IP entsperrt, hebt CrowdSec
> auch einen abdeckenden Bereich mit auf — das ist dessen eigenes Verhalten,
> identisch zu `cscli decisions delete --ip`.
>
> Für **Land** und **Netz (AS)** gibt es keinen Sammel-Filter; die LAPI bietet
> dafür keinen. Diese Sperren lassen sich nur über die Zeile aufheben.

### Neue Sperre

| Bereich | Wert | Beispiel |
|---|---|---|
| `Ip` | eine einzelne Adresse | `198.51.100.7` |
| `Range` | ein CIDR-Bereich | `198.51.100.0/24` |
| `Country` | Länderkürzel mit zwei Buchstaben | `CN` |
| `AS` | Netznummer ohne Präfix | `64500` |

**Art** ist `ban` (blockieren) oder `captcha` (Captcha vorschalten). `captcha`
wirkt nur, wenn der Bouncer ein Captcha eingerichtet hat — bei NPMplus zum
Beispiel über `crowdsec_captcha_provider`. Ohne diese Einrichtung passiert bei
`captcha` gar nichts.

**Dauer** kommt aus der Liste oder wird frei eingetragen, im Go-Format:
`30m`, `4h`, `1h30m`, `168h`. Eine unbegrenzte Sperre kennt CrowdSec nicht; der
längste Vorschlag ist ein Jahr (`8760h`).

**Grund** landet als Meldung am Alarm und taucht später in der Alarmliste auf.

> Sperren werden mit der Herkunft `cscli` angelegt, nicht mit einer eigenen.
> Bouncer und die CrowdSec-Konsole filtern nach bekannten Herkünften; eine
> unbekannte könnte stillschweigend übergangen werden. Dass die Sperre aus
> CrowdPanel kam, steht stattdessen im Szenariotext:
> `manual 'ban' from 'crowdpanel'`.

### Alarme

Was CrowdSec erkannt hat, unabhängig davon, ob daraus eine Sperre wurde.

Der Filter **Ansicht** entscheidet, wie die Liste aufgebaut wird:

- **einzeln** — jeder Alarm eine Zeile, chronologisch
- **nach Adresse** — eine Zeile je Quell-IP, mit Trefferzahl, allen dort gesehenen
  Szenarien, Land, Netz und dem letzten Auftreten
- **nach Szenario** — eine Zeile je Muster, mit der Zahl der beteiligten Adressen

Die Gruppierung ist meist das, was du willst. Aus hundert Einzelzeilen wird sichtbar,
dass achtundvierzig davon von derselben Adresse stammen und drei verschiedene
Angriffsmuster auslösen — genau daran erkennt man einen echten Angreifer und
unterscheidet ihn von einem Fehlalarm, der immer dasselbe Szenario meldet.

Jede Zeile mit einer Quelladresse hat einen Knopf **Sperren**. Der fragt nur noch
nach Dauer und Grund und legt die Sperre an, ohne dass du die Adresse abtippen musst.

Der Filter **Art** steht auf „nur Erkennungen". Der Grund: CrowdSec meldet auch
jede Aktualisierung einer abonnierten Blockliste als Alarm — Szenario
`update : +15000/-0 IPs`, null Ereignisse, 15.000 Entscheidungen daran. Das ist
kein Angriff, sondern ein Abgleich, und zwischen echten Erkennungen wäre es nur
Rauschen. Über „nur Blocklisten-Updates" oder „alles" sind sie trotzdem
erreichbar; in der Tabelle tragen sie die Marke *Blockliste*. Die Übersicht zählt
beides getrennt.
*Details* holt den vollständigen Alarm samt der ersten 20 Ereignisse und deren
Feldern — daraus wird ersichtlich, welche Log-Zeile den Alarm ausgelöst hat.

### Alarme lassen sich nicht löschen

CrowdSec erlaubt das Löschen von Alarmen nur von einer vertrauenswürdigen Adresse
aus — in der Voreinstellung `127.0.0.1`, also aus dem CrowdSec-Container heraus.
Über die LAPI antwortet es mit „access forbidden from this IP". CrowdPanel bietet
das deshalb bewusst nicht an. Wer aufräumen will, macht es dort, wo es erlaubt ist:

```sh
docker exec $CS cscli -c $CFG alerts list --origin cscli
docker exec $CS cscli -c $CFG alerts delete --origin cscli
```

Das Aufheben einer Sperre löscht den zugehörigen Alarm übrigens nie — der Alarm
ist der Nachweis, dass etwas passiert ist, die Sperre nur die Folge daraus.

### IP prüfen

Ein Feld für eine Adresse oder einen Bereich. Ergebnis: alle aktiven
Entscheidungen dazu, der Alarmverlauf und ob die Adresse auf einer Allowlist steht.

Gefunden werden dabei auch Sperren, die die Adresse nur mit abdecken — also ein
gesperrter Bereich, in dem sie liegt. Die LAPI vergleicht nur exakt, den
Abdeckungstest macht CrowdPanel selbst; das Ergebnis entspricht dem von
`cscli decisions list --ip`.

Der Allowlist-Teil ist wichtig: Steht eine Adresse auf einer Allowlist, greift
**keine** Sperre für sie — auch keine, die man gerade von Hand angelegt hat.

### Allowlists

Der Reiter zeigt zwei Dinge, die in CrowdSec leicht verwechselt werden.

**Allowlists** liegen in der CrowdSec-Datenbank und verhindern die Sperre: Ein
Alarm entsteht, aber keine Entscheidung greift. Sie gelten sofort für alle
Bouncer. Die LAPI gibt sie nur heraus — anlegen und ändern geht ausschließlich
mit `cscli allowlists`, dafür bietet die API keine Schnittstelle.

**Whitelists** sind Parser-Dateien und greifen eine Stufe früher, beim Lesen der
Logzeile. Eine Zeile von einer eingetragenen Adresse erzeugt gar keinen Alarm.
CrowdPanel liest die YAML-Dateien direkt aus
`/homeassistant/.storage/crowdsec/config/parsers/s02-enrich` und zeigt sie im
Klartext samt Änderungsdatum. Liegen sie woanders, hilft die Option
`whitelist_dir`.

Beides ist reine Anzeige. Für die Whitelists ist das Konfigurationsverzeichnis
von Home Assistant **nur lesend** ins Add-on gemappt; CrowdPanel schreibt dort
nichts und kann es auch nicht. Symbolische Verweise, die aus dem Verzeichnis
herausführen, werden übersprungen, und Dateien über 256 KB werden nicht
angezeigt.

Wie oft eine Whitelist tatsächlich gegriffen hat, steht nicht in den Dateien,
sondern in der Statistik:

```sh
docker exec $CS cscli -c $CFG metrics | grep -A15 -i whitelist
```

Die Spalte „Whitelisted" ist die interessante: Sie zählt, wie viele Zeilen
wirklich verworfen wurden — nicht, wie oft die Regel nur geprüft wurde.

---

## Verhältnis zu den anderen Bausteinen

CrowdSec besteht aus drei Teilen, und CrowdPanel sitzt genau in der Mitte:

| Teil | Aufgabe | Wer macht es |
|---|---|---|
| Eingang | Logs lesen und Angriffe erkennen | CrowdSec-Add-on (Acquisition) |
| Entscheidung | Sperren verwalten und ausliefern | CrowdSec-Engine mit LAPI |
| Ausgang | Sperren durchsetzen | Bouncer, zum Beispiel in NPMplus |

CrowdPanel redet ausschließlich mit der Mitte. Es ersetzt keinen Bouncer und
liest keine Logs — es ändert nur, welche Entscheidungen in der Mitte stehen.
Der Bouncer holt sich die Änderung beim nächsten Abgleich, in der Regel innerhalb
weniger Sekunden.

**Zur Ländersperre in NPMplus:** Die dortige `geo_mode`-Sperre arbeitet in nginx
und greift eine Schicht früher, bevor CrowdSec überhaupt etwas sieht. Ein Land
über CrowdPanel zu sperren ist etwas anderes: Diese Sperre gilt für **alle**
Bouncer, die an derselben LAPI hängen. Beides gleichzeitig ist möglich, aber
meist unnötig — für ein dauerhaft gesperrtes Land ist der nginx-Weg günstiger,
für eine schnelle, überall wirkende Sperre der Weg über CrowdPanel.

---

### Hub

Zeigt, was CrowdSec geladen hat: Collections, Parser, Postoverflows, Szenarien,
AppSec-Konfigurationen und -Regeln, jeweils mit der Angabe, ob das Element aus
dem Hub stammt oder von dir selbst kommt. Parser und Postoverflows sind nach
Stufe aufgeschlüsselt.

Gelesen wird das aus dem Konfigurationsverzeichnis von CrowdSec, standardmäßig
`/homeassistant/.storage/crowdsec/config`; liegt es woanders, hilft die Option
`crowdsec_dir`. Hub-Elemente sind dort symbolische Verweise in ein Verzeichnis
innerhalb des CrowdSec-Containers — CrowdPanel kommt an das Ziel nicht heran und
liest den Namen deshalb aus dem Verweis selbst.

**Versionen und Aktualisierungshinweise fehlen bewusst.** `cscli` ermittelt sie,
indem es den Inhalt jeder Datei hasht und im Hub-Index nachschlägt, und dieser
Index liegt ebenfalls im Container. Wer die grünen Haken und das
`update-available` braucht, nimmt weiterhin:

```sh
docker exec $CS cscli -c $CFG hub list
docker exec $CS cscli -c $CFG hub upgrade
```

---

### Metriken

CrowdSec führt über alles, was durch es hindurchläuft, eigene Zähler. Ausgeliefert
werden die im Prometheus-Textformat, und `cscli metrics` baut seine Tabellen aus
genau dieser Quelle. Der Reiter zeigt dasselbe im Browser:

| Tabelle | Beantwortet |
|---|---|
| Datenquellen | Kommen überhaupt Logzeilen an, und wie viele davon versteht CrowdSec nicht? |
| Parser | Welcher Parser greift, welcher läuft leer? |
| Szenarien | Welches Szenario löst tatsächlich aus, welches ist nur geladen? |
| Whitelists | Wie oft hat eine Ausnahme gegriffen — und aus welchem Grund? |
| LAPI-Aufrufe / je Maschine / je Bouncer | Wer fragt wie oft, und bekommt ein Bouncer überhaupt Sperren geliefert? |
| AppSec | Anfragen und Blockaden je Engine, dazu die Regeln, die getroffen haben |
| Aktive Sperren / Meldungen | CrowdSecs eigene Zählung, aufgeschlüsselt nach Grund, Herkunft und Aktion |
| Laufzeiten | Durchschnitt je Parsing-, Bucket- und LAPI-Vorgang in Millisekunden |
| Zwischenspeicher | Größe der internen Caches |

Alle Zähler laufen seit dem Start von CrowdSec und beginnen bei einem Neustart
wieder bei null. Es sind Summen, keine Raten.

**Die Zähler müssen erst freigegeben werden.** CrowdSec hört damit
standardmäßig nur auf `127.0.0.1`, also nur innerhalb seines eigenen Containers.
CrowdPanel läuft in einem anderen und kommt so nicht heran.

Das ist **keine Add-on-Option** — in den Optionen des CrowdSec-Add-ons taucht
Prometheus nicht auf. Die Einstellung steht in der `config.yaml` von CrowdSec
selbst, unter `/config/.storage/crowdsec/config/config.yaml`. Der Abschnitt ist
dort bereits vorhanden; zu ändern ist nur eine Zeile:

```yaml
prometheus:
  enabled: true
  level: full
  listen_addr: 0.0.0.0   # ← statt 127.0.0.1
  listen_port: 6060
```

Am bequemsten geht das im **Web-Terminal des CrowdSec-Add-ons** — dort ist `yq`
schon installiert:

```sh
yq eval -i '.prometheus.listen_addr = "0.0.0.0"'   /config/.storage/crowdsec/config/config.yaml
```

Danach das CrowdSec-Add-on neu starten und im selben Terminal prüfen:

```sh
curl -s localhost:6060/metrics | head -5
```

Die Datei bleibt erhalten: Das Add-on kopiert sie nur beim allerersten Start aus
dem Image ins Konfigurationsverzeichnis, spätere Starts fassen sie nicht mehr an.
Überschrieben wird bei jedem Start allein `acquis.yaml`.

Port 6060 muss **nicht** nach außen veröffentlicht werden. CrowdPanel spricht den
Container über das Docker-Netz an, genau wie die LAPI auf 8080 — nötig ist nur,
dass CrowdSec überhaupt auf allen Adressen lauscht.

CrowdPanel nimmt ohne weitere Angabe denselben Rechner wie in `lapi_url` und Port
6060; steht der Endpunkt woanders, trägt man ihn vollständig in `prometheus_url`
ein (`http://…:6060` oder direkt `http://…/metrics`).

Solange nichts erreichbar ist, bleibt der Reiter sichtbar und erklärt genau
diesen Schritt, statt einfach leer zu sein.

## Sensoren in Home Assistant

Ist `ha_sensors` an (Vorgabe), meldet CrowdPanel folgende Entitäten an Home
Assistant:

| Entität | Bedeutung |
|---|---|
| `sensor.crowdpanel_decisions` | alle aktiven Sperren, inklusive der abonnierten Blocklisten |
| `sensor.crowdpanel_decisions_local` | nur die aus Herkunft `crowdsec` und `cscli` — was diese Instanz selbst erkannt oder was du von Hand angelegt hast |
| `sensor.crowdpanel_alerts_24h` | Erkennungen der letzten 24 Stunden, ohne Blocklisten-Aktualisierungen |
| `binary_sensor.crowdpanel_lapi` | ob die LAPI erreichbar ist |
| `sensor.crowdpanel_bouncers` | Anzahl der echten Bouncer (ohne abgeleitete Kindeinträge, ohne zurückgezogene) |
| `sensor.crowdpanel_bouncers_stale` | wie viele davon gerade nicht mehr abholen; Attribut `bouncers` nennt sie namentlich |
| `sensor.crowdpanel_bouncer_<name>` | je Bouncer einer, Zustand ist der Zeitpunkt des letzten Abrufs (`device_class: timestamp`) |
| `binary_sensor.crowdpanel_bouncer_<name>` | derselbe Bouncer als Problemmelder: `on`, wenn er nicht mehr abholt (`device_class: problem`) |
| `binary_sensor.crowdpanel_bouncers` | `on`, sobald irgendein Bouncer nicht mehr abholt |

Jeder Bouncer erscheint doppelt: einmal als Zeitstempel für die Anzeige („vor
8 Sekunden") und einmal als Binärsensor mit `device_class: problem`. Der zweite
ist der für Automatisierungen — Home Assistant zeigt ihn von sich aus als
Problem an, und ein Auslöser auf `to: 'on'` braucht keine Zeitrechnung in der
Vorlage. `binary_sensor.crowdpanel_bouncers` fasst alle zu einer Meldung
zusammen.

Die Bouncer-Sensoren beantworten die Frage, ob die Sperren überhaupt noch
durchgesetzt werden. Holt ein Bouncer länger als 10 Minuten nichts mehr ab, gilt
er als still gefallen: `stale` im Attribut wird `true`, und er zählt in
`sensor.crowdpanel_bouncers_stale` mit. Ein Bouncer ohne Abruf meldet nichts —
ohne Sensor fällt genau das niemandem auf. Der Entitätsname entsteht aus dem
Bouncer-Namen, `firewall-bouncer` wird also zu
`sensor.crowdpanel_bouncer_firewall_bouncer`. Abgeleitete Kindeinträge
(`derived: true`) bekommen ebenfalls eine Entität, gelten aber nie als gefallen —
bei ihnen ist ein alter Zeitstempel der Normalfall. Verschwindet ein Bouncer aus
CrowdSec, entfernt CrowdPanel seine Entität beim nächsten Durchlauf.

Weil die Bouncer aus der CrowdSec-Datenbank kommen, brauchen diese Sensoren einen
lesbaren Pfad zu `crowdsec.db` — derselbe, den auch die Übersicht benutzt (siehe
`crowdsec_db`). Ist keiner erreichbar, entfallen sie stillschweigend.

Der interessante ist der zweite. Die Gesamtzahl schwankt mit jeder
Blocklisten-Aktualisierung um Tausende und sagt über deine Lage nichts aus; die
eigenen Sperren sind eine kleine, aussagekräftige Zahl. Eine Automatisierung, die
bei einem sprunghaften Anstieg meldet, gehört an diesen Sensor.

Das Intervall steuert `ha_sensor_interval` (Vorgabe 300 Sekunden). Jede
Aktualisierung fragt die LAPI ab, bei sehr vielen Sperren lohnt ein größerer Wert.

Lehnt Home Assistant die Sensoren ab, steht das **einmal** im Protokoll des Add-ons
— danach nicht mehr, damit eine Fehlkonfiguration das Log nicht flutet.

## Optionen

| Option | Vorgabe | Bedeutung |
|---|---|---|
| `username` | `admin` | Benutzername für den direkten Port |
| `password` | `changeme123` | Passwort für den direkten Port — unbedingt ändern |
| `session_hours` | `24` | Gültigkeit einer Anmeldung in Stunden |
| `lapi_url` | `http://127.0.0.1:8080` | Adresse der CrowdSec-LAPI |
| `machine_id` | leer | Name des Maschinen-Zugangs |
| `machine_password` | leer | Passwort des Maschinen-Zugangs |
| `lapi_tls_verify` | `true` | TLS-Zertifikat prüfen; nur bei selbstsigniertem `https` abschalten |
| `prometheus_url` | leer | Adresse der CrowdSec-Metriken; leer heißt Rechner aus `lapi_url`, Port 6060 |
| `default_ban_duration` | `4h` | Voreingestellte Dauer im Formular |
| `refresh_interval` | `30` | Sekunden bis zur automatischen Aktualisierung, `0` schaltet sie ab |
| `page_size` | `100` | wie viele Zeilen die Tabellen höchstens anzeigen |
| `whitelist_dir` | leer | Verzeichnis der Whitelist-Parser, nur falls die Suche fehlschlägt |
| `crowdsec_dir` | leer | Konfigurationsverzeichnis von CrowdSec, nur falls die Suche fehlschlägt |
| `crowdsec_db` | leer | Datenbank von CrowdSec, nur falls die Suche fehlschlägt |
| `history_days` | `7` | über wie viele Tage der Verlauf reicht |
| `ha_sensors` | `true` | Sensoren an Home Assistant melden |
| `ha_sensor_interval` | `300` | Sekunden zwischen zwei Sensor-Aktualisierungen |
| `verbose_log` | `false` | zusätzliche Zeilen im Protokoll |

---

## Pfade

| Pfad | Inhalt |
|---|---|
| `/data/options.json` | die Optionen, von Home Assistant geschrieben |
| `/data/sessions.json` | offene Anmeldungen |
| `/data/twofa.json` | 2FA-Geheimnis, Backup-Codes, vertrauenswürdige Geräte (Rechte 600) |
| `/data/secret.key` | Signaturschlüssel für Cookies (Rechte 600) |

Alles liegt in `/data` und damit nicht in einem durchsuchbaren Freigabeordner.
Wer die Zwei-Faktor-Anmeldung zurücksetzen muss, löscht `twofa.json` und startet
das Add-on neu.

---

## Fehlersuche

| Anzeige | Ursache | Abhilfe |
|---|---|---|
| Maschinen-Zugangsdaten fehlen | `machine_id` oder `machine_password` leer | Schritt 1 der Einrichtung nachholen |
| LAPI nicht erreichbar | falsche Adresse oder falscher Port | Hostname mit `docker inspect -f '{{.Config.Hostname}}' $CS` prüfen, nicht `127.0.0.1` raten |
| LAPI nicht erreichbar, lief vorher | `lapi_url` enthält eine Container-IP (`172.30.33.x`), die sich beim Neustart geändert hat | `lapi_url` auf den Hostname umstellen, z. B. `http://424ccef4-crowdsec:8080` |
| Maschinen-Zugangsdaten werden abgelehnt | Maschine in der falschen Datenbank angelegt | `cscli` mit `-c $CFG` erneut ausführen; mit `machines list` gegenprüfen |
| LAPI-Adresse ist keine http(s)-Adresse | Tippfehler, fehlendes `http://` | `lapi_url` korrigieren |
| Sperre angelegt, Bouncer sperrt nicht | Bouncer holt noch ab, oder Adresse steht auf einer Allowlist | *IP prüfen* öffnen und den Allowlist-Hinweis lesen |
| Anfrage abgelehnt, Seite neu laden | Sitzung oder Formular abgelaufen | Seite neu laden |

Weitere Hinweise stehen im Protokoll des Add-ons. Bei `verbose_log: true` kommen
Zeilen über den Auf- und Abbau der LAPI-Verbindung dazu.

### Zum Tempo

Die Antwort der LAPI auf „alle aktiven Entscheidungen" ist auf einer Instanz mit
Community-Blocklisten mehrere Megabyte groß. CrowdPanel hält sie deshalb 15
Sekunden lang vor und teilt sie zwischen Übersicht und Sperren; jede Änderung
verwirft den Zwischenspeicher sofort, eine aufgehobene Sperre verschwindet also
ohne Verzögerung. Beim Reiterwechsel zeichnet der Browser zuerst die zuletzt
geladenen Daten und lädt erst danach nach — deshalb wirkt der Wechsel sofort,
auch wenn die frischen Zahlen einen Moment später eintreffen.

---

## Sicherheit

- Über Ingress meldet Home Assistant an, über den direkten Port CrowdPanel selbst.
  Beide Wege führen zu denselben Rechten — wer die Oberfläche erreicht, darf
  sperren und entsperren.
- Zustandsändernde Anfragen brauchen ein signiertes CSRF-Merkmal und einen
  passenden Absender. Damit kann keine fremde Seite im Browser eine Sperre aufheben.
- Passwörter und das Maschinen-Passwort erscheinen in keiner Protokollzeile und in
  keiner Antwort der Oberfläche.
- Jede Eingabe wird geprüft, bevor sie die LAPI erreicht: Adressen und Bereiche
  über `ipaddress`, Länderkürzel und Netznummern über feste Muster, die Dauer über
  das Go-Zeitformat. Ungültiges wird mit einem Fehler abgewiesen und nie
  weitergereicht.
- Das Add-on ruft keine externen Dienste auf und führt keine Programme aus.
