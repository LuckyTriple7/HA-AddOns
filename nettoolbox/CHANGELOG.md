# Changelog

## [0.0.6] - 2026-09-03

### Fixed
- **Falscher Alarm bei kurzlebigen Zertifikaten.** Die Ablauf-Bewertung nutzte feste Tagesgrenzen
  (14 / 30 Tage) — bei einem Kurzlebig-Zertifikat mit z. B. 6 Tagen Gesamtlaufzeit (Let's-Encrypt-
  Short-Lived-Profil und ähnliche) meldete das „läuft in 6 Tagen ab — dringend erneuern", obwohl
  frisch ausgestellt und völlig normal. Bewertung läuft jetzt über den *Anteil* der verbleibenden
  Zeit an der Gesamtlaufzeit des Zertifikats (unter 10 % = dringend, unter einem Drittel =
  Warnung — an der üblichen CA-Erneuerungsschwelle orientiert), nicht mehr an absoluten Tagen.
  Ein 90-Tage-Zertifikat mit nur noch 6 Tagen bleibt zu Recht ein echter Alarm (6 %), ein
  6-Tage-Zertifikat mit 6 Tagen Rest jetzt korrekt „OK" (83 %). Kurzlebige Zertifikate (≤15 Tage
  Gesamtlaufzeit) bekommen zusätzlich einen erklärenden Hinweis dazu. Nachgerechnet, nicht nur
  angenommen — vier Fälle durchgespielt (frisch/kurzlebig, spät/kurzlebig, spät/langlebig,
  normal/langlebig), alle vier korrekt eingestuft.

## [0.0.5] - 2026-09-03

### Added
- **SSL/TLS-Zertifikatsprüfung.** Neuer Reiter „SSL/TLS": verbindet sich zu Host (Vorgabe Port
  443, auch host:port), prüft die Kette gegen den Systemspeicher, Ablaufdatum, SAN-Abdeckung und
  ausgehandelte TLS-Version — reine Python-Stdlib (`ssl`-Modul), keine zusätzliche Abhängigkeit.
  Live gegen echte Endpunkte getestet (github.com sowie expired/self-signed/wrong-host von
  badssl.com) — alle vier Fälle korrekt erkannt, inklusive Grund. Bei nicht vertrauenswürdiger
  Kette liefert `getpeercert()` in Python leer zurück (dokumentiertes Verhalten) — Protokoll,
  Chiffre und der genaue Verify-Fehlergrund werden trotzdem angezeigt, nur die Zertifikatsfelder
  selbst nicht; ehrlich als solches gekennzeichnet statt geraten.

### Fixed
- `bad_port` und `ipv6_unsupported` lieferten HTTP 502 statt 400 (fehlten in der
  Fehler-Status-Zuordnung).

## [0.0.4] - 2026-09-03

### Fixed
- **Container startete gar nicht mehr.** `blocklists.py` fehlte in der Dockerfile-COPY-Liste
  (jede Datei einzeln, kein Platzhalter) — `ModuleNotFoundError` beim Start, Neustart-Schleife.

## [0.0.3] - 2026-09-03

### Added
- **Sperrlisten-Check (DNSBL/RBL).** Neuer Reiter „Sperrlisten": eine IP-Adresse gegen 15 öffentliche
  Sperrlisten parallel geprüft (Spamhaus ZEN, SORBS, Barracuda, SpamCop, UCEPROTECT L1–L3, PSBL,
  CBL, Blocklist.de, Mailspike BL/Z, GBUdb, JustSpam, SpamEatingMonkey), mit Begründungstext, wo
  die Liste einen liefert. Alle 15 Zonen vorab live gegen die RFC-5782-Testadresse 127.0.0.2
  verifiziert, nicht nur aus Dokumentation übernommen — dabei zwei reale Fallstricke gefunden und
  abgefangen: SORBS antwortet mit einer festen, listungsunabhängigen Info-Adresse statt einem
  127.x-Code (wird als „nicht auswertbar" erkannt, nicht als Treffer gewertet), und Spamhaus- wie
  CBL-Anfragen über stark genutzte öffentliche Resolver (Quad9, Cloudflare) bekommen oft den
  Meta-Code „öffentlicher Resolver blockiert" zurück statt eines echten Ergebnisses — wird als
  eigener Zustand angezeigt statt fälschlich als sauber oder gelistet. Genau der Fall, für den der
  Root-Server-Worker gedacht ist. Nur IPv4, da fast keine öffentliche Sperrliste IPv6 führt.

## [0.0.2] - 2026-09-03

### Fixed
- **Ladeanzeige blieb nach jedem Ergebnis hängen.** Der Kringel für „Lädt …" wurde vor jeder Anfrage
  eingeblendet, aber beim Eintreffen der Antwort nicht mehr entfernt — das Ergebnis wurde einfach
  darunter angehängt und drehte scheinbar endlos weiter. Betraf alle Reiter außer Mail-Gesundheit.

### Added
- Laufende Anfragen lassen sich abbrechen: Klick auf „Abbrechen" neben dem Ladekringel, oder eine
  neue Anfrage bricht automatisch die noch laufende vorherige ab (verhindert nebenbei, dass eine
  spät eintreffende alte Antwort ein neueres Ergebnis überschreibt).

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
