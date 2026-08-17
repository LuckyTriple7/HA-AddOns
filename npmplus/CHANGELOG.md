# Changelog

## [0.1.0] - 2026-08-17

- Erste Version: NPMplus `2026-07-24-r1` als Home-Assistant-Add-on
- Host-Netzwerk, Ports 80/443 TCP, 443 UDP (HTTP/3) und 81 für die Weboberfläche
- Add-on-Optionen werden in NPMplus-Umgebungsvariablen übersetzt, alles Weitere über `extra_env`
- CrowdSec-Bouncer und AppSec direkt aus den Add-on-Optionen konfigurierbar (`/data/crowdsec/crowdsec.conf`)
- Logs wahlweise nach `/share/npmplus/logs` (Datei-Acquisition) und/oder ins Add-on-Protokoll (journald-Acquisition)
- Oberfläche und Dokumentation in Deutsch und Englisch
