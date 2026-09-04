# Changelog

## [0.1.30] - 2026-09-04

### Added
- **Wächter erscheinen als Entitäten in Home Assistant.** Je Wächter ein `sensor.nettoolbox_<name>`
  mit dem Zustand (`ok`/`info`/`warn`/`fail`) und den Einzelheiten als Attribute — Prüfung, Ziel,
  Zusammenfassung, Intervall, Zeitpunkt der letzten Prüfung. Dazu `sensor.nettoolbox_probleme`
  (Anzahl der Wächter auf Achtung oder Kritisch, mit Namensliste) und
  `binary_sensor.nettoolbox_problem` mit `device_class: problem`. Damit lassen sich die Zustände
  auf Dashboards zeigen und in Automationen verwenden, statt nur per Mail oder Telegram zu melden.
- Geschrieben wird über die Core-API des Supervisors (`homeassistant_api: true`), also ohne MQTT
  und ohne Broker. Sofort nach jeder Änderung an einem Wächter und zusätzlich jede Minute, weil
  auf diesem Weg gesetzte Zustände einen Neustart von Home Assistant nicht überleben und danach
  von selbst wieder auftauchen müssen.
- Abschaltbar über die neue Option **`ha_sensors`** (Vorgabe an). Außerhalb des Supervisors
  passiert ohnehin nichts; im Monitoring-Reiter steht der Hinweis nur dann, wenn wirklich
  geschrieben wird.
- Lehnt Home Assistant die Entitäten ab, sagt das Protokoll das **einmal** deutlich (samt
  Verweis auf `homeassistant_api`) statt stillschweigend nichts zu tun.

## [0.1.29] - 2026-09-04

