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
- **DNSSEC** — DS/DNSKEY-Status, ob der Resolver die Antwort validiert (AD-Flag)
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

## Standalone (ohne Home Assistant)

Dasselbe Image läuft auch ohne Supervisor — Optionen kommen dann über Umgebungsvariablen statt
`/data/options.json`:

```sh
docker run -d --name nettoolbox -p 17798:17798 \
  -e NETTOOLBOX_OPTIONS=/config \
  -v /pfad/zu/config:/config \
  ghcr.io/luckytriple7/nettoolbox
```

`/config/options.json` muss dabei existieren (siehe `dev_run.py` für ein Beispiel).
