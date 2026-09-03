# NetToolbox

**Netzwerk- und Mail-Diagnose für Home Assistant** · [English](README.en.md)

DNS-Abfragen, Propagationscheck, Reverse-DNS, DNSSEC und ein vollständiger
Mail-Gesundheitscheck (SPF/DKIM/DMARC/MTA-STS/TLS-RPT/BIMI) — ohne fremde API
und ohne die eigenen Daten an einen Drittanbieter zu schicken.

## Funktionen

- **DNS** — alle gängigen Record-Typen, alle Standard-Typen in einem Rutsch, TXT, SOA mit
  Nameserver-Sync-Check
- **Mail-Gesundheit** — SPF (inklusive Lookup-Zähler und Include-Kette), DKIM (Schlüsselstärke,
  Selektoren werden geraten), DMARC (Richtlinie, Berichtsadressen, Fremd-Domain-Autorisierung),
  MTA-STS (Policy gegen echte MX-Einträge geprüft), TLS-RPT, BIMI — mit eigenem 0–100-Punktestand
- **Propagation** — dieselbe Abfrage gegen acht öffentliche Resolver gleichzeitig
- **Reverse-DNS / MX** — PTR mit Vorwärts-Abgleich, MX-Server mit Adressen und Reverse-Namen
- **Sperrlisten** — eine IP gegen 15 öffentliche DNSBL/RBL parallel geprüft, mit Begründungstext
- **SSL/TLS** — Zertifikatskette, Ablaufdatum, Hostname-Abdeckung, ausgehandelte TLS-Version
- **Whois/RDAP** — Registrar, Registrierungs-/Ablaufdatum, Nameserver; RDAP zuerst, WHOIS-Fallback für Endungen ohne RDAP (z. B. .de)
- **HTTP-Header** — Weiterleitungskette, Security-Header, HTTP/3-Ankündigung (Alt-Svc)
- **SMTP** — Banner, EHLO-Fähigkeiten, STARTTLS, Offene-Relais-Test (liefert nie tatsächlich Mail aus)
- **HTTP/3 (QUIC)** — echter Handschlag über UDP/443, nicht nur die Alt-Svc-Ankündigung
- **Ping / Traceroute** — über die System-Werkzeuge im Container
- **DNSSEC** — DS/DNSKEY-Status, ob der Resolver die Antwort validiert (AD-Flag)
- **Monitoring** — Domains/IPs automatisch im gewählten Abstand prüfen (TLS-Ablauf, Sperrlisten,
  Mail-Gesundheit), Benachrichtigung per Mail oder Telegram bei Zustandswechsel
- **Root-Server-Worker** — dieselbe Instanz kann als Ziel für eine zweite dienen: mit fester
  IPv4 und offenem Port 25 laufen Abfragen dort, wo Sperrlisten antworten und SMTP-Tests möglich
  sind, statt hinter einem gewöhnlichen Internetanschluss
- Verlauf, Rate-Limit, Dark/Light · DE/EN · HA Ingress

## Schnellstart

1. Add-on installieren, `password` in den Optionen ändern
2. Optional: zweite Instanz auf einem Root-Server mit fester IPv4 betreiben, dort
   `worker_enabled` und einen zufälligen `worker_token` setzen, und beides bei der
   Zuhause-Instanz unter `worker_url` / `worker_token` eintragen

## Ports

| Port | Funktion |
|------|----------|
| 17798 | NetToolbox Web-UI (direkt, Anmeldung erforderlich) |

## Standalone (ohne Home Assistant, z. B. mit Dockge)

Dasselbe Image läuft auch ohne Supervisor — siehe [docker-compose.yml](docker-compose.yml):

```sh
docker compose up -d
docker compose logs nettoolbox   # zeigt das erzeugte Passwort für "admin"
```

Beim ersten Start legt NetToolbox `data/options.json` selbst an, mit einem zufälligen Passwort
fürs Protokoll. Genau dieselbe Instanz eignet sich als Root-Server-Worker (`worker_enabled` +
`worker_token` in der Datei setzen) oder als Client einer solchen (`worker_url` + `worker_token`).
