# NPMplus

🇬🇧 [English version](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/DOCS.en.md)

Reverse Proxy mit Weboberfläche auf Basis von [NPMplus](https://github.com/ZoeyVid/NPMplus) — einem aktiv gepflegten Fork von NGINX Proxy Manager mit HTTP/3, gehärtetem TLS, CrowdSec-Bouncer und AppSec/WAF.

## Voraussetzungen

- **Architektur**: amd64 (x86-64-v2 oder neuer) oder aarch64. Reines x86-64 der ersten Generation wird nicht unterstützt.
- **Ports 80, 443/TCP, 443/UDP und 81** müssen frei sein. Läuft bereits ein anderer Reverse Proxy als Add-on (z.B. NGINX Proxy Manager), muss der vorher gestoppt werden.
- Im Router: **443/UDP zusätzlich weiterleiten**, sonst bleibt HTTP/3 ungenutzt.

## Erste Einrichtung

1. Add-on konfigurieren: mindestens `TZ` und `acme_email` setzen.
2. Optional `initial_admin_email` und `initial_admin_password` setzen. Ohne diese Angaben legt NPMplus `admin@example.org` mit einem Zufallspasswort an und schreibt es ins Add-on-Protokoll.
3. Add-on starten und das Protokoll ansehen.
4. Oberfläche öffnen: `https://<HA-IP>:81`

Das Zertifikat der Oberfläche ist selbstsigniert — die Browserwarnung beim ersten Aufruf ist normal.

> **Kein Ingress**: Die NPMplus-Oberfläche spricht ausschließlich HTTPS und arbeitet mit absoluten Pfaden. Der HA-Ingress-Proxy erwartet einfaches HTTP unter einem Unterpfad, beides passt nicht zusammen. Der Zugriff läuft deshalb direkt über Port 81 und damit auch an der HA-Anmeldung vorbei — ein starkes Admin-Passwort ist Pflicht.

## Umstieg von NGINX Proxy Manager

Bestehende Hosts lassen sich nicht automatisch übernehmen, die Datenbanken sind nicht kompatibel. Der Weg mit der kürzesten Ausfallzeit:

1. Im alten Add-on alle Proxy Hosts notieren: Domain, Ziel-IP, Ziel-Port, Schema (http/https), aktivierte Schalter.
2. Altes Add-on **stoppen** — sonst blockiert es Port 80 und 443.
3. NPMplus starten, anmelden, Hosts neu anlegen.
4. Je Host das Let's-Encrypt-Zertifikat neu ausstellen.

Let's Encrypt erlaubt 50 Zertifikate pro Woche und Domain — ein Dutzend Domains neu auszustellen ist unkritisch. Nur bei wiederholten Fehlversuchen mit identischem Domain-Satz greift das Limit von 5 doppelten Zertifikaten pro Woche.

**Wichtig:** Diese DNS-Challenge-Anbieter fallen weg und müssen ersetzt werden: `certbot-dns-he`, `certbot-dns-dnspod`, `certbot-dns-online`, `certbot-dns-powerdns`, `certbot-dns-do`. Route53 wird ebenfalls nicht unterstützt.

## CrowdSec

NPMplus bringt den **Bouncer** mit (nginx/Lua, blockt einzelne Anfragen) und kann den **AppSec/WAF**-Endpunkt ansprechen. Die CrowdSec-Engine selbst läuft weiter in deinem CrowdSec-Add-on. Ein zusätzlich vorhandener Firewall-Bouncer bleibt sinnvoll und stört nicht — er blockt auf IP-Ebene, der nginx-Bouncer auf HTTP-Ebene.

> **Voraussetzung: CrowdSec ist nicht Teil dieses Repos.** Alles hier Beschriebene setzt eine
> laufende CrowdSec-Engine (LAPI) voraus. Für Home Assistant gibt es dazu offizielle Add-ons:
> <https://github.com/crowdsecurity/home-assistant-addons> — `crowdsec` ist die Engine/LAPI,
> `crowdsec-firewall-bouncer` ist optional und sperrt auf Ebene der Host-Firewall.
>
> Der Bouncer für NPMplus selbst steckt bereits in NPMplus (OpenResty/Lua) — es muss also nichts
> zusätzlich installiert werden. Nötig ist nur ein API-Schlüssel aus der Engine
> (`cscli bouncers add npmplus`, siehe Schritt 4). Eingetragen wird er in den Add-on-Optionen
> unter `crowdsec_api_key`, zusammen mit `crowdsec_enabled: true`. Die Datei
> `/data/crowdsec/crowdsec.conf` füllt das Add-on daraus bei jedem Start selbst — `ENABLED`,
> `API_URL`, `API_KEY`, `APPSEC_URL` und die Captcha-Schlüssel dort von Hand zu setzen bringt
> also nichts; alle übrigen Werte der Datei bleiben unangetastet.
>
> Ohne installierte Engine bleiben alle CrowdSec-Optionen wirkungslos.

### 1. Collection in CrowdSec ergänzen

NPMplus schreibt ein anderes Logformat als NGINX Proxy Manager. Die Collection `crowdsecurity/nginx-proxy-manager` greift dort **nicht**. In der CrowdSec-Konfiguration ergänzen:

```yaml
collections:
  - crowdsecurity/home-assistant
  - crowdsecurity/http-cve
  - ZoeyVid/npmplus
```

`crowdsecurity/nginx-proxy-manager` kann drin bleiben, solange das alte Add-on noch läuft, und danach raus.

### 2. Logs zu CrowdSec bringen

Über journald. Ein Weg, kein zweiter.

Add-on-Option `log_to_stdout: true` setzen. Danach den Syslog-Identifier ermitteln, zum Beispiel im Terminal-Add-on:

```sh
journalctl --directory=/var/log/journal/ -o json -n 200 \
  | jq -r .SYSLOG_IDENTIFIER | sort -u | grep -i npmplus
```

Der Wert sieht aus wie `app_<8-stelliger-Repo-Hash>_npmplus`. Damit in die CrowdSec-Acquisition:

```yaml
---
source: journalctl
journalctl_filter:
  - "--directory=/var/log/journal/"
  - "SYSLOG_IDENTIFIER=app_xxxxxxxx_npmplus"
labels:
  type: npmplus
```

### 3. AppSec/WAF aktivieren (optional)

In der CrowdSec-Acquisition ergänzen:

```yaml
---
listen_addr: 0.0.0.0:7422
appsec_config: crowdsecurity/appsec-default
name: appsec
source: appsec
labels:
  type: appsec
```

### 4. Bouncer registrieren

Der Bouncer braucht einen Schlüssel aus **deiner** CrowdSec-Instanz. Ohne gültigen Schlüssel antwortet AppSec mit HTTP 403 — und 403 heißt im AppSec-Protokoll „sperren". Ein falscher Schlüssel würde also jede Anfrage blockieren. Das Add-on prüft ihn deshalb beim Start und startet im Zweifel ohne Bouncer.

Containernamen ermitteln (im Terminal-Add-on mit Docker-Zugriff):

```sh
docker ps --format '{{.Names}}' | grep -iE 'crowdsec|npmplus'
```

> **Wichtigste Stolperfalle:** `cscli` benutzt per Voreinstellung `/etc/crowdsec/config.yaml` — das CrowdSec-**Add-on** startet die Engine aber mit einer eigenen Konfiguration, typischerweise unter `/config/.storage/crowdsec/config/config.yaml`. Ohne `-c` legst du den Bouncer in einer Datenbank an, die die laufende Instanz gar nicht liest. `cscli bouncers list` zeigt ihn dann brav an, die LAPI antwortet trotzdem mit **403**.
>
> Welche Konfiguration wirklich läuft, verrät der Prozess:
> ```sh
> docker exec <crowdsec-container> ps aux | grep crowdsec
> ```
> Hinter `-c` steht der richtige Pfad. Den bei **jedem** `cscli`-Aufruf mitgeben.

Schlüssel erzeugen — mit `-k` einen eigenen, rein hexadezimalen Schlüssel vorgeben, dann können beim Kopieren keine Sonderzeichen wie `+`, `/` oder `=` verlorengehen:

```sh
KEY=$(openssl rand -hex 22)
echo "$KEY"

docker exec <crowdsec-container> cscli -c /config/.storage/crowdsec/config/config.yaml \
  bouncers add npmplus -k "$KEY"
```

Kontrolle — hier muss `npmplus` erscheinen:

```sh
docker exec <crowdsec-container> cscli -c /config/.storage/crowdsec/config/config.yaml bouncers list
```

Ohne `-k` erzeugt `cscli` den Schlüssel selbst; er wird dann **einmalig** angezeigt und ist danach nicht mehr abrufbar. Existiert der Name schon, vorher `cscli … bouncers delete npmplus`.

### 5. Adresse von CrowdSec bestimmen

`http://127.0.0.1:8080` stimmt nur, wenn CrowdSec seine Ports auf den Host legt. Läuft es als gewöhnliches Add-on im Docker-Netz, ist `127.0.0.1` aus Sicht von NPMplus der Host — und dort lauscht niemand. Ergebnis: `connection refused`.

Richtig ist der **Container-Hostname** von CrowdSec:

```sh
docker inspect -f '{{.Config.Hostname}}' <crowdsec-container>
```

Das Ergebnis sieht aus wie `424ccef4-crowdsec`. Der vordere Teil ist die Kennung des Add-on-Repositorys und unterscheidet sich je nach Installation — den eigenen Wert auslesen, nicht diesen abschreiben.

Damit dann in den Add-on-Optionen:

```yaml
crowdsec_enabled: true
crowdsec_api_key: "<Schlüssel aus cscli>"
crowdsec_lapi_url: "http://424ccef4-crowdsec:8080"
crowdsec_appsec_url: "http://424ccef4-crowdsec:7422"
```

> **Keine Container-IP eintragen.** Die IP (`172.30.33.x`, zu finden über `docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' <crowdsec-container>`) gilt nur bis zum nächsten Start. Docker vergibt sie jedes Mal neu, und ein Neustart von Home Assistant startet alle Add-on-Container neu. Danach zeigen `crowdsec_lapi_url` und `crowdsec_appsec_url` ins Leere und der Bouncer bleibt aus, ohne dass jemand etwas geändert hätte. Der Hostname bleibt gleich.

> NPMplus läuft im Host-Netz, löst den Hostnamen anderer Add-ons aber trotzdem auf — der Supervisor gibt jedem Add-on-Container den HA-DNS-Dienst mit. Schlägt die Auflösung ausnahmsweise fehl, funktioniert die lange Form `424ccef4-crowdsec.local.hass.io`.

> Läuft AppSec nicht (kein `appsec`-Block in der Acquisition), muss `crowdsec_appsec_url` **leer** bleiben.

### Beispielkonfiguration des CrowdSec-Add-ons

Zum Abgleich eine vollständige Konfiguration des offiziellen `crowdsec`-Add-ons, die mit
NPMplus zusammenspielt. Der Syslog-Identifier ist ein Platzhalter — den eigenen wie in
Schritt 2 ermitteln und einsetzen.

```yaml
acquisition: |
  ---
  # Home Assistant Core - Anmeldeversuche.
  # type: syslog ist Absicht: syslog-logs setzt das program aus dem
  # SYSLOG_IDENTIFIER, und genau darauf filtert home-assistant-logs.
  source: journalctl
  journalctl_filter:
    - "--directory=/var/log/journal/"
    - "SYSLOG_IDENTIFIER=homeassistant"
  labels:
    type: syslog
  ---
  # NPMplus - Zugriffslog des Reverse Proxy.
  # type: npmplus ist Pflicht: non-syslog setzt daraus das program, und
  # ZoeyVid/npmplus-logs filtert auf program startsWith 'npmplus'.
  source: journalctl
  journalctl_filter:
    - "--directory=/var/log/journal/"
    - "SYSLOG_IDENTIFIER=app_<repo-hash>_npmplus"
  labels:
    type: npmplus
  ---
  # AppSec/WAF - nur virtuelle Patches und generische Regeln.
  listen_addr: 0.0.0.0:7422
  appsec_config: crowdsecurity/appsec-default
  name: appsec
  source: appsec
  labels:
    type: appsec
disable_lapi: false
remote_lapi_url: ''
agent_username: ''
agent_password: ''
collections:
  - crowdsecurity/home-assistant
  - ZoeyVid/npmplus
  - crowdsecurity/http-cve
  - crowdsecurity/appsec-virtual-patching
  - crowdsecurity/appsec-generic-rules
  - crowdsecurity/http-dos
  - crowdsecurity/whitelist-good-actors
parsers: []
scenarios: []
postoverflows: []
parsers_to_disable:
  - crowdsecurity/whitelists
scenarios_to_disable: []
disable_online_api: false
```

Anmerkungen dazu:

- **`type:` je Quelle** entscheidet, welcher Parser greift. Für Home Assistant `syslog` (der
  Parser liest das Programm aus dem `SYSLOG_IDENTIFIER`), für NPMplus `npmplus` —
  `ZoeyVid/npmplus-logs` filtert auf ein Programm, dessen Name mit `npmplus` beginnt.
- **`crowdsecurity/appsec-crs`** (OWASP Core Rule Set) ist bewusst nicht dabei. Er schlägt in
  einer typischen Home-Assistant-Installation reihenweise falsch an, weil er auf
  Teilzeichenketten prüft — `elif` in Jinja-Templates auf `/api/template`, `sched` innerhalb
  von `schedule` in GitHub-Webhooks. Virtual Patching und die generischen Regeln reichen für
  den Anfang; CRS lässt sich später ergänzen, wenn man Ausnahmelisten pflegen mag.
- **`parsers_to_disable: crowdsecurity/whitelists`** schaltet die Freigabe privater
  Adressbereiche ab. Sinnvoll, wenn auch Zugriffe aus dem eigenen LAN bewertet werden sollen —
  wer sich dabei selbst aussperrt, nimmt die Zeile wieder raus.
- **`disable_online_api: false`** meldet Angriffe an die CrowdSec-Community und holt dafür die
  Community-Blocklist. Wer nichts nach außen melden will, setzt `true` und verzichtet auf die
  Blocklist.

### 6. Kontrollieren

NPMplus neu starten. Im Protokoll steht genau eine der beiden Zeilen:

```
[INFO] CrowdSec bouncer active against http://…
[WARN] CrowdSec rejected the bouncer key (HTTP 403) — bouncer stays OFF.
```

> Die Protokollausgabe des Add-ons ist durchgehend englisch, unabhängig von der Sprache dieser Anleitung.

Auf der CrowdSec-Seite prüfen, ob der Bouncer registriert ist und Entscheidungen abholt:

```sh
docker exec <crowdsec-container> cscli -c /config/.storage/crowdsec/config/config.yaml bouncers list
```

`npmplus` muss dort stehen und unter „Last API pull" einen aktuellen Zeitstempel haben. Ist die Liste leer, wurde der Schlüssel nie angelegt — dann Schritt 4 wiederholen.

Ob Logzeilen ankommen:

```sh
docker exec <crowdsec-container> cscli -c /config/.storage/crowdsec/config/config.yaml metrics
```

Unter **Acquisition Metrics** muss die npmplus-Quelle stehen und `lines read` steigen.

### 7. Captcha statt harter Sperre (optional)

Der Bouncer kann verdächtige Besucher ein Rätsel lösen lassen, statt sie auszusperren. Nützlich bei Verdachtsfällen, die auch echte Nutzer treffen können.

Unterstützt werden **Turnstile** (Cloudflare, kostenlos, ohne Nutzerprofilbildung — empfohlen), **hCaptcha** und **reCAPTCHA**. Schlüsselpaar beim jeweiligen Anbieter erzeugen und eintragen:

```yaml
crowdsec_captcha_provider: turnstile
crowdsec_captcha_site_key: "0x4AAA…"
crowdsec_captcha_secret_key: "0x4AAA…"
```

> **Wichtig:** Damit überhaupt ein Captcha erscheint, muss CrowdSec Entscheidungen vom Typ `captcha` ausstellen. Standardmäßig erzeugt es `ban`. Das steuert die `profiles.yaml` in der CrowdSec-Konfiguration, z.B.:
> ```yaml
> name: captcha_remediation
> filters:
>   - Alert.Remediation == true && Alert.GetScenario() contains "http-crawl"
> decisions:
>   - type: captcha
>     duration: 4h
> ```
> Ohne diese Anpassung bleibt jede Sperre eine harte Sperre, egal welche Schlüssel eingetragen sind.

Zum Testen eine Captcha-Entscheidung für die eigene IP setzen:

```sh
docker exec $CS cscli -c $CFG decisions add --ip <deine-ip> --duration 5m --type captcha
```

Das Aussehen der Seite lässt sich über `/data/crowdsec/captcha.html` anpassen; die unveränderte Vorlage liegt daneben als `captcha.html.example`.

### Prüfbefehle auf einen Blick

Alle Befehle im Terminal-Add-on mit Docker-Zugriff. `CS` ist der CrowdSec-Container, `NP` der von NPMplus.

```sh
CS=$(docker ps --format '{{.Names}}' | grep -i crowdsec | head -1)
NP=$(docker ps --format '{{.Names}}' | grep -i npmplus | head -1)
CFG=/config/.storage/crowdsec/config/config.yaml
```

| Frage | Befehl |
|---|---|
| Welche Konfiguration nutzt die laufende Engine? | `docker exec $CS ps aux \| grep crowdsec` |
| Ist der Bouncer registriert und holt er ab? | `docker exec $CS cscli -c $CFG bouncers list` |
| Kommen Logzeilen an? | `docker exec $CS cscli -c $CFG metrics` |
| Wer ist gerade gesperrt? | `docker exec $CS cscli -c $CFG decisions list` |
| Welche Szenarien und Parser sind installiert? | `docker exec $CS cscli -c $CFG collections list` |
| Wie heißt der CrowdSec-Container? | `docker inspect -f '{{.Config.Hostname}}' $CS` |
| Sind LAPI und AppSec von außen erreichbar? | `nc -z -v <crowdsec-hostname> 8080 && nc -z -v <crowdsec-hostname> 7422` |
| Was steht in der Bouncer-Konfiguration von NPMplus? | `docker exec $NP grep -E '^(ENABLED\|API_URL\|APPSEC_URL)=' /data/crowdsec/crowdsec.conf` |
| Akzeptiert die LAPI genau diesen Schlüssel? | siehe unten |

Schlüssel direkt testen — nimmt den Wert aus der Datei und fragt die LAPI daran vorbei am Add-on:

```sh
KEY=$(docker exec $NP sh -c "grep '^API_KEY=' /data/crowdsec/crowdsec.conf | cut -d= -f2-")
echo "Länge: ${#KEY}"   # cscli erzeugt 44 Zeichen
docker exec $CS curl -s -o /dev/null -w '%{http_code}\n' \
  -H "X-Api-Key: $KEY" "http://127.0.0.1:8080/v1/decisions?ip=1.2.3.4"
```

`200` heißt: Schlüssel gültig. `403` heißt: die laufende Instanz kennt ihn nicht — fast immer, weil er mit `cscli` ohne `-c` in der falschen Datenbank gelandet ist.

Ob der Bouncer tatsächlich blockt, siehst du am schnellsten an einer Testsperre der eigenen IP:

```sh
docker exec $CS cscli -c $CFG decisions add --ip <deine-ip> --duration 2m --type ban
```

Danach eine Domain aufrufen: es muss die Sperrseite kommen. Wieder freigeben:

```sh
docker exec $CS cscli -c $CFG decisions delete --ip <deine-ip>
```

## Ländersperre

Sperrt ganze Länder direkt in nginx — ohne MaxMind-Konto, ohne Zusatzmodul, ohne CrowdSec. Die Entscheidung fällt beim ersten Paket, während CrowdSec erst nach der Auswertung der ersten Anfrage reagiert.

Die Adressbereiche kommen vom Projekt [ipverse/country-ip-blocks](https://github.com/ipverse/country-ip-blocks), das die Delegationsdateien der Regional Internet Registries (RIPE, ARIN, APNIC …) täglich zu fertigen CIDR-Listen aufbereitet. Das Add-on lädt sie beim Start und schreibt sie in das eingebaute `geo`-Modul von nginx.

### Zwei Betriebsarten

```yaml
geo_mode: block
geo_countries:
  - cn
  - ru
  - kp
```

`block` lässt alle durch und sperrt die genannten Länder. Empfohlen für den Anfang.

### Vorauswahl statt Tipparbeit

```yaml
geo_mode: block
geo_preset: high_risk
```

Trägt 16 Länder auf einen Schlag ein:

`CN` `RU` `KP` `IR` `PK` `BD` `VN` `MY` `TH` `PH` `NG` `GH` `ZA` `AR` `CO` `EG`

Zusammen rund **38 000 Adressbereiche**. Der Download dauert beim Start ein paar Sekunden, danach liegt alles im Container.

`geo_countries` bleibt daneben nutzbar — beide Listen werden zusammengeführt, Doppelte fallen weg:

```yaml
geo_preset: high_risk
geo_countries:
  - ua
  - by
```

**`geo_mode` ist der Hauptschalter.** Steht er auf `off`, passiert nichts, egal was in Vorauswahl und Länderliste steht — das Protokoll warnt dann darüber. In Verbindung mit `allow` wird die Vorauswahl mit einer Warnung übergangen, sonst wäre aus der Sperrliste plötzlich eine Erlaubnisliste geworden.

Ob die Sperre tatsächlich läuft, erkennst du im Protokoll an der Zeile `Downloading country lists for … countries` und der Meldung `Country filter active`. Fehlen die, ist sie aus.

**Was nicht drin ist und warum:** `IN`, `BR`, `MX`, `ID` und `TR` fehlen bewusst. Das sind große Internetländer mit vielen echten Nutzern — sie zu sperren kostet mehr an ausgesperrten Besuchern, als es an Angriffen erspart. Wer sie trotzdem will, schreibt sie zusätzlich in `geo_countries`:

```yaml
geo_preset: high_risk
geo_countries:
  - in
  - br
```

Umgekehrt gilt: Die Auswahl bleibt grob. Auch in den 16 Ländern wohnen echte Menschen. Wer dort Bekannte hat oder jemanden im Urlaub erwartet, lässt das Land weg und tippt die gewünschten Codes einzeln in `geo_countries`, statt `high_risk` zu benutzen. Einzelne Adressen lassen sich über `geo_allow_ips` freistellen.

**Grenzen der Methode:** Der überwiegende Teil automatisierter Angriffe kommt heute aus Rechenzentren, nicht aus Wohnanschlüssen — gemietete Server in den Niederlanden, Deutschland oder den USA. Genau die kann man nicht sperren, dort steht man selbst. Eine Ländersperre senkt also das Grundrauschen im Protokoll spürbar, ersetzt aber CrowdSec nicht.

```yaml
geo_mode: allow
geo_countries:
  - de
  - at
  - ch
```

`allow` dreht es um: nur die genannten Länder kommen durch, alles andere bekommt **403**.

### Ausnahmen

```yaml
geo_exempt_hosts:
  - home.gizmonet.de
```

Für diese Hostnamen gilt die Sperre nicht. Der Eintrag rettet dich, wenn du im Urlaub in einem gesperrten Land stehst und an Home Assistant musst.

Zwei Ausnahmen setzt das Add-on immer selbst:

- **`/.well-known/acme-challenge/`** ist grundsätzlich frei. Let's Encrypt validiert aus den USA — ohne diese Ausnahme wären im `allow`-Modus Erstausstellung und Verlängerung tot.
- Die **Weboberfläche auf Port 81** ist nicht betroffen, sie läuft in einem eigenen Server-Block.

### Einzelne Adressen sperren oder freigeben

Unabhängig vom Land:

```yaml
geo_deny_ips:
  - 203.0.113.7
  - 198.51.100.0/24
  - 2001:db8::/32
```

Diese Adressen bekommen immer **403** — auch bei `geo_mode: off` und auch auf den Hostnamen aus `geo_exempt_hosts`. Das ist die harte Sperrliste für einzelne Störer.

Umgekehrt:

```yaml
geo_allow_ips:
  - 203.0.113.7
```

Diese Adressen trifft die Ländersperre nie, selbst wenn sie in einem gesperrten Land liegen. Gedacht für die eigene Anschrift im Urlaub oder einen Überwachungsdienst im Ausland. Auf `geo_deny_ips` hat das keinen Einfluss — was dort steht, bleibt gesperrt.

Beide Listen nehmen einzelne Adressen und CIDR-Bereiche, IPv4 wie IPv6. Im `geo`-Modul gewinnt immer der genauere Eintrag, eine einzelne Adresse schlägt also den Länderblock, in dem sie liegt. Einträge, die keine Adresse sind, werden mit einer Warnung im Protokoll verworfen statt in die Konfiguration übernommen.

Für dauerhafte Sperren gegen Angreifer ist CrowdSec trotzdem der bessere Weg — es findet sie selbst und vergisst sie wieder. `geo_deny_ips` ist für Fälle gedacht, die man von Hand entschieden hat.

### Auffrischen

```yaml
geo_refresh_hours: 24
```

Die Registries verschieben laufend Adressblöcke. Nach einigen Monaten ohne Auffrischung sperrt die Liste die Falschen aus. Das Add-on lädt sie deshalb im eingestellten Abstand neu und startet nginx nur dann durch, wenn sich tatsächlich etwas geändert hat. `0` schaltet das Auffrischen ab.

Ist das Netz beim Start gestört, bleiben die zuletzt geladenen Listen in Kraft. Gibt es noch gar keine, bleibt die Sperre **aus** — ein Downloadfehler soll niemanden aussperren.

### Genauigkeit

Registerdaten sagen, wem ein Adressblock *zugeteilt* ist, nicht, wo er benutzt wird. MaxMind misst zusätzlich und liegt deshalb im Einzelfall näher dran.

Für `block` ist der Unterschied belanglos. Bei `allow` mit nur `de` fliegen dagegen echte Besucher raus, sobald ihr Anbieter Adressen aus einem im Register ausländisch geführten Block vergibt — bei Mobilfunk und großen Hostern keine Seltenheit. Sperrliste ist im Zweifel die gesündere Wahl.

### Nachsehen, was aktiv ist

```sh
CT=$(docker ps --format '{{.Names}}' | grep npmplus)
docker exec $CT sh -c 'wc -l /data/geoip/ranges.conf; cat /data/geoip/http.conf'
```

### Was gesperrte Besucher bekommen

```yaml
geo_deny_action: 403
```

Standard. nginx liefert eine kurze Sperrseite in Deutsch und Englisch. Sie liegt als `/data/geoip/blocked.html` und lässt sich frei bearbeiten — das Add-on legt sie nur an, wenn sie fehlt, und überschreibt sie nie. Sinnvoll, um einen Kontaktweg für Fehlsperrungen hineinzuschreiben.

```yaml
geo_deny_action: 444
```

nginx schließt die Verbindung, ohne eine einzige Zeile zu antworten. Ein Scanner erfährt so nicht einmal, dass an der Adresse ein Server steht. Nachteil: ein versehentlich gesperrter echter Besucher sieht nur einen Verbindungsabbruch und meldet dir „die Seite geht nicht" statt einer klaren Fehlermeldung.

Die Sperrseite ersetzt nicht die Seite von CrowdSec. Beide bleiben getrennt: das Add-on antwortet intern mit dem eigenen Code 460 und wandelt ihn erst danach in 403 um. Ein `error_page 403` hätte auch die Sperrseiten von CrowdSec und von Zugriffslisten verschluckt.

### Wer gesperrt wurde, und aus welchem Land

```yaml
geo_log_country: true
```

Schreibt jede gesperrte Anfrage nach `/data/nginx/logs/blocked.log`, mit Ländercode:

```
2026-08-18T11:04:12+02:00 www.gizmonet.de 1.2.3.4 cn "GET /wp-login.php HTTP/1.1" 403 "python-requests/2.31"
```

Die Spalten:

| Spalte | Inhalt | Beispiel |
|---|---|---|
| 1 | Zeitstempel | `2026-08-18T11:04:12+02:00` |
| 2 | Angefragter Host | `www.gizmonet.de` |
| 3 | Quell-IP | `49.232.104.223` |
| 4 | Land | `cn` |
| 5–7 | Anfrage in Anführungszeichen | `"GET /wp-login.php HTTP/1.1"` |
| 8 | Statuscode | `403` |
| 9+ | User-Agent in Anführungszeichen | `"python-requests/2.31"` |

Drei Auswertungen, die sich lohnen:

```sh
L=/share/npmplus/logs/blocked.log

# Welche Länder tragen überhaupt etwas bei?
awk '{print $4}' $L | sort | uniq -c | sort -rn

# Hartnäckigste Einzeladressen
awk '{print $3, $4}' $L | sort | uniq -c | sort -rn | head -20

# Was wollten sie eigentlich?
awk -F'"' '{print $2}' $L | sort | uniq -c | sort -rn | head -20
```

Die dritte ist die aufschlussreichste. Stehen dort massenhaft `/wp-login.php`, `/.env` oder `/phpmyadmin`, sind es reine Scanner und die Sperre tut genau, was sie soll. Tauchen dagegen gewöhnliche Seitenaufrufe auf, hast du womöglich echte Besucher erwischt — dann lohnt der Blick, aus welchem Land sie kamen.

Länder, die dort mit einer Handvoll Treffern auftauchen, kannst du wieder aus der Liste nehmen — jedes gesperrte Land kostet echte Besucher.

> Zeilen aus Versionen vor 0.1.24 haben ein Feld mehr, weil der Zeitstempel damals ein Leerzeichen enthielt. Für die ist `$5` die Landesspalte. Nach der nächsten Logrotation erledigt sich das.

Kosten: eine zweite Nachschlagetabelle im Arbeitsspeicher, rund 4 MB bei 38 000 Bereichen. Im Erlaubnismodus steht in der Spalte `-`, weil dort nur die freigegebenen Länder geladen wurden und die Herkunft der übrigen unbekannt bleibt.

Das reguläre Access-Log von NPMplus bleibt daneben unverändert.

### Startzeit

Beim Start prüft das Add-on, ob die vorhandenen Listen noch zur Konfiguration passen und jünger als `geo_refresh_hours` sind. Ist das der Fall, entfällt der Download und der Proxy steht sofort:

```
[INFO] Country lists on disk are still current (38034 ranges) — skipping download
```

Sobald du Länder änderst, die Betriebsart wechselst oder `geo_log_country` umstellst, passt der Fingerabdruck nicht mehr und die Listen werden neu geholt.

Im Add-on-Protokoll steht der ganze Vorgang:

```
[INFO] Country preset 'high_risk' adds 21 countries
[INFO] Downloading country lists for 21 countries from ipverse...
[INFO]   cn: 7551 ranges
[INFO]   ru: 10830 ranges
...
[INFO] Country lists ready: 72820 ranges in 9s
[INFO] Country filter active (block): cn,ru,kp,..., 72820 ranges
[INFO] IP deny list active: 3 entries
[INFO] Country lists are refreshed every 24 h
```

Fehlt ein Land, steht dort `Country list xx/ipv4-aggregated could not be downloaded` und am Ende eine Warnung, wie viele Listen fehlen. Die Sperre arbeitet dann trotzdem, nur unvollständig.

### Änderungen wirksam machen

Die nginx-Konfiguration für die Sperre wird beim Start des Add-ons gebaut. Nach jeder Änderung an `geo_mode`, `geo_preset`, `geo_countries`, `geo_exempt_hosts`, `geo_deny_ips`, `geo_allow_ips`, `geo_deny_action` oder `geo_log_country` das **Add-on neu starten** — Speichern allein genügt nicht, und ein `nginx -s reload` auch nicht, weil die Dateien dann noch den alten Stand haben.

Einzige Ausnahme ist das Auffrischen der Länderlisten über `geo_refresh_hours`: das läuft im Betrieb und startet nginx bei einer Änderung selbst durch.

### Verhältnis zu CrowdSec

Beides parallel zu betreiben ist sinnvoll und stört sich nicht. Die Ländersperre ist grob und sofort, CrowdSec ist fein und lernt dazu. Wer Ländersperren bisher über CrowdSec-Szenarien gelöst hat, kann sie dort abschalten.

## Home Assistant hinter NPMplus

Home Assistant beantwortet Anfragen von einem unbekannten Proxy mit **400 Bad Request**. NPMplus läuft im Host-Netz und hat damit keine eigene Container-Adresse — die Anfragen kommen mit der LAN-IP der Maschine an, nicht aus dem `172.30.x.x`-Netz. Ein Eintrag, der für ein Add-on im Bridge-Netz gepasst hat, greift hier also nicht.

In **Einstellungen → System → Netzwerk** unter „X-Forwarded-For vertrauen" oder in der `configuration.yaml`:

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 127.0.0.1
    - ::1
    - 192.168.178.200   # LAN-IP der Home-Assistant-Maschine
    - 172.30.32.0/23
```

Danach Home Assistant **neu starten** — `http:` wird nur beim Start ausgewertet.

Alternativ im Proxy Host als Ziel die interne Adresse `http://172.30.32.1:8123` eintragen; dann bleibt die Quell-IP im Docker-Netz und die vorhandene Liste passt schon.

> Dasselbe gilt für **jeden anderen Dienst hinter NPMplus**, der vertrauenswürdige Proxys prüft — Nextcloud, Vaultwarden, Uptime Kuma und ähnliche. Überall gehört die LAN-IP der Home-Assistant-Maschine in die jeweilige Proxy-Liste, nicht mehr eine `172.30.x.x`-Adresse. Bleibt sie außen vor, sieht der Dienst entweder gar keine Anfrage mehr oder protokolliert alle Zugriffe mit der Proxy-IP — womit ein Brute-Force-Schutz im Zweifel dich selbst aussperrt.


## GoAccess-Statistik

GoAccess wertet das Access-Log aus und zeigt Besucher, Top-Hosts, angefragte URLs, Statuscodes, Traffic, Browser und Referrer — live, per WebSocket aktualisiert.

Einschalten mit `goaccess: true`. `logrotate` wird dabei automatisch mitgesetzt, ohne Access-Log hätte GoAccess nichts zu lesen. Der Dienst startet erst, wenn tatsächlich Zeilen im Log stehen, direkt nach dem Start bleibt die Seite also kurz leer.

> **Nicht unter `/goaccess`.** In der eingesetzten NPMplus-Version läuft GoAccess als eigener HTTPS-Server auf **Port 91**, nicht als Unterpfad der Oberfläche. `https://<HA-IP>:81/goaccess` liefert deshalb die Fehlerseite von NPMplus. Der Umbau auf einen Unterpfad samt Admin-Prüfung steckt zwar im Entwicklungszweig von NPMplus, ist aber in noch keiner Veröffentlichung enthalten.

### Zugriff absichern

Der Server auf Port 91 hat **keine Anmeldung**. Wer ihn erreicht, sieht alle Besucher-IPs und jede angefragte URL deiner Dienste. Das Add-on bindet ihn deshalb standardmäßig nur an `127.0.0.1` (`goaccess_listen_localhost: true`).

Empfohlener Weg zum Dashboard — Proxy Host mit Access-Liste davor:

1. In NPMplus eine **Zugriffsliste** anlegen (Benutzername und Passwort, optional zusätzlich auf dein Subnetz beschränken).
2. Einen **Proxy Host** anlegen, z.B. `stats.deine-domain.tld`, Ziel `https://127.0.0.1:91`.
3. Im Reiter „Optionen" die eben angelegte Zugriffsliste auswählen, im Reiter „TLS" ein Zertifikat ausstellen und HTTPS erzwingen.
4. **Websockets zulassen** einschalten — ohne das bleibt die Live-Aktualisierung stehen.

Nur schnell hineinschauen, ohne Proxy Host: `goaccess_listen_localhost: false` setzen und `https://<HA-IP>:91` aufrufen. Dann liest allerdings jedes Gerät im LAN mit. **Port 91 gehört unter keinen Umständen in eine Portweiterleitung im Router.**

Die Auswertung enthält personenbezogene Daten (IP-Adressen). Wer die Dienste dahinter öffentlich betreibt, gehört mit einem Hinweis in die eigene Datenschutzerklärung.

### Länderauswertung

Fehlt ab Werk. Dafür müssen die MaxMind-Datenbanken (kostenloses Konto) nach `/data/goaccess/geoip` gelegt werden — `GeoLite2-City.mmdb`, `GeoLite2-Country.mmdb` oder `GeoLite2-ASN.mmdb`. NPMplus bindet gefundene Dateien beim Start selbst ein.

## Einstellungen je Proxy Host

### Reiter „Optionen"

| Option | Bedeutung | Empfehlung |
|---|---|---|
| Send noindex header and block some user agents | Setzt `X-Robots-Tag: noindex` und blockt bekannte Crawler | Für private Dienste an, für öffentliche Webseiten aus — sonst verschwindet die Seite aus Suchmaschinen |
| Disable Crowdsec Appsec | Schaltet die WAF-Prüfung nur für diesen Host ab | Aus. Nur bei Fehlalarmen einschalten (z.B. große Uploads, WebDAV) |
| Disable Request Buffering | nginx puffert den Anfrage-Body normalerweise, bevor er ihn weiterreicht | Aus. Bei sehr großen Uploads sinnvoll — mit aktivem CrowdSec wird ohnehin immer gepuffert |
| Disable Response Buffering | Antwort wird sofort durchgereicht statt gesammelt | Aus. Nur für Live-Streams nötig (Server-Sent Events, laufende Logausgaben) |
| Enable compression by upstream | Das Backend darf selbst komprimieren | Aus. NPMplus komprimiert mit brotli/zstd besser |
| Disable URI Sanitisation | nginx normalisiert die URL nicht mehr | Aus. Nur wenn eine App kodierte Sonderzeichen im Pfad braucht |
| Spoof Host Header | Schickt die Ziel-IP als `Host` statt der angefragten Domain | Aus. Bricht bei den meisten Anwendungen Weiterleitungen und absolute Links |
| Enable fancyindex | Verzeichnisauflistung — nur relevant, wenn NPMplus selbst Dateien ausliefert | Bei einem Proxy-Ziel ohne Wirkung |
| X-Frame-Options | Steuert, ob die Seite in einen iframe darf | `SAMEORIGIN` belassen; auf `none` nur, wenn du den Dienst woanders einbetten willst |
| Auth Request | Vorgeschalteter Login über Authelia, Authentik, tinyauth, oauth2-proxy oder Anubis | `none`, solange keiner dieser Dienste läuft. Sonst zusätzlich die passende `AUTH_REQUEST_*_UPSTREAM`-Variable über `extra_env` setzen |

### Reiter „TLS-Zertifikate"

| Schalter | Bedeutung |
|---|---|
| Erzwinge HTTPS | Leitet HTTP auf HTTPS um. Die ACME-Challenge auf Port 80 bleibt davon unberührt |
| HTTP/3 Support | Aktiviert QUIC. Wirkt nur, wenn im Router 443/UDP freigegeben ist — sonst fällt der Browser still auf HTTP/2 zurück |
| HSTS aktiviert | Browser merken sich: diese Domain nur noch über HTTPS |
| HSTS Subdomains+Preload | **Mit Bedacht einschalten.** `includeSubDomains` zwingt *jede* Subdomain auf gültiges HTTPS — ein Gerät, das nur HTTP kann, ist im Browser dann unerreichbar. `preload` zielt auf die Aufnahme in die fest eingebaute Browser-Liste; die Rücknahme dauert Monate |
| Schlüssel beibehalten | Bei der Erneuerung bleibt derselbe private Schlüssel. Nötig für DANE/TLSA-Einträge, sonst Geschmackssache |
| Nutze DNS Challenge | Prüfung über einen TXT-Record statt über Port 80. Nötig hinter CGNAT/DS-Lite, Voraussetzung für Wildcard-Zertifikate |

## Optionen

| Option | Standard | Bedeutung |
|---|---|---|
| `TZ` | `Europe/Berlin` | Zeitzone des Containers |
| `acme_email` | – | E-Mail für Let's Encrypt |
| `acme_profile` | `shortlived` | Laufzeit der Zertifikate: `shortlived` ≈ 6 Tage, `classic` = 90 Tage |
| `initial_admin_email` | – | Erster Benutzer, nur beim allerersten Start |
| `initial_admin_password` | – | Passwort dazu; leer = Zufallspasswort im Protokoll |
| `http_port` | `80` | HTTP-Port; Änderung bricht die HTTP-Challenge |
| `https_port` | `443` | HTTPS-Port, TCP und UDP |
| `admin_port` | `81` | Port der Weboberfläche |
| `disable_ipv6` | `false` | IPv6 abschalten |
| `disable_h3_quic` | `false` | HTTP/3 abschalten |
| `enable_mptcp` | `false` | Multipath-TCP |
| `logrotate` | `true` | Access-Logs schreiben und rotieren |
| `logrotations` | `3` | Wie viele rotierte Logs bleiben |
| `error_log_level` | `warn` | Ab welcher Stufe nginx ins Error-Log schreibt |
| `share_logs` | `true` | Logs nach `/share/npmplus/logs` spiegeln |
| `log_to_stdout` | `true` | Access-Log zusätzlich ins Add-on-Protokoll (journald) |
| `goaccess` | `false` | GoAccess-Dashboard auf Port 91 |
| `goaccess_listen_localhost` | `true` | Dashboard nur an `127.0.0.1` binden |
| `trust_ip` | – | Vertrauenswürdige Proxy-IPs für X-Forwarded-For |
| `trust_cloudflare` | `false` | Cloudflare-IP-Bereiche laden und vertrauen |
| `crowdsec_enabled` | `false` | nginx-Bouncer aktivieren |
| `crowdsec_lapi_url` | `http://127.0.0.1:8080` | CrowdSec Local API |
| `crowdsec_api_key` | – | Bouncer-Schlüssel aus `cscli bouncers add` |
| `crowdsec_appsec_url` | `http://127.0.0.1:7422` | AppSec/WAF-Endpunkt |
| `crowdsec_captcha_provider` | – | `turnstile`, `hcaptcha` oder `recaptcha`; leer = aus |
| `crowdsec_captcha_site_key` | – | Öffentlicher Schlüssel des Anbieters |
| `crowdsec_captcha_secret_key` | – | Geheimer Schlüssel des Anbieters |
| `geo_mode` | `off` | Ländersperre: `block`, `allow` oder `off` |
| `geo_preset` | `none` | Fertige Länderauswahl: `high_risk` oder `none` |
| `geo_countries` | `[]` | Ländercodes mit zwei Buchstaben, z. B. `cn` |
| `geo_exempt_hosts` | `[]` | Hostnamen, für die die Sperre nicht gilt |
| `geo_deny_ips` | `[]` | Immer gesperrte Adressen oder CIDR-Bereiche |
| `geo_allow_ips` | `[]` | Adressen, die die Ländersperre nie trifft |
| `geo_refresh_hours` | `24` | Abstand für das Neuladen der Listen; `0` = aus |
| `geo_deny_action` | `403` | Antwort bei Sperre: `403` mit Seite oder `444` wortlos |
| `geo_log_country` | `true` | Gesperrte Anfragen mit Land nach `blocked.log` |
| `nginx_worker_processes` | `auto` | Anzahl nginx-Worker |
| `nginx_worker_connections` | `512` | Verbindungen je Worker |
| `cookie_secret` | – | Fester Schlüssel für Anmelde-Cookies |
| `extra_env` | `[]` | Weitere NPMplus-Variablen als `KEY=VALUE` |

Alles, was hier nicht auftaucht, lässt sich über `extra_env` setzen. Die vollständige Liste steht in der [compose.yaml von NPMplus](https://github.com/ZoeyVid/NPMplus/blob/develop/compose.yaml):

```yaml
extra_env:
  - "ACME_SERVER=https://acme.zerossl.com/v2/DV90"
  - "NGINX_LOG_NOT_FOUND=true"
```

## Laufzeit der Zertifikate

NPMplus fordert bei Let's Encrypt standardmäßig das Profil `shortlived` an — die Zertifikate laufen rund **6 Tage**. Certbot erneuert stündlich bis dreistündlich, im Normalbetrieb merkst du davon nichts.

Vorteil: ein abhandengekommener Schlüssel ist binnen einer Woche wertlos, Sperrlisten spielen keine Rolle mehr.

Nachteil: Fällt die Erneuerung länger aus — Ausfall der Maschine, Port 80 zu, DNS falsch — sind die Zertifikate schnell abgelaufen. Mit `classic` bekommst du die gewohnten 90 Tage und damit mehr Luft:

```yaml
acme_profile: classic
```

Die Umstellung wirkt erst bei der nächsten Ausstellung, nicht rückwirkend auf vorhandene Zertifikate.

## Daten und Backup

Alles liegt im privaten Add-on-Verzeichnis `/data`:

| Was | Pfad |
|---|---|
| Datenbank | `/data/npmplus/database.sqlite` |
| Verschlüsselungsschlüssel | `/data/npmplus/keys.json` |
| Let's-Encrypt-Zertifikate | `/data/tls/certbot/live/npm-<id>/` |
| Eigene Zertifikate | `/data/tls/custom/` |
| CrowdSec-Bouncer-Konfiguration | `/data/crowdsec/crowdsec.conf` |
| nginx-Konfigurationen | `/data/nginx/` |
| Logs | `/data/nginx/logs/` bzw. `/share/npmplus/logs` |

### Über Samba erreichbar?

Nein. Der Samba-Share zeigt `config`, `share`, `media`, `backup`, `ssl` und `addons` — Datenverzeichnisse von Add-ons gehören nicht dazu. Einzige Ausnahme sind die Logs, wenn `share_logs` aktiv ist: die liegen unter `/share/npmplus/logs` und sind damit sichtbar.

Alles andere erreichst du über ein Terminal-Add-on mit Docker-Zugriff. Ansehen:

```sh
docker exec <npmplus-container> ls -la /data/tls/certbot/live/
```

Herauskopieren:

```sh
docker cp <npmplus-container>:/data/npmplus/database.sqlite /share/npmplus-db.sqlite
docker cp <npmplus-container>:/data/tls /share/npmplus-tls
```

Danach liegen die Kopien in `/share` und sind über Samba sichtbar.

> In `/data/tls` liegen die **privaten Schlüssel deiner Zertifikate**. Eine Kopie in `/share` kann jeder lesen, der Zugriff auf die Freigabe hat — nach dem Sichern also wieder löschen.

### Reguläre Sicherung

Ein Home-Assistant-Backup des Add-ons enthält `/data` vollständig, inklusive Datenbank und Zertifikaten. Für Sicherungen brauchst du also nichts von Hand zu kopieren — dieselbe Warnung gilt aber auch hier: das Backup enthält private Schlüssel.

## Problembehandlung

**Add-on startet nicht, Port belegt** — es läuft noch ein anderer Proxy (altes NGINX-Add-on, Caddy, Traefik). Erst stoppen.

**Zertifikat lässt sich nicht ausstellen, Fehler nennt eine IPv6-Adresse** — existiert für die Domain ein AAAA-Record, versucht Let's Encrypt zuerst IPv6. Zeigt der Record auf ein Gerät, das nicht antwortet, scheitert die Prüfung, egal wie gut IPv4 eingerichtet ist. Prüfen mit `dig +short AAAA <domain>`; wenn du IPv6 nicht betreibst, den Record beim DNS-Anbieter löschen. Achtung: Subdomains haben eigene Records, nur CNAMEs erben. Und der DynDNS-Updater darf keine IPv6 mehr melden, sonst steht der Record beim nächsten Lauf wieder da.

> IPv6 im Router oder im Add-on abzuschalten hilft **nicht** — entscheidend ist allein der DNS-Eintrag.

**Zertifikat lässt sich nicht ausstellen** — Port 80 muss aus dem Internet erreichbar sein und die Domain per DNS auf deine öffentliche IP zeigen. Bei CGNAT oder blockiertem Port 80 hilft nur die DNS-Challenge.

**Alle Seiten liefern die CrowdSec-Sperrseite** — der Bouncer erreicht CrowdSec nicht oder der Schlüssel wird abgelehnt. Ab Version 0.1.4 verhindert die Startprüfung das; bei älteren Ständen `crowdsec_enabled` ausschalten und neu starten.

**CrowdSec lief, nach einem Neustart erreicht der Bouncer nichts mehr** — in `crowdsec_lapi_url` steht eine Container-IP (`172.30.33.x`), die Docker beim Start neu vergeben hat. Beide URLs auf den Container-Hostnamen umstellen, z.B. `http://424ccef4-crowdsec:8080`.

**Protokoll meldet „error loading captcha plugin: no recaptcha site key provided"** — kosmetisch. Ist `crowdsec_captcha_provider` leer, fällt der Bouncer intern auf `recaptcha` zurück, findet keinen Site-Key und schaltet Captcha ab. Der Bouncer selbst arbeitet normal weiter. Die Zeile verschwindet erst, wenn Captcha mit Anbieter und beiden Schlüsseln eingerichtet ist (siehe Schritt 7).

**Protokoll meldet „Permission Denied" mit HTTP 403 auf `/api/nginx/...`** — diese Anfragen kommen nicht aus dem Add-on. Am User-Agent (`HomeAssistant/…`) und der IP erkennbar: eine Home-Assistant-Integration fragt die NPMplus-API ab, typischerweise „Nginx Proxy Manager" aus HACS. Die Anmeldung selbst klappt (sonst käme 401), aber der dort hinterlegte Benutzer darf die Listen nicht lesen. In NPMplus unter *Users* den Benutzer öffnen, *Edit Permissions* auf mindestens „View" stellen oder ihn zum Administrator machen — sonst die Integration entfernen. Der Proxy-Betrieb ist davon nicht betroffen, nur die Sensoren der Integration bleiben leer.

**Falsche Client-IPs in den Logs** — steht ein weiterer Proxy oder Cloudflare davor, dessen IPs in `trust_ip` eintragen bzw. `trust_cloudflare` aktivieren.

**CrowdSec sieht keine Angriffe** — Reihenfolge prüfen: `logrotate` an, Logs kommen über journald an (`log_to_stdout` an, Identifier stimmt), Collection `ZoeyVid/npmplus` installiert, `cscli metrics` zeigt die Acquisition.

**400 Bad Request bei Home Assistant** — siehe Abschnitt „Home Assistant hinter NPMplus".

**Protokoll meldet „CrowdSec rejected the bouncer key (HTTP 403)", obwohl der Schlüssel stimmt** — der Bouncer steckt in der falschen Datenbank. `cscli` ohne `-c` schreibt nach `/etc/crowdsec/`, die Add-on-Instanz liest aber ihre eigene Konfiguration. Bouncer mit `-c <pfad-aus-ps-aux>` neu anlegen.

**Anmeldung nach jedem Neustart weg** — `cookie_secret` auf einen festen Zufallswert setzen.

**`https://<HA-IP>:81/goaccess` zeigt „Ups… Sie haben eine Fehlerseite gefunden"** — den Pfad gibt es nicht. GoAccess läuft auf Port 91, siehe Abschnitt „GoAccess-Statistik".

**GoAccess-Dashboard bleibt leer** — der Dienst startet erst, wenn `/data/nginx/logs/access.log` Zeilen enthält, und prüft das alle 10 Sekunden. Eine Seite über den Proxy aufrufen und kurz warten.

**Port 91 antwortet nicht** — Standard ist `goaccess_listen_localhost: true`, damit lauscht der Dienst nur auf `127.0.0.1` und ist aus dem LAN absichtlich nicht erreichbar.

## Lizenz

NPMplus steht unter der [AGPL-3.0-or-later](https://github.com/ZoeyVid/NPMplus/blob/develop/COPYING) und basiert auf dem MIT-lizenzierten nginx-proxy-manager.

Dieses Add-on baut auf dem offiziellen Image `zoeyvid/npmplus` auf (gepinnt in [Dockerfile](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/Dockerfile)) und **ersetzt dessen Entrypoint** durch `run.sh`, damit die Add-on-Optionen als Umgebungsvariablen ankommen. Die Anwendung selbst wird nicht verändert, es kommt kein RUN-Layer hinzu.

Das veröffentlichte Image `ghcr.io/luckytriple7/npmplus` enthält damit eine geänderte AGPL-Arbeit und steht als Ganzes unter der **AGPL-3.0-or-later**. Die eigenen Dateien des Add-ons stehen unter der MIT-Lizenz. Einzelheiten und Quellenangaben: [LICENSE.md](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/LICENSE.md).

Fehlerberichte: alles rund um `run.sh`, Optionen und Doku gehört in [dieses Repository](https://github.com/LuckyTriple7/HA-AddOns/issues); Fehler in NPMplus selbst bittet das Projekt zuerst [dort](https://github.com/ZoeyVid/NPMplus/issues) zu melden, nicht beim ursprünglichen nginx-proxy-manager.
