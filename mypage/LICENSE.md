# Lizenzen — MyPage-Add-on

## Eigene Dateien

Der Quelltext dieses Add-ons (`app.py`, `game_*.py`, `templates/`, `static/`, `locales/`,
`translations/`, `config.yaml`, `Dockerfile` und die Markdown-Dateien in diesem Verzeichnis)
stammt aus diesem Repository und steht unter der **MIT-Lizenz**
(siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## Länderdaten (DB-IP Lite)

Die Länder-Erkennung in der Statistik nutzt die frei verfügbare Liste **DB-IP Lite**
(`dbip-country-lite`). Sie steht unter der
**[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)**
und verlangt eine Namensnennung:

> IP Geolocation by DB-IP — <https://db-ip.com>

Diese Nennung steht in der Admin-Statistik unter der Länder-Verteilung sowie in der
[DOCS.md](DOCS.md). Die Liste wird zur Laufzeit heruntergeladen und liegt unter
`/config/geoip` — sie ist **nicht** Bestandteil des Images.

Fällt der Download aus, greift das Add-on auf die Delegationsdateien der fünf Regional
Internet Registries (APNIC, RIPE NCC, ARIN, LACNIC, AFRINIC) zurück. Diese Dateien sind
öffentliche Registerdaten und werden von den Registries ohne Lizenzauflagen bereitgestellt.

## Weitere Bestandteile

Das Image basiert auf `python:3.14-alpine` (PSF-Lizenz bzw. die Lizenzen der Alpine-Pakete)
und enthält die per `pip` installierten Abhängigkeiten mit ihren jeweiligen Lizenzen
(u. a. Flask, Jinja2, Waitress, Requests — alle BSD/MIT-artig). Die mitgelieferten
Schriften unter `fonts/` behalten ihre eigenen Lizenzen.
