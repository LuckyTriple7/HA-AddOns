# Changelog

## [0.1.5] - 2026-09-03

### Fixed
- **Passwortfelder im Einstellungen-Dialog schmaler als alle anderen.** `width:100%` galt nur für
  `input[type="text"]`, nicht für `input[type="password"]` — beide Geheimfelder fielen auf die
  Browser-Standardbreite zurück.
- **Zahnrad-Symbol sah aus wie eine Sonne.** Der verwendete Pfad war ein Feather-Icons-Umriss
  (für `stroke`, nicht `fill` gedacht) — als Fläche gefüllt wurden aus den Zähnen einzelne
  Keile statt eines zusammenhängenden Zahnrads. Durch einen echten, für Flächenfüllung gedachten
  Zahnrad-Pfad ersetzt.

## [0.1.4] - 2026-09-03

### Fixed
- **Propagation-Check: dns0.eu-Resolver antwortete nie.** Sowohl die Resolver-IP (193.110.81.0)
  als auch dns0.eus eigene Webseite waren beim Nachtesten von zwei unabhängigen Netzen aus
  komplett unerreichbar (Timeout bzw. Verbindung abgelehnt) — sieht nach echtem Ausfall bei
  dns0.eu aus, nicht nach einem Problem auf einer Seite. Da sich keine aktuelle IP verifizieren
  ließ, ersetzt statt geraten: CleanBrowsing (185.228.168.9), live getestet und schnell.

## [0.1.3] - 2026-09-03

### Fixed
- Einstellungen-Dialog: uneinheitliches Layout — Absender-/Empfängeradresse standen ohne
  erkennbaren Grund nebeneinander, alle anderen Felder einzeln untereinander. Jetzt durchgehend
  einspaltig.

## [0.1.2] - 2026-09-03

### Added
- **Mail/Telegram-Konfiguration in die Oberfläche verlagert.** Zahnradsymbol im Header (wie bei
  TUIWatch) öffnet einen Einstellungen-Dialog für SMTP und Telegram — nicht mehr nur über die
  Home-Assistant-Add-on-Optionen erreichbar. Gespeichert wird in `settings.json` im
  Datenverzeichnis, Passwort und Bot-Token dabei mit einem eigenen Fernet-Schlüssel
  (`settings.key`) verschlüsselt statt im Klartext — genau das Muster aus TUIWatchs
  `settings.py` übernommen. Ein leeres Geheimfeld beim Speichern heißt „unverändert lassen",
  nie „löschen". `cryptography` ist jetzt eine eigene, direkte Abhängigkeit (vorher nur
  transitiv über `aioquic` vorhanden — hätte sonst beim nächsten QUIC-Rückbau die
  Verschlüsselung stillschweigend mitgerissen).
  Add-on-Optionen bleiben als Notzugang für `monitoring_enabled`/`monitoring_poll_seconds`
  bestehen; `smtp_*`/`telegram_*` sind komplett aus `config.yaml` raus, Vorrang beim Lesen:
  Standardwerte < Add-on-Optionen < `settings.json` — ein vorher über die Optionen gesetzter
  Wert bleibt also aktiv, bis er in der Oberfläche überschrieben wird.
- **Bearbeiten-Button für Monitore.** Füllt das Anlegen-Formular mit den aktuellen Werten,
  Button wechselt auf „Änderungen speichern" (PUT statt POST), mit Abbrechen-Möglichkeit.

### Fixed
- Lokal end-to-end getestet: Speichern/Laden der Einstellungen (Secrets verschlüsselt auf
  Platte, `geheim123` nicht im Klartext in der Datei gefunden), „gesetzt"-Anzeige nach dem
  Speichern, Monitor-Bearbeiten über die echte HTTP-API (Umbenennen, Intervall ändern).

## [0.1.1] - 2026-09-03

