# Changelog

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