### Added
- **EHLO-Antwort wird angezeigt.** Die erste Zeile der EHLO-Antwort wurde bisher weggeworfen —
  dabei ist sie oft das Einzige, was ein Server über sich verrät, wenn das Banner anonymisiert
  wurde („… Hello host [ip], **pleased to meet you**" ist sendmails Wortlaut).
- **Stilerkennung als letzte Instanz.** Sagen weder Banner noch EHLO-Erweiterungen etwas, wird
  der Wortlaut der Begrüßung ausgewertet und ausdrücklich als „sendmail-Stil (kein Nachweis)"
  ausgegeben — mehrere Mailserver haben sendmails Formulierungen übernommen, das ist ein
  Stilhinweis und kein Produktnachweis.
- **EHLO-Fähigkeiten nach STARTTLS.** Viele Server zeigen erst im verschlüsselten Kanal mehr,
  vor allem AUTH samt Mechanismen; die zusätzliche Liste fließt in die Software-Erkennung ein
  (bei STRATO kommt so z. B. `requiretls` dazu).

## [0.1.28] - 2026-09-04

### Added
- **Zertifikatsangaben auch für nicht vertrauenswürdige Zertifikate.** Bisher blieben Aussteller,
  Name, Seriennummer und Laufzeit leer, sobald die Prüfung fehlschlug — genau im interessantesten
  Fall also. Grund war eine Einschränkung von `getpeercert()`, das ohne Verifizierung ein leeres
  Wörterbuch liefert. Das rohe Zertifikat wird jetzt mit `cryptography` (ohnehin schon
  Abhängigkeit für die verschlüsselten Einstellungen) in dieselbe Form gebracht. Ein Fragezeichen
  an der Karte sagt dazu, dass die Angaben aus einem nicht bestandenen Zertifikat stammen.
- **Erkennung von Platzhalter-Zertifikaten.** Selbst ausgestellt, kein passender Name, Laufzeit
  über zehn Jahre — das ist das Standardzertifikat eines Webservers oder Reverse-Proxys, weil für
  den Namen kein Host eingerichtet ist. Statt eines nackten „selbstsigniert" steht das jetzt als
  Diagnose da (geprüft an gizmonet.eu: NPMplus antwortet mit CN `*`, gültig bis 3026).
- Eine Laufzeit von über zehn Jahren wird als eigener Hinweis gemeldet, statt als grünes
  „noch 364996 Tage gültig" durchzugehen.

### Fixed
- Beschriftung „Aussteller für" hieß richtig **„Ausgestellt für"**.

## [0.1.27] - 2026-09-04

### Added
- **DNS-Momentaufnahme & Vergleich** (neue Karte im DNS-Reiter, `snapshots.py`). Hält den
  Zonenstand fest — A, AAAA, MX, NS, TXT, SOA, CAA, DS am Apex plus `www` und `_dmarc`, den
  beiden Namen, an denen sich in der Praxis am häufigsten unbemerkt etwas ändert — und zeigt
  später, was anders ist.
- Verglichen wird wahlweise **gegen den jetzigen Stand** oder **gegen eine zweite Aufnahme**;
  das Ergebnis steht als Zeilendiff da (`−` alt, `+` neu), immer von der älteren zur neueren
  Aufnahme, egal in welcher Reihenfolge man sie auswählt.
- TTL-Änderungen zählen bewusst nicht als Änderung — eine von 3600 auf 3599 heruntergelaufene
  TTL ist kein Ereignis.
- Eigene SQLite-Datei `snapshots.db` nach dem Muster des Monitor-Speichers (eine Verbindung je
  Thread, WAL, Schreibsperre). Bis zu 30 Aufnahmen je Domain und 500 insgesamt, ältere fallen
  beim Speichern heraus. Der Speicher hängt nicht am Monitoring und steht auch dann bereit,
  wenn kein Wächter eingerichtet ist.
- Eine einzelne fehlgeschlagene Abfrage wird als Zeile mit Fehlercode aufgenommen, statt die
  ganze Momentaufnahme scheitern zu lassen.

## [0.1.26] - 2026-09-04

### Added
- **Gesamtbericht für eine Domain.** Neuer erster Reiter „Bericht": eine Eingabe, neun Prüfungen
  — DNS, DNSSEC, Whois, Mail-Gesundheit, MX, TLS, HTTP, SEO und Sperrlisten für die erste
  A-Adresse — auf einem Blatt, mit Gesamturteil und je Prüfung einer Kennzahl (Punktestand,
  Restlaufzeit, Status, gefundene Sperrlisten).
- Ausführung läuft parallel über vier Arbeiter (`/api/report`); gegen echte Domains 1–2 Sekunden
  statt der Summe aller Einzelläufe. Jede Teilprüfung zählt einzeln gegen das Rate-Limit, damit
  der Bericht kein Weg daran vorbei ist.
- Eine fehlgeschlagene Teilprüfung erscheint als Zeile im Bericht und reißt nie den ganzen
  Bericht mit — dieselbe Regel wie beim Monitoring.
- **Markdown-Export.** Knopf „Als Markdown speichern" erzeugt aus dem Ergebnis ein Dokument
  (Überschrift je Prüfung, Kennzahl, alle Funde mit Stufe) und lädt es als
  `nettoolbox-<domain>.md` herunter — zum Weiterreichen oder Archivieren.
- Der Bericht ist jetzt die Startansicht; DNS und die übrigen Reiter bleiben unverändert einen
  Klick entfernt.

## [0.1.25] - 2026-09-04

### Added
- **Drei neue Wächter im Monitoring:**
  - **Domain-Ablauf** — meldet eine auslaufende Registrierung ab 30 Tagen Restlaufzeit, per Mail
    oder Telegram wie die übrigen Wächter. Die Restlaufzeit rechnete `domaininfo.py` schon aus,
    es fehlte nur der Wächter drumherum.
  - **Erreichbarkeit** — HTTP-Status und Weiterleitungsziel einer Adresse.
  - **SEO-Punktestand** — schlägt an, wenn der Wert kippt (etwa weil ein Deployment `noindex`
    stehen lässt oder die Sitemap verschwindet).
- Beim Domain-Ablauf steht direkt im Formular, wo die Grenze liegt: **.de (DENIC) und .eu
  (EURid) veröffentlichen kein Ablaufdatum**, dort kann der Wächter nichts melden. Bei
  .com/.net/.org und den meisten neuen Endungen funktioniert er (live geprüft: github.com,
  noch 35 Tage).

### Fixed
- Fehlt das Ablaufdatum, sagt die Whois-Prüfung das jetzt ausdrücklich als Hinweis, statt es
  stillschweigend leer zu lassen — sonst sieht ein Domain-Wächter für .de aus, als sei alles
  geprüft.
- **.eu-Whois: Registrar wurde als „Name: netcup GmbH" ausgegeben.** EURid schreibt „Registrar:"
  in eine eigene Zeile und den Namen eingerückt darunter; das Präfix wird jetzt abgeschnitten.

## [0.1.24] - 2026-09-04

### Added
- **Austragungs-Links bei Sperrlisten-Treffern.** Jede Zone kennt jetzt die Abfrage- bzw.
  Delisting-Seite ihres Betreibers; bei einem Treffer steht der Link direkt neben dem
  Listennamen. Jede Adresse wurde vor der Aufnahme abgerufen — wo die Seite nicht bestätigt
  werden konnte (GBUdb), steht bewusst kein Link statt eines geratenen.
- **Testsuite** unter `tests/` (55 Tests, `python3 -m pytest tests -q`). Deckt die reinen
  Funktionen ab: Eingabe-Validierung, Anbieter- und Software-Erkennung inklusive des Falls
  `google.com.angreifer.net` (Suffix statt Teilstring), SMTP-Zielparsing, Ping-Ausgabe-Muster,
  den SEO-HTML-Parser samt Punktestand und die Schlüsselgleichheit beider Sprachdateien. Kein
  Test braucht Netz.

### Changed
- **Platzhalter aller Eingabefelder werden übersetzt** (17 Felder). Vorher stand in der
  englischen Oberfläche deutscher Text („example.com **oder** 203.0.113.10").
- **SORBS entfernt.** Der Dienst ist eingestellt, sorbs.net löst nicht mehr auf, und die Zone
  beantwortet inzwischen jede Abfrage — auch die RFC-5782-Testadresse — mit derselben festen
  Nicht-127er-Adresse. Sie konnte also gar kein echtes Ergebnis mehr liefern und kostete nur
  eine Abfrage. Damit 14 statt 15 Zonen.

### Fixed
- **Monospace-Text bricht nicht mehr mitten im Wort** (`overflow-wrap: anywhere` statt
  `word-break: break-all`). Betraf jede Tabelle und jede Ergebniskarte — sichtbar zuletzt in der
  SMTP-Banner-Box als „hornetsecurit/y.com".

## [0.1.23] - 2026-09-04

### Added
- **SEO-Check.** Neues Modul `seocheck.py`, Probe `seo`, eigene Karte im Reiter HTTP-Header —
  dieselbe Adresse, dieselbe geschützte HTTP-Schicht (SSRF-Guard, Weiterleitungskette,
  Größenlimit) wie die HTTP-Prüfung darüber. Gelesen wird mit `html.parser` aus der
  Standardbibliothek; keine neue Abhängigkeit im Image.
  - **Grundlagen:** Titel (30–60 Zeichen), Meta-Description (70–160), Canonical, `lang`,
    Zeichensatz, Viewport, `robots`-Meta (noindex/nofollow).
  - **Struktur:** genau eine H1, übersprungene Überschriften-Ebenen, Wortzahl, Bilder ohne
    Alternativtext (ein leeres `alt=""` gilt korrekt als gewollt dekorativ).
  - **Crawling:** robots.txt inklusive „sperrt alle Crawler", Sitemap aus robots.txt oder
    `/sitemap.xml` mit Anzahl der Adressen, hreflang-Verweise.
  - **Technik:** Status, Antwortzeit, Seitengröße, Weiterleitungen, Kompression, Cache-Control,
    Open Graph, Twitter Cards, JSON-LD-Typen, Mixed Content (http-Ressourcen auf https-Seiten).
  - Eigener 0–100-Punktestand nach dem Muster der Mail-Gesundheit, Hinweis-Funde kosten nichts.
- Ehrlich benannte Grenzen: Core Web Vitals, Rankings und Backlinks sind nicht dabei (echter
  Browser bzw. kostenpflichtige Dienste nötig), und beurteilt wird das ausgelieferte HTML — was
  erst JavaScript aufbaut, erscheint als „wenig Text", genau wie bei einem Crawler ohne
  JavaScript. Wird die Seite größer als 512 KB, sagt ein eigener Hinweis, dass nur der obere
  Teil ausgewertet wurde.
- Gzip-komprimierte Sitemaps (`.gz`) werden übersprungen und `/sitemap.xml` immer zusätzlich
  probiert — heise.de nennt sieben Sitemaps in der robots.txt, sechs davon `.gz`, und die erste
  davon antwortet mit 404.

### Changed
- `httpcheck._normalise_url` / `_follow` heißen jetzt `normalise_url` / `follow_redirects`, da
  sie von `seocheck.py` mitbenutzt werden.

## [0.1.22] - 2026-09-04

### Changed
- **Alles zum Thema Mail sitzt jetzt in einem Reiter.** Mail-Gesundheit, MX-Server, SMTP-Server
  und Sperrlisten lagen quer über die Leiste verteilt, dazwischen DNS-, TLS- und HTTP-Reiter.
  Sie stehen jetzt als vier Karten untereinander im Reiter **Mail**, in der Reihenfolge, in der
  man sie beim Nachsehen braucht: Gesamtbild, MX, Server-Direkttest, Ruf der IP.
- Die Navigationsleiste schrumpft dadurch von zwölf auf zehn Einträge; die Reiter "SMTP" und
  "Sperrlisten" entfallen als eigene Punkte.
- Die MX-Karte hat ein eigenes Symbol bekommen (Posteingang statt Briefumschlag), damit sie sich
  in der neuen Nachbarschaft von der Mail-Gesundheit unterscheidet.

## [0.1.21] - 2026-09-04

### Added
- **mailcow-Banner wird erkannt.** mailcow setzt Postfix' `mail_name` auf "Postcow", das Banner
  nennt also nie "Postfix", obwohl genau das darunter läuft — die Software-Erkennung stand
  deshalb auf "nicht erkannt". Neues Muster, Ausgabe: `Postfix (mailcow)`.
- **Quelladresse der SMTP-Prüfung wird angezeigt** ("Geprüft von 10.0.0.5 → 203.0.113.10"). Für
  den Relay-Test ist das die entscheidende Angabe, siehe unten.

### Fixed
- **Falscher Offene-Relais-Alarm, wenn Add-on und Mailserver auf derselben Maschine laufen.**
  Mailserver stufen ihr eigenes Netz üblicherweise als vertrauenswürdig ein (Postfix
  `mynetworks`) und nehmen von dort Post für fremde Domains an. Aus dieser Nähe sieht das
  identisch zu einem offenen Relais aus, sagt über die Erreichbarkeit aus dem Internet aber
  nichts.
  - Quelle == Ziel derselben Verbindung: statt rotem "Relay offen" jetzt die Warnung "Relay
    offen — von hier aus" mit der Erklärung und dem Rat, von außen zu prüfen.
  - Quelle ist eine private Adresse (NAT oder Container): der Fund bleibt kritisch, bekommt aber
    einen Hinweis danebengestellt, dass eine Prüfung aus einem fremden Netz nötig ist, falls
    Add-on und Mailserver dieselbe Maschine oder dasselbe Docker-Netz teilen.

## [0.1.20] - 2026-09-04

### Added
- **SMTP-Prüfung nimmt jetzt einfach eine Domain.** Bisher musste der Hostname des Mailservers
  von Hand herausgesucht und eingetippt werden — den kennt aber niemand auswendig. Wird eine
  Domain eingegeben, folgt die Prüfung selbst dem MX-Eintrag und verbindet sich mit dem MX-Host
  niedrigster Priorität, genau wie ein sendender Mailserver es täte. Ein Chip "MX-Host: …" und
  ein Hinweis-Fund zeigen, welcher Server tatsächlich angesprochen wurde; bei mehreren MX werden
  alle als Chips gelistet.
- Ein ausdrücklicher Port (`host:587`) und eine IP-Adresse werden unverändert direkt angesteuert
  — Submission-Ports liegen am Host selbst und nie am MX-Eintrag.

### Fixed
- **Domains ohne Mailserver liefern jetzt eine klare Auskunft statt einer fehlgeschlagenen
  Prüfung.** Zwei Fälle, beide mit eigenem Text:
  - Null-MX nach RFC 7505 (ein einzelner MX auf `.`, wie bei example.com) — die Domain erklärt
    damit ausdrücklich, keine Mail anzunehmen. Vorher lief das in ein irreführendes
    "Host lässt sich nicht auflösen", weil der leere MX-Name an den Resolver ging.
  - Weder MX noch eigene A/AAAA-Adresse — hier ist schlicht kein Mailserver eingetragen.

## [0.1.19] - 2026-09-04

### Changed
- **Dockge-Anleitung als echte Schritt-für-Schritt-Fassung (DE und EN).** Bisher stand dort nur
  der Pfad `/opt/stacks/<stack>/data/`; jetzt fünf nummerierte Schritte vom Anlegen des Stacks
  über das Ablesen des erzeugten Passworts bis zu `chmod 600` auf die `options.json`.
- **Eigener Abschnitt "Worker-Optionen in der options.json setzen"** mit vollständigem
  JSON-Beispiel für die ausführende Seite (`worker_enabled` + `worker_token`, `worker_url`
  bleibt leer) und dem Gegenstück für den umgekehrten Fall. Der Schlüssel wird vorher per
  `openssl rand -hex 32` erzeugt, statt im JSON-Beispiel versteckt zu sein.

## [0.1.18] - 2026-09-04

### Changed
- **Dokumentation zum Root-Server-Worker neu geschrieben (DE und EN).** Der bisherige Text
  beschrieb nur *wie* man den Worker einrichtet, nicht *ob* man ihn überhaupt braucht — mit dem
  Ergebnis, dass eine einzelne Instanz auf einem Root-Server so aussah, als fehle ihr noch eine
  Einstellung. Neuer Abschnitt "Brauche ich den Root-Server-Worker?" mit klarer Antwort: bei nur
  einer Instanz, egal wo sie läuft, bleiben alle `worker_*`-Optionen leer, und die Statusanzeige
  "Lokal" ist der gewünschte Zustand. Der Worker ist ausschließlich die Krücke für eine
  Heim-Instanz hinter einem gesperrten Port 25.
- Einrichtung jetzt als Zwei-Seiten-Tabelle: was auf dem Root-Server und was im
  Home-Assistant-Add-on einzutragen ist, samt Hinweis auf `worker_disabled` als Antwort einer
  Gegenseite ohne `worker_enabled`, und auf den Token, der über http im Klartext mitläuft.
- Optionsbeschreibungen in `translations/de.yaml` und `en.yaml` entsprechend geschärft:
  `worker_url` ist ausdrücklich optional, `worker_enabled` gehört auf die ausführende Seite.
- Standalone-Abschnitt um die Dockge-Pfade ergänzt (`/opt/stacks/<stack>/data/options.json`) und
  um den Hinweis, dass Änderungen an `options.json` sofort greifen.

### Fixed
- **Falsche Angabe zum erzeugten Passwort korrigiert.** README (DE/EN) und der Kommentarkopf der
  `docker-compose.yml` verwiesen auf `docker compose logs` als Fundort — das Passwort steht aber
  bewusst nur in `data/options.json` und nie im Protokoll.

## [0.1.17] - 2026-09-04

### Fixed
- **Statusanzeige unterscheidet jetzt drei Zustände statt zwei.** Auf dem Root-Server stand in
  der Kopfzeile ebenfalls "Lokal", obwohl diese Instanz gerade die Worker-Rolle ausfüllt — sie
  führt ihre eigenen Prüfungen ja tatsächlich lokal aus, und nur das war bisher abgefragt. Ist
  `worker_enabled` an, zeigt die Anzeige jetzt **"Worker-Modus"**. "Worker verbunden" bleibt der
  Zustand der Heim-Instanz, die ihre Prüfungen dorthin auslagert.
- Die Anzeige hat einen Tooltip bekommen, der den jeweiligen Zustand in einem Satz erklärt (bei
  "Worker verbunden" samt Worker-Adresse).
- Ein fehlerhaftes lokales Backend zeigte trotz roter Anzeige weiter "Lokal" (die Textauswahl
  hatte in beiden Zweigen denselben Wert stehen); jetzt "Lokal — Fehler".

## [0.1.16] - 2026-09-04

### Added
- **Anbieter- und Software-Erkennung.** Neues Modul `mailprovider.py` (rein rechnend, keine
  eigenen Netzabfragen) beantwortet zwei Fragen aus Daten, die die bestehenden Prüfungen ohnehin
  holen:
  - *Wer betreibt den Mailserver?* — aus den MX-Hostnamen, weil die pro Produkt fest sind
    (alles unter `mail.protection.outlook.com` ist Microsoft 365, egal welche Domain davor steht).
    Rund 70 Muster: Google Workspace, Microsoft 365, IONOS, STRATO, ALL-INKL, Netcup, Hetzner,
    GMX/WEB.DE, mailbox.org, Posteo, Proton, Fastmail, Zoho, Amazon SES/WorkMail, Cloudflare
    Email Routing, Mimecast, Proofpoint, Hornetsecurity, Barracuda, OVH, Gandi, GoDaddy u. a.
    Abgleich immer als Suffix, nie als Teilstring — `google.com.angreifer.net` matcht nicht.
  - *Welche Software läuft dort?* — aus dem SMTP-Banner (Postfix, Exim, Sendmail, Microsoft
    Exchange, OpenSMTPD, Haraka, Zimbra, RZmta, qmail, Stalwart, MDaemon, Kerio, IceWarp u. a.,
    inkl. Version wenn genannt), ersatzweise aus herstellerspezifischen EHLO-Erweiterungen
    (`XEXCH50` → Exchange), wenn das Banner nichts verrät.
- Angezeigt wird das an drei Stellen: Zeile "Erkannter Betreiber" in der MX-Karte und in der
  Mail-Gesundheit, sowie Chips (Betreiber + Software) und eine Zeile "Software" in der
  SMTP-Karte.
- Beides ist ausdrücklich nur eine Vermutung und färbt keine Ampel: ein Banner ist frei
  wählbarer Text, und ein selbst gehosteter Server passt auf kein MX-Muster — der wird als
  "kein bekannter Anbieter — vermutlich selbst gehostet" ausgewiesen.

## [0.1.15] - 2026-09-04

### Fixed
- **IP-Lookup: Zeilenlayout aufgeräumt.** Die Wertespalte hing an `.kv` (Flex mit
  `space-between`) und an `.mono` mit `word-break: break-all` — dadurch standen die Werte
  rechtsbündig auf wechselnden Positionen und Wörter wurden mitten drin umbrochen
  ("Baden-Württem/berg", "Stiegeler Internet S/ervice GmbH"). Jetzt eigenes Raster mit fester
  Beschriftungsspalte (106px), linksbündigen Werten und Umbruch nur an Wortgrenzen. Monospace
  bleibt den technischen Werten (Zeitzone, Koordinaten, AS, PTR) vorbehalten, Orts- und
  Firmennamen laufen als normaler Text. Die beiden Unterkarten bekommen zudem ein breiteres
  Raster (320px statt 230px Mindestbreite), damit Anbieternamen in eine Zeile passen.

## [0.1.14] - 2026-09-04

### Added
- **IP-Lookup (Standort & Betreiber).** Neue Karte in der Sektion "Reverse/IP": IP-Adresse oder
  Domainname eingeben und Geolocation (Land, Region, Ort, PLZ, Zeitzone, Koordinaten), Anbieter,
  Organisation und AS-Nummer direkt im Add-on anzeigen. Datenquelle ist ip-api.com (kostenlos,
  ohne Schlüssel, rund 45 Abfragen pro Minute) — deshalb eine Abfrage pro Klick, kein Polling.
  Ein Domainname wird vorher per DNS aufgelöst (A vor AAAA), der PTR-Name kommt aus den eigenen
  konfigurierten Resolvern statt aus ip-apis `reverse`-Feld (das dort eine zusätzliche
  rDNS-Abfrage auslöst und die Antwort merklich verlangsamt).
- **Button "Eigene IP".** Leere Abfrage an ip-api.com zeigt die öffentliche Adresse, mit der die
  laufende Instanz nach außen geht — zu Hause die des Anschlusses, im Worker-Modus die des
  Root-Servers.
- Einstufung als Rechenzentrum/Hosting, Mobilfunknetz oder Proxy/VPN/Tor wird mit ausgegeben;
  Proxy/VPN ist eine Warnung, Hosting und Mobilfunk bleiben reine Hinweise und färben die Ampel
  nicht.
- Private und reservierte Adressen werden gar nicht erst an ip-api.com geschickt, sondern als
  Warnung mit PTR-Ergebnis beantwortet.

## [0.1.13] - 2026-09-03

### Added
- **Traceroute: ICMP statt UDP.** Neue Checkbox "ICMP statt UDP" — schaltet `-I` an (ICMP-Echo-
  Sonden statt traceroutes UDP-Standard). Anlass: eine Cloud-Firewall, die nur ICMP durchlässt und
  UDP komplett verwirft, ließ Traceroute scheitern, obwohl die ICMP-Regeln (ein-/ausgehend, v4+v6)
  korrekt standen. `-I` braucht hier keine Zusatzrechte (live geprüft, unprivilegiert lauffähig,
  genau wie schon Pings Raw-Socket). Live gegen 1.1.1.1 getestet: mit `-I` `reached: true`.

## [0.1.12] - 2026-09-03

### Added
- **Ping und Traceroute in getrennte Boxen aufgeteilt.** Bisher ein Kasten mit zwei Buttons (einer
  grün, einer nicht) und gemeinsamem Zielfeld/Ergebnisbereich — jetzt zwei eigenständige Karten,
  je mit eigenem Ziel-Feld und Ergebnisbereich.
- **Dauerping.** Neuer Button "Dauerping starten" — pingt fortlaufend (1 Paket pro Tick, alle
  700ms) bis "Stoppen" gedrückt wird, mit Live-Diagramm (Canvas, kein externes JS), aktuellem
  Wert, min/avg/max der laufenden Session und Verlustzähler. Läuft über eine eigene Schleife statt
  über den geteilten Abbruch-Controller der übrigen Buttons — ein Klick anderswo in der App killt
  die Sitzung nicht, und umgekehrt. Ein einzelner verlorener/rate-limitierter Tick zeigt nur eine
  Lücke im Diagramm statt die Sitzung abzubrechen.
- **IPv4/IPv6 wählbar, bei Ping, Dauerping und Traceroute.** Neues Feld "IP-Version" (Auto/IPv4/
  IPv6) je Box — reicht `-4`/`-6` an ping/traceroute durch. `guard_target()` prüft ohnehin schon
  alle Adressen (beide Familien) einer Domain, also keine Lücke bei der SSRF-Prüfung durch die
  erzwungene Familie. Traceroutes "Ziel erreicht"-Abgleich holte sich bisher immer nur den
  A-Record zum Vergleich — bei erzwungenem IPv6 hätte das nie gepasst; jetzt AAAA bei family=6.
  Live getestet: `ping -4`/`-6` und `traceroute -4`/`-6` gegen google.com liefern beide
  jeweils die passende Adressfamilie.

## [0.1.11] - 2026-09-03

### Fixed
- **Monitor-Formular: Zeile verrutscht.** Der neue AAAA-Hinweistext saß innerhalb der Ziel-Spalte,
  machte sie dadurch höher als Name/Prüfung/Intervall — bei `align-items:center` auf der Zeile
  wurden die kürzeren Spalten dagegen zentriert, sichtbar als versetzte Labels. Hinweis jetzt als
  eigene volle Zeile unter dem ganzen Formular statt in der Ziel-Spalte.

## [0.1.10] - 2026-09-03

### Added
- **Neuer Monitor-Typ: AAAA-Wächter.** Warnt, sobald bei einer beobachteten Domain ein AAAA-Eintrag
  (IPv6) auftaucht — gedacht für einen Heimserver ohne sauberen IPv6-Pfad, wo ein verirrter AAAA
  (Router/DDNS-Client, der kurz eine IPv6-Adresse hatte) IPv6-bevorzugende Clients auf eine
  Adresse schickt, die nicht durchkommt, ohne dass sich das irgendwo außer im DNS zeigt. Ein
  Monitor deckt mehrere Domains gleichzeitig ab (Komma-getrennt im Ziel-Feld, bis zu 20) — kein
  Einzelmonitor pro Domain nötig. Neuer Probe `aaaa_guard` in probes.py, ein fehlerhafter Eintrag
  in der Liste bricht die restlichen nicht ab (pro Domain einzeln gefangen). Live getestet:
  google.com (hat AAAA) korrekt als Achtung geflaggt, gizmonet.eu (keine AAAA) korrekt OK.
- `monitor_hint` korrigiert — verwies noch auf die Add-on-Optionen für Mail/Telegram, die seit
  0.1.2 im Zahnrad-Dialog liegen.

## [0.1.9] - 2026-09-03

### Fixed
- **Monitor-Benachrichtigungen zeigten den Level doppelt.** Betreff endete auf `: WARN` und die
  erste Zeile der Kurzbeschreibung fing selbst nochmal mit `WARN:` an — in Telegram/E-Mail stand
  "WARN WARN ..." bzw. "INFO INFO ...". `summarize()` gibt jetzt nur noch die reine Beschreibung
  zurück (kein Level-Präfix mehr); Betreff trägt den Level stattdessen einmalig als farbiger Punkt
  + deutsches Wort: 🟢 OK, 🔵 Hinweis, 🟡 Achtung, 🔴 Kritisch — passend zur neuen
  OK/Achtung/Kritisch-Ampel aus 0.1.8.

## [0.1.8] - 2026-09-03

### Changed
- **Gesamt-Ampel ignoriert reine Hinweise.** Bisher zog jede rein informative Einzelmeldung (nur
  1 MX-Eintrag, optionale TLS-RPT/BIMI-Records fehlen, DMARC auf quarantine statt reject, kurzlebiger
  Zertifikatstyp) den Gesamtstatus einer Prüfung auf "Hinweis" runter, selbst wenn inhaltlich alles
  in Ordnung war — verwirrend, wirkte wie ein Problem. `_worst()` (mailauth/tlscheck/httpcheck/
  domaininfo/quiccheck/smtpcheck — 6× identischer Code) zählt INFO jetzt nicht mehr für die
  Gesamt-Ampel, nur noch FAIL/WARN. Einzelne Hinweis-Zeilen bleiben wie gehabt sichtbar, nur die
  Kopf-Ampel wird jetzt grün, wenn nichts Echtes vorliegt. Verifiziert: `mail_health` für
  gizmonet.eu (nur OK/Info-Funde) liefert jetzt `level: ok` statt `info`.
- **Label-Umbenennung:** "Warnung" → "Achtung", "Fehler" → "Kritisch" (EN: "Fail" → "Critical"),
  für eine klarere Drei-Stufen-Ampel OK/Achtung/Kritisch. "Hinweis" (info, einzelne Fundzeilen)
  bleibt unverändert.

### Fixed
- **TLS-Ablauf: 24h-Notfall-Floor.** Die anteilige Ablauf-Bewertung (Warnstufe ab <34%,
  Kritisch ab <10% der Zertifikats-Lebensdauer) konnte bei kurzlebigen Zertifikaten (z. B.
  10-Tage-Cert) mit genau noch 1 vollem Tag Rest bei "Achtung" hängenbleiben (1/10 = 10%, knapp
  über der Kritisch-Schwelle), obwohl real nur noch <24h bis zum Ablauf bleiben. Fester Floor
  ergänzt: unter 24 Stunden Restlaufzeit (sekundengenau, nicht die auf ganze Tage abgerundete
  Anzeige) ist immer Kritisch, unabhängig von der Lebensdauer-Quote.

## [0.1.7] - 2026-09-03

### Security
- **CodeQL: Information exposure through an exception (2× app.py, Mail-/Telegram-Testversand).**
  `send_email`/`send_telegram` in monitor.py gaben bei Fehlschlag bisher `str(e)` roh zurück, und
  die Test-Endpunkte reichten das unverändert ins UI durch — genau das Muster, das im letzten
  Changelog noch als Feature beschrieben war ("Fehlertexte laufen bewusst nicht durch die feste
  Übersetzung"), tatsächlich aber SMTP-/Telegram-Ausnahmetext (Hostnamen, Server-Antworten) an den
  Browser weiterreichte. Jetzt liefern beide Funktionen nur noch eine von fünf festen
  Kategorien (`auth_failed`, `recipient_refused`, `timeout`, `connection_failed`,
  `not_configured`) plus bei Telegram `http_NNN`; der volle `str(e)` geht weiterhin (wie schon
  vorher) ins Log, aber nicht mehr ins JSON. Neue Übersetzungen für alle vier Kategorien in
  de/en.json.
- **CodeQL: Clear-text logging of sensitive information (app.py, Erstlogin-Passwort).** Das beim
  ersten Start generierte Admin-Passwort landete per `log.info` im Klartext im Add-on-Log
  (HA-UI-sichtbar, potenziell länger aufbewahrt als options.json). Das Passwort wird weiterhin wie
  bisher in options.json geschrieben, aber nicht mehr geloggt — die Log-Zeile verweist nur noch auf
  die Datei.
- **CodeQL: Construction of a cookie using user-supplied input (app.py, `/set-lang`).** Die
  Sprache kam als `lang if lang in ('de','en') else 'en'` in `set_cookie` — durch die
  Mitgliedschaftsprüfung praktisch harmlos, aber für CodeQLs Taint-Tracking noch derselbe
  Request-Wert. Auf eine feste Zwei-Werte-Lookup-Tabelle umgestellt, deren Rückgabe garantiert
  eines von zwei hartkodierten Literalen ist.
- **CodeQL: Use of insecure SSL/TLS version (2× tlscheck.py) — geprüft, kein Fix.** Beide Treffer
  markieren die TLS-Handshakes, mit denen dieses Modul absichtlich beliebige Fremd-Server abfragt,
  um u. a. veraltete Protokollversionen (TLSv1/1.1/SSLv3) als Befund zu melden
  (`_WEAK_PROTOCOLS`). Ein `minimum_version`-Pin auf TLSv1.2 würde genau die Verbindungen, die
  dieses Feature erkennen soll, schon am Handshake scheitern lassen statt sie zu melden — kein
  NetToolbox-Geheimnis läuft über diese Sockets. Code-Kommentar an beiden Stellen ergänzt; Alerts
  #224/#225 sollten in GitHub als "used in code, false positive" geschlossen werden statt per
  Autofix verändert.

## [0.1.6] - 2026-09-03

### Added
- **Testversand für Mail und Telegram.** Je ein Button im Einstellungen-Dialog, direkt neben den
  jeweiligen Feldern — schickt eine echte Testnachricht mit den gerade eingetippten Werten, ohne
  vorher speichern zu müssen (leere Felder fallen auf die bereits gespeicherten Werte zurück,
  dieselbe Regel wie beim Speichern selbst). Live getestet: echte Telegram-API lehnt einen
  Fake-Token korrekt mit 401 ab, echter SMTP-Server (Google) lehnt Fake-Zugangsdaten korrekt mit
  535 ab — beide Fehlermeldungen kommen unverändert im UI an statt in „Unbekannter Fehler"
  aufzugehen, da SMTP-/Telegram-Fehlertexte bewusst nicht durch die feste Fehlercode-Übersetzung
  laufen.

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