### Added
- **Echtes HTTP/3 (QUIC) wieder eingebaut.** War in 0.0.10 entfernt worden, weil auf einem
  Netcup-Server per Paketmitschnitt scheinbar eine Netzwerksperre nachgewiesen wurde — stellte
  sich beim Nachtesten als **abgelaufener/falscher AAAA-Eintrag** der geprüften Domain heraus,
  kein Netzwerkproblem. Genau der Fehlertyp, für den der IPv4-Vorzug-Fix aus 0.0.9 gedacht war
  (aioquics eigene Adressauswahl bevorzugt IPv6 ohne Rückfall, hängt bei einer toten Route);
  nur traf es hier den eigenen DNS-Eintrag, nicht den Server. Unverändert aus der Git-Historie
  wiederhergestellt (inklusive beider 0.0.9-Fixes: IPv4-Vorzug über die eigene DNS-Schicht,
  harte äußere Zeitgrenze um den ganzen Handschlag). Erneut live gegen cloudflare.com und
  google.com bestätigt (~25 ms, echte HTTP/3-Antworten).

## [0.1.0] - 2026-09-03

### Added
- **Monitoring mit Benachrichtigung.** Neuer Reiter „Monitoring": beliebig viele Domains/IPs
  automatisch im gewählten Abstand prüfen lassen (SSL/TLS-Ablauf, Sperrlisten, Mail-Gesundheit),
  mit Verlauf pro Monitor. Benachrichtigt nur bei **Zustandswechsel** (ok→warn, warn→fail,
  fail→ok — „wieder repariert" zählt genauso), nicht bei jedem Lauf. Beim allerersten Lauf nur
  bei einem sofortigen `fail` eine Benachrichtigung, ein routinemäßiges `info` (fehlendes BIMI,
  ein einzelner MX — beides normal) setzt still die Basislinie.
  - Zwei Kanäle, beide optional und unabhängig voneinander: **Mail** per SMTP (eigener Server,
    Zugangsdaten in den Add-on-Optionen) und **Telegram** (eigener Bot-Token, unabhängig vom
    Telegram-Add-on dieses Repositorys — kein Installationszwang).
  - Läuft als eigener Hintergrund-Dienst (kein Cronjob nötig), SQLite unter `/data/monitors.db`
    im selben Muster wie crowdpanels Alarm-Archiv (thread-lokale Verbindungen, WAL, ein
    Schreib-Lock) — jeder Thread bekommt seine eigene Verbindung, Flask bedient mehrere Anfragen
    gleichzeitig neben dem Prüf-Thread.
  - Neue Optionen: `monitoring_enabled`, `monitoring_poll_seconds`, `smtp_host/port/user/
    password/from/to/tls`, `telegram_bot_token`, `telegram_chat_id`.
  - Lokal end-to-end getestet: vollständiger CRUD-Zyklus über die echte HTTP-API (Anlegen,
    Auflisten, manuell Ausführen, Verlauf, Ändern, Löschen, 404 nach Löschen), echte TLS-Probe
    gegen github.com, echte Blacklist-/Mail-Gesundheit-Proben, Zustandswechsel-Erkennung,
    Validierungsfehler (unbekannte Prüfung, leeres Ziel).

## [0.0.10] - 2026-09-03

### Removed
- **Echter HTTP/3-Test (QUIC) wieder entfernt.** Beim Testen auf einem echten Netcup-Server
  zeigte sich per Paketmitschnitt zweifelsfrei: ausgehende QUIC-Pakete verlassen den Server
  korrekt (richtige Quell-IP, korrekte Paketgröße, sauberes Retry-Backoff), aber es kommt nie
  eine Antwort zurück — weder von der eigenen Domain noch von cloudflare.com. Lokale und
  Netcup-Cloud-Firewall waren beide aus; die Ursache liegt vermutlich am Netzwerkrand
  (Backbone/DDoS-Schutz filtert eingehendes UDP/443 asymmetrisch, wie bei vielen VPS-Hostern
  üblich) und ist von innerhalb der VM aus nicht behebbar. Damit war die Funktion für den
  eigentlichen Anwendungsfall dauerhaft unbrauchbar — auf Wunsch entfernt. Die zuverlässige
  Alt-Svc-Ankündigungserkennung im HTTP-Header-Reiter bleibt unverändert bestehen, dafür reicht
  ein normaler HTTPS-Request, kein eigener UDP-Roundtrip nötig.
- Abhängigkeit `aioquic` (und damit transitiv `cryptography`, `pylsqpack`, `service_identity`)
  wieder aus `requirements.txt` entfernt.

## [0.0.9] - 2026-09-03

### Fixed
- **Ladekringel blieb im Fehlerfall überall hängen — nicht nur bei HTTP/3.** Alle 16 Fehlerpfade
  der Oberfläche hängten die Fehlermeldung nur unter den Kringel, statt ihn zu ersetzen (derselbe
  Bug wie in 0.0.2, diesmal im `catch`-Zweig statt im Erfolgspfad — betraf jeden einzelnen Reiter
  seit der ersten Version, fiel aber erst jetzt auf, weil frühere Tests direkt gegen die JSON-API
  liefen statt gegen den echten Browser-DOM). Der tote „Abbrechen"-Link daneben tat nichts mehr,
  weil die Anfrage längst durch war.
- **Echtes HTTP/3 konnte hängen bleiben, auch gegen Server, die HTTP/3 wirklich sprechen.**
  `aioquic.connect()` löst den Host über ein eigenes, unge­filtertes `getaddrinfo()` auf und nimmt
  das erste Ergebnis — ohne Happy-Eyeballs, ohne IPv4-Vorzug (im Quellcode nachgeschaut, nicht
  angenommen). Bekam der Host eine IPv6-Antwort zuerst und der Container hatte kein echtes
  IPv6-Routing, blieb die QUIC-Verbindung tot, während die Alt-Svc-Erkennung über `requests`
  (die IPv4 zuverlässiger bevorzugt) weiterhin funktionierte — genau das gemeldete Bild. Jetzt
  wird die Adresse vorher gezielt über die eigene DNS-Schicht als A-Eintrag aufgelöst (AAAA nur
  als Rückfall, wenn wirklich keine IPv4-Adresse existiert) und aioquic bekommt die fertige
  Adresse statt selbst zu raten. Zusätzlich eine harte äußere Zeitgrenze um den ganzen Handschlag
  gelegt (nicht nur um die Antwort danach) — falls der interne `idle_timeout` aus irgendeinem
  Grund nicht feuert, kann die Anfrage jetzt nicht mehr unbegrenzt hängen bleiben.

## [0.0.8] - 2026-09-03

### Added
- **Echtes HTTP/3 (QUIC).** Zweiter Button im HTTP-Header-Reiter: echter QUIC-Handschlag über
  UDP/443 plus eine HTTP/3-Anfrage (`aioquic`), nicht nur die Alt-Svc-Ankündigung. Die
  Wheel-Sorge aus 0.0.7 (Alpine + Python 3.14) war unbegründet — live gegen PyPI geprüft: sowohl
  `aioquic` als auch `cryptography` und die transitive Abhängigkeit `pylsqpack` haben
  `abi3`+`musllinux`-Wheels für amd64 und aarch64, keine Kompilierung im Image nötig. Jede
  benutzte aioquic-API (H3Connection, QuicConnectionProtocol, ProtocolNegotiated-Event, …) wurde
  vor dem Schreiben gegen die echte installierte Bibliothek geprüft, nicht aus der Erinnerung
  übernommen. Live gegen cloudflare.com und google.com getestet (echte Handschläge, ~25 ms,
  echte HTTP/3-Antworten mit Status und Inhalt).
- **Ping / Traceroute.** Als weitere Karten im bestehenden „Netzwerk-Tools"-Reiter (vormals
  „Reverse / MX") statt neuer Nav-Punkte — die Leiste hat genug Einträge. Ruft die
  System-Programme `ping` (iputils) und `traceroute` im Container auf statt eigene ICMP-Sockets
  zu bauen; die Standard-Capabilities des Containers reichen dafür, live bestätigt. Live gegen
  echte Ziele getestet, dabei einen Parsing-Bug gefunden: `"4.633 ms"` sind bei traceroute zwei
  durch Leerzeichen getrennte Tokens, keins — die Laufzeit blieb dadurch immer leer.

### Changed
- Reiter „Reverse / MX" heißt jetzt „Netzwerk-Tools" (deckt jetzt auch Ping/Traceroute ab).

## [0.0.7] - 2026-09-03

### Added
- **Whois/RDAP.** Neuer Reiter „Whois": RDAP zuerst (JSON, Server über die IANA-Bootstrap-Liste
  gefunden — genau wie jeder RDAP-Client), klassisches WHOIS (Port 43) als Fallback für Endungen
  ohne RDAP-Server. `.de` ist der auffälligste Fall: DENIC betreibt bis heute kein öffentliches
  RDAP (live gegen die echte IANA-Liste geprüft, nicht angenommen) und gibt über das
  Whois-Protokoll aus Datenschutzgründen weder Registrar noch irgendein Datum heraus — nur
  Nameserver und Status. Wird dem Nutzer als genau das erklärt, nicht als Fehler des Tools.
  Zwei echte Bugs beim Testen gegen echtes DNS gefunden: DENICs Kurzantwort ohne `-T dn`-Flag
  enthält keine Nameserver (jetzt per Sonderfall behandelt), und alle Feld-Regexe (Registrar,
  Datumsfelder) fehlte `re.M` — `^`/`$` griffen dadurch nie bei mehrzeiligem Text.
