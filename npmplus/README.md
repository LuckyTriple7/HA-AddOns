# NPMplus

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=npmplus&style=flat-square)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

🇬🇧 [English version](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/README.en.md)

Reverse Proxy mit Weboberfläche auf Basis von [NPMplus](https://github.com/ZoeyVid/NPMplus) — dem aktiv gepflegten Fork von NGINX Proxy Manager.

## Zugriff

| Dienst | URL |
|--------|-----|
| Weboberfläche | `https://<HA-IP>:81` |
| GoAccess-Statistik (optional) | `https://<HA-IP>:91` — eigener Port, standardmäßig nur auf `127.0.0.1` |

Das Zertifikat der Oberfläche ist selbstsigniert — die Browserwarnung beim ersten Aufruf ist normal.

## Funktionen

- **HTTP/3 (QUIC)** auf UDP 443, eigener nginx-Build mit aws-lc
- **Let's Encrypt** inklusive automatischer Erneuerung, weitere ACME-Server (ZeroSSL, Google Public CA) über `extra_env`
- **Gehärtetes TLS**: ML-KEM, Encrypted Client Hello, moderne Cipher-Auswahl ab Werk
- **CrowdSec-Bouncer und AppSec/WAF** direkt aus den Add-on-Optionen konfigurierbar
- **mTLS**: Client-Zertifikate und eigene CAs hochladbar
- **Access-Listen** pro Host und pro Location, mehrere Listen kombinierbar
- **GoAccess-Dashboard** auf Port 91, ohne eigene Anmeldung — daher ab Werk nur auf `127.0.0.1`, Zugriff über einen Proxy Host mit Zugriffsliste
- **zstd- und brotli-Kompression**, Datei- und PHP-Server mit fancyindex
- Logs wahlweise nach `/share/npmplus/logs` und/oder ins Add-on-Protokoll — passend zu beiden CrowdSec-Acquisition-Varianten

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `TZ` | `Europe/Berlin` | Zeitzone des Containers |
| `acme_email` | – | E-Mail-Adresse für Let's Encrypt |
| `initial_admin_email` | – | Erster Benutzer, nur beim allerersten Start |
| `initial_admin_password` | – | Passwort dazu; leer = Zufallspasswort im Protokoll |
| `admin_port` | `81` | Port der Weboberfläche |
| `logrotate` | `true` | Access-Logs schreiben und rotieren |
| `goaccess` | `false` | GoAccess-Dashboard auf Port 91 |
| `goaccess_listen_localhost` | `true` | Dashboard nur an `127.0.0.1` binden |
| `share_logs` | `true` | Logs nach `/share/npmplus/logs` spiegeln |
| `log_to_stdout` | `true` | Access-Log zusätzlich ins Add-on-Protokoll (journald) |
| `crowdsec_enabled` | `false` | nginx-Bouncer aktivieren |
| `crowdsec_api_key` | – | Schlüssel aus `cscli bouncers add npmplus` |
| `extra_env` | `[]` | Weitere NPMplus-Variablen als `KEY=VALUE` |

Vollständige Optionsliste, CrowdSec-Einrichtung und Umstieg vom alten NGINX-Proxy-Manager-Add-on: **[Dokumentation](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/DOCS.md)**

## Hinweise

- Braucht die Ports **80, 443/TCP, 443/UDP und 81** — ein anderer Reverse Proxy muss vorher gestoppt werden.
- Im Router zusätzlich **443/UDP** weiterleiten, sonst bleibt HTTP/3 ungenutzt.
- **Kein Ingress**: die Oberfläche läuft direkt auf Port 81 und damit an der HA-Anmeldung vorbei. Starkes Admin-Passwort setzen.
- Architektur: amd64 (x86-64-v2 oder neuer) und aarch64.

## Changelog

Siehe [CHANGELOG.md](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/CHANGELOG.md)

## Lizenz

NPMplus steht unter der AGPL-3.0-or-later und basiert auf dem MIT-lizenzierten nginx-proxy-manager. Dieses Add-on verpackt nur das offizielle Image `zoeyvid/npmplus`.
