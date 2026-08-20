# Changelog

## [0.1.26] - 2026-08-20

### Dokumentation
- **CrowdSec ist nicht Teil dieses Repos** — der Abschnitt sagt das jetzt zu Beginn und
  verweist auf die offiziellen Add-ons unter
  https://github.com/crowdsecurity/home-assistant-addons (`crowdsec` = Engine/LAPI,
  `crowdsec-firewall-bouncer` = optional). Der Bouncer selbst steckt in NPMplus; nötig ist
  nur der Schlüssel aus `cscli bouncers add npmplus`. Ohne Engine bleiben alle
  `crowdsec_*`-Optionen wirkungslos.
- Klargestellt, dass `/data/crowdsec/crowdsec.conf` für `ENABLED`, `API_URL`, `API_KEY`,
  `APPSEC_URL` und die Captcha-Schlüssel bei jedem Start aus den Add-on-Optionen
  überschrieben wird — Handarbeit an diesen Zeilen ist wirkungslos, der Rest der Datei bleibt.
- Beispielkonfiguration des CrowdSec-Add-ons ergänzt (Acquisition für Home Assistant, NPMplus
  und AppSec, Collections, `parsers_to_disable`), samt Begründung, warum
  `crowdsecurity/appsec-crs` nicht enthalten ist — Teilzeichenketten wie `elif` in
  Jinja-Templates oder `sched` in `schedule` lösen reihenweise Fehlalarme aus.
- README (DE/EN) und die Optionsbeschreibung von `crowdsec_enabled` weisen auf die nötige
  Engine hin.

## [0.1.25] - 2026-08-19

### Fixed
- **Dokumentation:** Variante B der CrowdSec-Anbindung (Datei-Acquisition über
  `/share/npmplus/logs/*.log`) war als gleichwertige Möglichkeit beschrieben. Sie
  funktioniert mit dem CrowdSec-Add-on nicht — dessen Container bekommt nur
  `/config` und `/data` eingehängt, kein `/share`. Wer der Anleitung folgte,
  bekam eine Acquisition, die stillschweigend nichts liest. Der Abschnitt weist
  jetzt darauf hin, nennt den Prüfbefehl und verweist für diesen Fall auf
  Variante A (journald). `share_logs` bleibt sinnvoll, um die Logs über Samba
  einzusehen.

## [0.1.24] - 2026-08-18

- Fix: Im Protokoll der gesperrten Anfragen stand der Zeitstempel als `[$time_local]` und enthielt damit ein Leerzeichen vor der Zeitzone. Jede Spaltennummer in `awk` verschob sich dadurch um eins — die dokumentierte Auswertung `$4` lieferte die IP statt des Landes. Jetzt `$time_iso8601`, ein einziges Feld, das Land steht verlässlich in Spalte 4
- Bestehende `blocked.log` behalten das alte Format bis zur nächsten Rotation; für ältere Zeilen ist `$5` die richtige Spalte
- Doku: Spaltenaufbau von `blocked.log` als Tabelle, dazu drei Auswertungen — häufigste Länder, hartnäckigste Einzeladressen und die tatsächlich angefragten Pfade. Letztere zeigt am schnellsten, ob die Sperre Scanner oder echte Besucher trifft

## [0.1.23] - 2026-08-18

- Start ohne Wartezeit: passen die vorhandenen Länderlisten noch zur Konfiguration und sind sie jünger als `geo_refresh_hours`, entfällt der Download. Bisher kostete jeder Neustart 14 Sekunden, auch wenn sich nichts geändert hatte. Ein Fingerabdruck aus Betriebsart, Ländern und Protokollschalter entscheidet darüber; sobald du etwas davon änderst, werden die Listen neu geholt
- Neue Option `geo_deny_action`: `403` liefert wie bisher eine Sperrseite, `444` schließt die Verbindung wortlos — ein Scanner erfährt so nicht einmal, dass an der Adresse ein Server steht
- Eigene Sperrseite unter `/data/geoip/blocked.html`, zweisprachig und ohne externe Ressourcen. Sie wird nur angelegt, wenn sie fehlt, und nie überschrieben — eigener Text und Kontaktweg bleiben über Updates hinweg erhalten
- Die Sperrseite ersetzt bewusst nicht die von CrowdSec: intern antwortet das Add-on mit dem eigenen Code 460 und wandelt ihn erst danach in 403 um. Ein `error_page 403` hätte auch die Seiten von CrowdSec und von Zugriffslisten verschluckt
- Neue Option `geo_log_country` (Standard `true`): gesperrte Anfragen landen mit Herkunftsland in `/data/nginx/logs/blocked.log`. Damit lässt sich nach ein paar Wochen auswerten, welche Länder überhaupt etwas beitragen und welche nur echte Besucher kosten. Preis ist eine zweite Nachschlagetabelle, rund 4 MB Arbeitsspeicher. Im Erlaubnismodus bleibt die Spalte `-`, weil dort nur die freigegebenen Länder geladen werden
- Das reguläre Access-Log von NPMplus bleibt daneben unverändert

