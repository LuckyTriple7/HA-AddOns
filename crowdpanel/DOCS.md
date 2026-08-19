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
veröffentlicht. Läuft CrowdSec als Add-on im eigenen Container, ist die
Container-Adresse nötig:

```sh
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' $CS
```

Ergebnis ist typischerweise etwas wie `172.30.33.22`, die LAPI also
`http://172.30.33.22:8080`.

### Schritt 3 — Optionen setzen

| Option | Wert |
|---|---|
| `lapi_url` | `http://172.30.33.22:8080` |
| `machine_id` | `crowdpanel` |
| `machine_password` | das Passwort aus Schritt 1 |
| `password` | ein eigenes Passwort statt `changeme123` |

Add-on starten. Im Protokoll steht dann:

```
[INFO] CrowdSec LAPI reachable at http://172.30.33.22:8080 (7 ms)
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

### Sperren

Die Tabelle zeigt jede aktive Entscheidung mit Wert, Bereich, Art, Szenario,
Herkunft, Land, Netz und Restlaufzeit.

- **Suchen** filtert die angezeigten Zeilen über Wert, Szenario, Land und Netz.
- **Bereich**, **Art** und **Herkunft** werden direkt an die LAPI weitergegeben.
- **Entsperren** hebt genau diese eine Entscheidung auf.
- **Alle gefilterten aufheben** hebt genau die angezeigten Zeilen auf, einzeln und
  nacheinander. Es wird nie mehr gelöscht als auf dem Bildschirm steht — das ist
  Absicht, damit ein Filter nicht versehentlich die halbe Sperrliste mitnimmt.

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
*Details* holt den vollständigen Alarm samt der ersten 20 Ereignisse und deren
Feldern — daraus wird ersichtlich, welche Log-Zeile den Alarm ausgelöst hat.

### IP prüfen

Ein Feld für eine Adresse oder einen Bereich. Ergebnis: alle aktiven
Entscheidungen dazu, der Alarmverlauf und ob die Adresse auf einer Allowlist steht.

Der Allowlist-Teil ist wichtig: Steht eine Adresse auf einer Allowlist, greift
**keine** Sperre für sie — auch keine, die man gerade von Hand angelegt hat.

### Allowlists

Nur zum Ansehen. Angelegt und gepflegt werden Allowlists mit
`cscli allowlists`.

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
| `default_ban_duration` | `4h` | Voreingestellte Dauer im Formular |
| `refresh_interval` | `30` | Sekunden bis zur automatischen Aktualisierung, `0` schaltet sie ab |
| `page_size` | `100` | wie viele Alarme höchstens abgefragt werden |
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
| LAPI nicht erreichbar | falsche Adresse oder falscher Port | Container-Adresse mit `docker inspect` prüfen, nicht `127.0.0.1` raten |
| Maschinen-Zugangsdaten werden abgelehnt | Maschine in der falschen Datenbank angelegt | `cscli` mit `-c $CFG` erneut ausführen; mit `machines list` gegenprüfen |
| LAPI-Adresse ist keine http(s)-Adresse | Tippfehler, fehlendes `http://` | `lapi_url` korrigieren |
| Sperre angelegt, Bouncer sperrt nicht | Bouncer holt noch ab, oder Adresse steht auf einer Allowlist | *IP prüfen* öffnen und den Allowlist-Hinweis lesen |
| Anfrage abgelehnt, Seite neu laden | Sitzung oder Formular abgelaufen | Seite neu laden |

Weitere Hinweise stehen im Protokoll des Add-ons. Bei `verbose_log: true` kommen
Zeilen über den Auf- und Abbau der LAPI-Verbindung dazu.

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
