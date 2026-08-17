# NPMplus

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

Zwei Wege, je nachdem wie dein CrowdSec liest. Beide sind im Add-on einzeln schaltbar.

**Variante A — journald** (passt zu einer bestehenden journald-Acquisition):

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

**Variante B — Dateien** (der vom NPMplus-Projekt dokumentierte Weg):

Add-on-Option `share_logs: true` setzen, dann liegen die Logs unter `/share/npmplus/logs`. Das CrowdSec-Add-on braucht dafür Zugriff auf `/share`.

```yaml
---
filenames:
  - /share/npmplus/logs/*.log
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

Im CrowdSec-Add-on:

```sh
cscli bouncers add npmplus
```

Den ausgegebenen Schlüssel in die Add-on-Optionen eintragen:

```yaml
crowdsec_enabled: true
crowdsec_api_key: "<Schlüssel aus cscli>"
crowdsec_lapi_url: "http://127.0.0.1:8080"
crowdsec_appsec_url: "http://127.0.0.1:7422"
```

NPMplus neu starten. Im Protokoll erscheint `CrowdSec-Bouncer aktiv gegen …`.

> Läuft CrowdSec in einem eigenen Container ohne Host-Netzwerk, ist `127.0.0.1` falsch — dann die IP des Hosts oder des CrowdSec-Containers eintragen und dort die Ports 8080 und 7422 freigeben.

> Mit aktivem CrowdSec puffert nginx alle Anfragen. `proxy_request_buffering off` wirkt dann nicht mehr.

## Optionen

| Option | Standard | Bedeutung |
|---|---|---|
| `TZ` | `Europe/Berlin` | Zeitzone des Containers |
| `acme_email` | – | E-Mail für Let's Encrypt |
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
| `share_logs` | `true` | Logs nach `/share/npmplus/logs` spiegeln |
| `log_to_stdout` | `true` | Logs zusätzlich ins Add-on-Protokoll (journald) |
| `goaccess` | `false` | GoAccess-Dashboard unter `/goaccess` |
| `trust_ip` | – | Vertrauenswürdige Proxy-IPs für X-Forwarded-For |
| `trust_cloudflare` | `false` | Cloudflare-IP-Bereiche laden und vertrauen |
| `crowdsec_enabled` | `false` | nginx-Bouncer aktivieren |
| `crowdsec_lapi_url` | `http://127.0.0.1:8080` | CrowdSec Local API |
| `crowdsec_api_key` | – | Bouncer-Schlüssel aus `cscli bouncers add` |
| `crowdsec_appsec_url` | `http://127.0.0.1:7422` | AppSec/WAF-Endpunkt |
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

## Daten und Backup

Alles liegt im Add-on-Verzeichnis `/data`: SQLite-Datenbank, Zertifikate unter `/data/tls`, nginx-Konfiguration, CrowdSec-Bouncer-Konfiguration unter `/data/crowdsec/crowdsec.conf`.

Ein Home-Assistant-Backup dieses Add-ons enthält damit **auch die privaten Schlüssel deiner Zertifikate**. Backups entsprechend behandeln.

## Problembehandlung

**Add-on startet nicht, Port belegt** — es läuft noch ein anderer Proxy (altes NGINX-Add-on, Caddy, Traefik). Erst stoppen.

**Zertifikat lässt sich nicht ausstellen** — Port 80 muss aus dem Internet erreichbar sein und die Domain per DNS auf deine öffentliche IP zeigen. Bei CGNAT oder blockiertem Port 80 hilft nur die DNS-Challenge.

**Falsche Client-IPs in den Logs** — steht ein weiterer Proxy oder Cloudflare davor, dessen IPs in `trust_ip` eintragen bzw. `trust_cloudflare` aktivieren.

**CrowdSec sieht keine Angriffe** — Reihenfolge prüfen: `logrotate` an, Logs kommen an (Variante A oder B), Collection `ZoeyVid/npmplus` installiert, `cscli metrics` zeigt die Acquisition.

**Anmeldung nach jedem Neustart weg** — `cookie_secret` auf einen festen Zufallswert setzen.

## Lizenz

NPMplus steht unter der [AGPL-3.0-or-later](https://github.com/ZoeyVid/NPMplus/blob/develop/LICENSE) und basiert auf dem MIT-lizenzierten nginx-proxy-manager. Dieses Add-on ist nur eine Verpackung des offiziellen Images `zoeyvid/npmplus` — es verändert die Anwendung nicht.