## [0.1.22] - 2026-08-18

- Fix: Das Protokoll nannte zwei verschiedene Zahlen für dieselbe Sache — `38189 ranges` beim Download, `38034 ranges` beim Aktivieren. Gezählt wurden die Rohzeilen der heruntergeladenen Dateien, in der fertigen Liste fallen Leerzeilen aber weg. Jetzt wird gezählt, was tatsächlich in der Datei landet

## [0.1.21] - 2026-08-18

- Fix: Wer `geo_preset` oder `geo_countries` ausfüllt, aber `geo_mode` auf `off` stehen lässt, bekam keinerlei Rückmeldung — die Sperre blieb still aus. Das Protokoll warnt jetzt in beiden Fällen und nennt den fehlenden Schritt
- Doku und Optionsbeschreibung nennen `geo_mode` deutlich als Hauptschalter und sagen, an welchen Protokollzeilen man erkennt, dass die Sperre wirklich läuft

## [0.1.20] - 2026-08-18

- `geo_preset: high_risk` umfasst jetzt 16 statt 21 Länder, rund 38000 statt 73000 Adressbereiche. Herausgenommen: IN, BR, MX, ID und TR. Das sind große Internetländer mit vielen echten Nutzern — sie zu sperren kostet mehr an ausgesperrten Besuchern, als es an Angriffen erspart. Wer sie trotzdem will, trägt sie zusätzlich in `geo_countries` ein
- Doku: Abschnitt dazu, was bewusst nicht in der Vorauswahl steht und warum, samt Hinweis auf die Grenzen der Methode — der überwiegende Teil automatisierter Angriffe kommt aus Rechenzentren in Ländern, die man nicht sperren kann, weil man selbst dort steht. Eine Ländersperre senkt das Grundrauschen, ersetzt CrowdSec aber nicht

## [0.1.19] - 2026-08-18

- Neue Option `geo_preset`: `high_risk` trägt 21 Länder auf einen Schlag ein (CN, RU, KP, IR, IN, PK, BD, VN, ID, MY, TH, PH, NG, GH, ZA, BR, AR, CO, MX, TR, EG), rund 73000 Adressbereiche. `geo_countries` bleibt daneben nutzbar, beide Listen werden zusammengeführt und Doppelte fallen weg
- Die Vorauswahl gilt nur für `geo_mode: block`. Zusammen mit `allow` wird sie mit einer Warnung übergangen, sonst wäre aus einer Sperrliste unbemerkt eine Erlaubnisliste geworden
- Protokoll zeigt den Download jetzt nachvollziehbar: Anzahl der Länder, eine Zeile je Land mit der Anzahl Bereiche, Gesamtzahl und Dauer. Fehlende Listen stehen als Warnung darin, samt Hinweis am Ende, wie viele fehlen
- Fix: Ein fehlgeschlagener Download blieb unbemerkt. Der Rückgabewert einer Pipeline ist der ihres letzten Glieds — `awk` war auch nach einem 404 zufrieden, das Land fehlte still in der Sperre. Jetzt wird der HTTP-Code selbst ausgewertet
- Nicht jede fehlende Datei ist ein Fehler: Nordkorea hat keine IPv6-Zuteilung, ipverse veröffentlicht dafür also nichts. Ein 404 gilt deshalb als übersprungen und nicht als Ausfall

## [0.1.18] - 2026-08-18

