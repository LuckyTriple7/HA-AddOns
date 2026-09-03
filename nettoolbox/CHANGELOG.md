# Changelog

## [0.0.1] - 2026-09-03

### Added
- Erste Fassung. DNS-Abfragen (A/AAAA/MX/NS/TXT/CNAME/SOA/PTR/SRV/CAA/DS/DNSKEY/TLSA/NAPTR/SPF),
  Abfrage aller Standard-Typen in einem Rutsch, DNS-Propagation über acht öffentliche Resolver,
  Reverse-DNS mit Vorwärts-Abgleich, DNSSEC-Status (DS/DNSKEY/AD-Flag), SOA-Seriennummer je
  Nameserver mit Sync-Check.
- Mail-Gesundheit in einem Durchgang: SPF (inklusive Lookup-Zähler nach RFC 7208 und
  Include-Kettenauflösung), DKIM (RSA/Ed25519-Schlüsselprüfung, häufige Selektoren werden
  automatisch geraten), DMARC (Richtlinie, Berichtsadressen, Autorisierungsprüfung fremder
  rua/ruf-Domains), MTA-STS (Policy-Datei wird geladen und gegen die echten MX-Einträge
  abgeglichen), TLS-RPT, BIMI (inklusive Logo-Abruf). Eigener 0–100-Punktestand je Domain.
- **Root-Server-Worker.** Dasselbe Image kann als Ziel für eine zweite Instanz dienen: Wer eine
  feste IPv4 mit offenem Port 25 hat, schaltet dort `worker_enabled` mit einem Zugriffsschlüssel
  ein und trägt Adresse plus Schlüssel bei der Zuhause laufenden Instanz unter `worker_url` /
  `worker_token` ein. Alle Abfragen laufen dann über den Root-Server — wichtig für
  Sperrlisten-Abfragen (viele beantworten öffentliche Resolver nicht) und künftige SMTP-Prüfungen
  (Port 25 ist bei den meisten Internetanschlüssen zu Hause gesperrt).
- SSRF-Schutz: Abfragen gegen private, Loopback- und Link-lokale Adressen sind gesperrt, sofern
  nicht `allow_private_targets` ausdrücklich eingeschaltet ist — sonst würde jede Instanz zu
  einem offenen Scan-Proxy ins eigene Netz.
- Verlauf der letzten Prüfungen, Rate-Limit je Minute, DE/EN, Dark/Light, HA Ingress, direkter
  Port mit eigener Anmeldung (Benutzername/Passwort, CSRF, Rate-Limit auf Fehlversuche).
- `docker-compose.yml` für Standalone-Betrieb (Dockge & Co.): Beim ersten Start ohne Supervisor
  legt NetToolbox `data/options.json` selbst mit einem zufälligen Passwort an und schreibt es
  ins Protokoll — kein manuelles Anlegen der Datei mehr nötig.

### Noch nicht enthalten (geplante nächste Schritte)
- SMTP-Test (Banner, STARTTLS, Open-Relay, Reverse-Match) — braucht offenen Port 25, sinnvoll
  vor allem über den Root-Server-Worker.
- Sperrlisten-Check (RBL/DNSBL) gegen die üblichen rund 100 Listen.
- SSL/TLS-Zertifikatsprüfung, HTTP-Header-Analyse, Whois/RDAP.
- Geplantes Cron-Monitoring mit Home-Assistant-Sensoren bei Änderungen.