- **HTTP-Header-Analyse + HTTP/3-Signal.** Neuer Reiter „HTTP-Header": folgt der
  Weiterleitungskette von Hand (jeder Sprung einzeln über den bestehenden SSRF-Schutz geprüft —
  ein Server kann NetToolbox über eine Weiterleitung nicht ins eigene Netz locken), listet die
  gängigen Security-Header (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy,
  Permissions-Policy) mit eigenem 0–100-Punktestand, meldet preisgegebene Server/Technologie-
  Header. HTTP/3 wird nur über den Alt-Svc-Header (RFC 7838) als **Ankündigung** erkannt, kein
  echter QUIC-Verbindungsaufbau — bewusst, da eine echte Prüfung `aioquic`+`cryptography`
  bräuchte und Alpine mit sehr neuem Python (3.14) ein unsicheres Wheel-Risiko ist. Klar als
  Ankündigungs-Erkennung gekennzeichnet, nicht als Verbindungsnachweis.
- **SMTP-Test.** Neuer Reiter „SMTP": Banner, EHLO-Fähigkeiten, STARTTLS (nur Protokoll/Chiffre
  gemeldet, keine Zertifikatsvertrauensprüfung — anders als beim SSL/TLS-Reiter ist ein
  selbstsigniertes Zertifikat bei opportunistischem STARTTLS auf Port 25 normal), Banner-vs-PTR-
  Abgleich, und ein Offene-Relais-Test. Der Relais-Test sendet MAIL FROM + RCPT TO an eine
  Adresse unter example.com (IANA-reservierte Test-Domain, RFC 2606) und danach immer RSET/QUIT
  — **niemals DATA**, es wird also nie tatsächlich eine Mail zugestellt, egal wie der Server
  antwortet. Dieselbe Technik, die jedes seriöse Mailserver-Prüfwerkzeug seit jeher verwendet.
  Live gegen Googles und mailbox.orgs echte MX-Server getestet (beide korrekt: STARTTLS zu
  TLS 1.3, Relais korrekt geschlossen). Dabei einen echten smtplib-Stolperstein gefunden: der
  private `_host`-Attributwert wird nur vom Konstruktor selbst gesetzt, nicht von einem separat
  aufgerufenen `.connect()` — STARTTLS brauchte ihn für SNI und schlug sonst mit einer kryptischen
  ValueError fehl.

### Fixed
- `http_get()` erlaubte bisher nur `https://` — für die Weiterleitungs-Verfolgung (z. B. HTTP→
  HTTPS-Redirect prüfen) musste auch `http://` möglich sein.

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