- Neue Ländersperre über die Optionen `geo_mode`, `geo_countries`, `geo_exempt_hosts` und `geo_refresh_hours`. Sie arbeitet mit dem eingebauten `geo`-Modul von nginx und greift damit schon bei der ersten Anfrage, während CrowdSec erst nach deren Auswertung entscheidet
- Die Adressbereiche kommen von [ipverse/country-ip-blocks](https://github.com/ipverse/country-ip-blocks) und damit aus den Delegationsdateien der Regional Internet Registries — kein MaxMind-Konto, kein Lizenzschlüssel, kein zusätzliches nginx-Modul nötig
- Zwei Betriebsarten: `block` sperrt die genannten Länder, `allow` lässt nur sie durch. `geo_exempt_hosts` nimmt einzelne Hostnamen aus, damit erreichbar bleibt, was man aus dem Ausland braucht
- `/.well-known/acme-challenge/` ist immer frei, sonst wären im `allow`-Modus Ausstellung und Verlängerung der Let's-Encrypt-Zertifikate tot. Die Weboberfläche auf Port 81 ist nicht betroffen
- Neue Listen `geo_deny_ips` und `geo_allow_ips` für einzelne Adressen und CIDR-Bereiche. `geo_deny_ips` wirkt unabhängig vom Land, auch bei `geo_mode: off` und auch auf ausgenommenen Hostnamen; `geo_allow_ips` nimmt einzelne Adressen von der Ländersperre aus. Werte, die keine Adresse sind, werden verworfen und nicht in die nginx-Konfiguration geschrieben
- Die Listen werden im Abstand von `geo_refresh_hours` neu geladen, nginx aber nur bei echter Änderung durchgestartet. Schlägt der Download fehl, bleiben die zuletzt geladenen Listen in Kraft; gibt es noch keine, bleibt die Sperre aus — ein Netzausfall darf niemanden aussperren
- Eigene Einträge in `/data/custom_nginx/http_top.conf` und `server_http.conf` bleiben erhalten, das Add-on schreibt nur zwischen seine eigenen Marker und räumt sie beim Umstellen auf `off` wieder ab
- Doku: Hinweis, dass Änderungen an den Geo-Optionen erst nach einem Neustart des Add-ons wirken — die nginx-Konfiguration dafür entsteht beim Start. Nur das Auffrischen der Länderlisten läuft im Betrieb
- Doku: neuer Abschnitt „Ländersperre" in beiden Sprachen, samt Hinweis auf die geringere Trefferquote von Registerdaten gegenüber MaxMind und der Empfehlung, im Zweifel eine Sperr- statt einer Erlaubnisliste zu benutzen

## [0.1.17] - 2026-08-17

- Doku: Der Link auf die NPMplus-Lizenz lief ins Leere — die Datei heißt dort `COPYING`, nicht `LICENSE`
- Doku: Die Aussage „verpackt nur das Image, verändert die Anwendung nicht" war ungenau, der Entrypoint wird ersetzt. Neue `LICENSE.md` beschreibt Art und Umfang der Änderung, trennt die MIT-lizenzierten Add-on-Dateien vom AGPL-Gesamtwerk im veröffentlichten Image und nennt die verwendete NPMplus-Fassung als Quellenangabe
- Doku: Hinweis, wohin Fehlerberichte gehören — Add-on-Eigenheiten in dieses Repository, NPMplus-Fehler zuerst zum NPMplus-Projekt

## [0.1.16] - 2026-08-17

- Fix: Die GoAccess-Statistik war unter der dokumentierten Adresse `https://<HA-IP>:81/goaccess` nicht erreichbar, dort kam die Fehlerseite von NPMplus. In der eingesetzten Version läuft GoAccess als eigener HTTPS-Server auf **Port 91**; der Unterpfad in der Oberfläche existiert bisher nur im Entwicklungszweig von NPMplus. Doku, Übersetzungen und Portliste korrigiert
- Sicherheit: Dieser Server auf Port 91 kennt **keine Anmeldung** und zeigt Besucher-IPs sowie jede angefragte URL — die bisherige Beschreibung „Nur für angemeldete Admins sichtbar" war falsch. Neue Option `goaccess_listen_localhost` (Standard `true`) bindet ihn deshalb nur an `127.0.0.1`. Für den Zugriff einen Proxy Host mit Zugriffsliste auf `https://127.0.0.1:91` anlegen, Websockets zulassen nicht vergessen. Wer es wie bisher offen im LAN haben will, setzt die Option auf `false`
- Protokoll nennt beim Start die tatsächliche Adresse des Dashboards und warnt, wenn es ungeschützt im LAN hängt
- Doku: eigener Abschnitt „GoAccess-Statistik" samt Länderauswertung über MaxMind, drei neue Einträge in der Problembehandlung
- Backlog: was beim nächsten Versionssprung von NPMplus rückgebaut werden muss, sobald GoAccess dort unter `/goaccess` mit Admin-Prüfung liegt

## [0.1.15] - 2026-08-17

- Neue Optionen `crowdsec_captcha_provider`, `crowdsec_captcha_site_key` und `crowdsec_captcha_secret_key`: der Bouncer kann verdächtige Besucher ein Captcha lösen lassen statt sie auszusperren (Turnstile, hCaptcha, reCAPTCHA). Ohne Schlüssel bleibt Captcha aus — das erklärt auch die bisherige Logzeile „error loading captcha plugin"
- Doku: eigener Abschnitt dazu, samt Hinweis, dass CrowdSec über seine `profiles.yaml` erst Entscheidungen vom Typ `captcha` ausstellen muss

## [0.1.14] - 2026-08-17

- Doku: Hinweis ergänzt, dass nicht nur Home Assistant, sondern jeder Dienst hinter NPMplus mit Proxy-Prüfung die LAN-IP der Maschine in seiner Liste vertrauenswürdiger Proxys braucht — betrifft z.B. Nextcloud

## [0.1.13] - 2026-08-17

- Doku: Abschnitt „Prüfbefehle auf einen Blick" — Registrierung, Logfluss, aktive Sperren, Collections, Container-IP, Erreichbarkeit von LAPI und AppSec, direkter Schlüsseltest an der LAPI sowie eine Testsperre der eigenen IP zum Nachweis, dass der Bouncer wirklich blockt

## [0.1.12] - 2026-08-17

- Neue Option `acme_profile`: steuert die Laufzeit der Let's-Encrypt-Zertifikate. Standard bleibt `shortlived` (≈ 6 Tage, so wie NPMplus es vorgibt), `classic` liefert die gewohnten 90 Tage
- Doku: eigener Abschnitt zur Laufzeit samt Abwägung — kurze Laufzeiten sind sicherer, verzeihen aber keinen längeren Ausfall der Erneuerung

## [0.1.11] - 2026-08-17

- Protokollausgabe des Add-ons durchgehend auf Englisch umgestellt — passend zur Ausgabe von NPMplus selbst, die ebenfalls englisch ist. Die Konfigurationsoberfläche und die Dokumentation bleiben zweisprachig

## [0.1.10] - 2026-08-17

- Doku: `cscli`-Falle beschrieben — ohne `-c` schreibt `cscli` in `/etc/crowdsec/`, während das CrowdSec-Add-on seine Engine mit einer eigenen Konfiguration startet. Der Bouncer landet dann in einer Datenbank, die die laufende Instanz nie liest: `bouncers list` zeigt ihn an, die LAPI antwortet trotzdem mit 403
- Doku: Schlüssel per `cscli bouncers add … -k $(openssl rand -hex 22)` selbst vorgeben, damit beim Kopieren keine Sonderzeichen verlorengehen

## [0.1.9] - 2026-08-17

- Fix: Bouncer-Key, LAPI- und AppSec-URL werden jetzt von Leerraum und Zeilenenden befreit. Ein aus Datei oder Terminal kopierter Wert schleppt leicht ein `\r` oder ein abschließendes Leerzeichen mit — im HTTP-Header macht das den Schlüssel ungültig, ohne dass man es sehen kann
- Startprüfung fragt zusätzlich `/v1/decisions/stream` ab und schickt einen eigenen User-Agent mit, damit sie nicht an einer einzelnen Endpunkt-Eigenheit scheitert
- Wird der Schlüssel abgelehnt, nennt die Warnung jetzt seine Länge (cscli erzeugt 44 Zeichen) — damit fällt ein abgeschnittener Wert sofort auf

## [0.1.8] - 2026-08-17

- Fix: tini warnte beim Start „Tini is not running as PID 1 and isn't registered as a child subreaper". Da run.sh seit 0.1.2 PID 1 bleibt, läuft tini jetzt mit `-s` und registriert sich als child subreaper — verwaiste Prozesse werden damit wieder abgeräumt

## [0.1.7] - 2026-08-17

- Doku: neuer Abschnitt „Einstellungen je Proxy Host" — alle Schalter des Optionen-Reiters (noindex, AppSec, Buffering, URI-Sanitisation, Host-Header, X-Frame-Options, Auth Request) und des TLS-Reiters (HTTPS erzwingen, HTTP/3, HSTS, Preload-Warnung, Schlüssel beibehalten, DNS-Challenge) mit Empfehlung

## [0.1.6] - 2026-08-17

- Doku: Abschnitt „Daten und Backup" erweitert — vollständige Pfadtabelle (Datenbank, Zertifikate, Schlüssel, CrowdSec-Konfiguration), Klarstellung dass Add-on-Daten **nicht** über Samba erreichbar sind, und `docker exec`/`docker cp`-Beispiele zum Ansehen und Herauskopieren

## [0.1.5] - 2026-08-17

- Doku überarbeitet, nachdem die Ersteinrichtung mehrere unbeschriebene Fallen hatte:
  - CrowdSec-Adresse: `127.0.0.1` stimmt nur bei Port-Mapping auf den Host; sonst Container-IP ermitteln
  - Bouncer-Registrierung prüfen (`cscli bouncers list`) — eine leere Liste heißt, der Schlüssel wurde nie angelegt
  - `crowdsec_appsec_url` muss leer bleiben, wenn kein `appsec`-Block in der Acquisition steht
  - Neuer Abschnitt „Home Assistant hinter NPMplus": 400 Bad Request wegen `trusted_proxies`, da Host-Netz eine andere Quell-IP liefert als ein Add-on im Bridge-Netz
  - Problembehandlung: AAAA-Record als Ursache fehlschlagender Zertifikate, inklusive Hinweis, dass IPv6 im Router abzuschalten nichts hilft

## [0.1.4] - 2026-08-17

- Sicherheitsnetz: Der Bouncer-Key wird beim Start gegen die CrowdSec-LAPI geprüft. Antwortet sie mit 401/403 oder ist gar nicht erreichbar, bleibt der Bouncer AUS statt jede Anfrage zu sperren
- Hintergrund: AppSec beantwortet eine unauthentifizierte Anfrage mit 403, und 403 bedeutet im AppSec-Protokoll „blockieren" — ein Tippfehler im Schlüssel legte damit sämtliche Dienste hinter dem Proxy lahm
- Die Warnung im Protokoll nennt jetzt auch den häufigsten Fall: CrowdSec läuft in einem eigenen Container, dann ist 127.0.0.1 die falsche Adresse

## [0.1.3] - 2026-08-17

- Fix: Add-on-Protokoll wurde von nginx-`[notice]`-Zeilen geflutet. Mit `logrotate: true` aktiviert NPMplus sein Error-Log auf Stufe `info`, das protokolliert jeden Worker-Wechsel und jedes SIGCHLD. Neue Option `error_log_level`, Standard `warn`
- `log_to_stdout` spiegelt jetzt nur noch das Access-Log ins Protokoll; das Error-Log bleibt in der Datei

## [0.1.2] - 2026-08-17

- Fix: Add-on beendete sich mit Exit-Code 143, Supervisor meldete „did not handle SIGTERM". `run.sh` übergab per `exec` an tini, damit war tini PID 1 und starb am Signal statt sauber mit 0 zu enden. Jetzt bleibt `run.sh` PID 1, fängt SIGTERM/SIGINT ab, reicht ihn weiter, wartet auf das Ende von NPMplus und beendet sich mit 0
- Fix: der `tail`-Prozess der Log-Spiegelung war verwaist und bekam nie ein Signal — wird jetzt beim Stoppen mit beendet
- tini läuft mit `-g`, das Signal geht damit an die gesamte Prozessgruppe statt nur an `entrypoint.sh`
- Stirbt NPMplus von sich aus, wird der Exit-Code jetzt durchgereicht statt verschluckt

## [0.1.1] - 2026-08-17

- Fix: Sprachumschalter und Verweise auf DOCS/CHANGELOG waren relative Links und damit in der Home-Assistant-Oberfläche tot — HA rendert Markdown ohne Repo-Bezug. Jetzt absolute GitHub-URLs
- Sprachumschalter DE/EN auch in DOCS.md und DOCS.en.md

## [0.1.0] - 2026-08-17

- Erste Version: NPMplus `2026-07-24-r1` als Home-Assistant-Add-on
- Host-Netzwerk, Ports 80/443 TCP, 443 UDP (HTTP/3) und 81 für die Weboberfläche
- Add-on-Optionen werden in NPMplus-Umgebungsvariablen übersetzt, alles Weitere über `extra_env`
- CrowdSec-Bouncer und AppSec direkt aus den Add-on-Optionen konfigurierbar (`/data/crowdsec/crowdsec.conf`)
- Logs wahlweise nach `/share/npmplus/logs` (Datei-Acquisition) und/oder ins Add-on-Protokoll (journald-Acquisition)
- Oberfläche und Dokumentation in Deutsch und Englisch
