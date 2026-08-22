# Backlog — CrowdPanel

Ideen, die nicht dringend sind. Kein Zeitplan.

Die Liste entstand beim Vergleich mit [crowdsec-web-ui](https://github.com/TheDuffman85/crowdsec-web-ui)
— einem eigenständigen Web-UI für CrowdSec (React/Vite/Hono/Node/SQLite). Dessen
Code lässt sich nicht übernehmen, CrowdPanel ist Flask mit reinem JavaScript;
übernommen werden also allenfalls Ideen, und dann nachgebaut.

Erledigt daraus: **Prometheus-Metriken** (0.4.6, Reiter „Metriken“), die
**Angriffskarte** (0.5.0, Übersicht) — letztere als Punktkarte aus echten
GeoIP-Koordinaten statt nur eingefärbter Länder — und die **lokale
Alarm-Datenbank** (0.6.0, `/data/alerts.db`).

## Such-Syntax statt Freitext

`_text_match` in `app.py` vergleicht nur Teilzeichenketten über eine feste
Feldliste. Sinnvoll wäre eine kleine Abfragesprache: `scenario:ssh-bf`,
`country:CN`, `since:>7d`, Anführungszeichen für Wortgruppen, `AND`/`OR`. Der
Parser gehört in ein eigenes Modul mit Tests, die Filterung bleibt serverseitig.

## Abgelaufene Sperren und Duplikate

Der Reiter „Sperren“ zeigt nur aktive Entscheidungen. Eine Umschaltung auf
abgelaufene würde die Frage „war diese Adresse schon einmal gesperrt?“
beantworten, ohne den Umweg über „IP prüfen“. Dazu ein Schalter, der mehrfache
Entscheidungen zur selben Adresse (verschiedene Blocklisten, dieselbe IP) zu
einer Zeile zusammenfasst.

## Alarme löschen

`DELETE /v1/alerts` gibt es, die LAPI verlangt dafür aber, dass die aufrufende
Adresse in `api.server.trusted_ips` von CrowdSec steht. Das ist eine
Konfigurationsänderung außerhalb des Add-ons, also Dokumentation plus eine
Schaltfläche, die sauber erklärt, warum sie gerade nicht geht. Siehe
DOCS-Abschnitt „Alarme lassen sich nicht löschen“.

## Simulationsmodus sichtbar machen

Szenarien im Simulationsmodus erzeugen Alarme mit `simulated: true`, aber keine
wirksamen Sperren. CrowdPanel zeigt sie heute wie alle anderen. Ein Filter plus
eine Kennzeichnung in der Zeile würde die Verwirrung auflösen, warum eine
Adresse „gesperrt“ aussieht und trotzdem durchkommt.

## Wählbare Spalten

`DECISION_COLS` und die Alarm-Tabelle sind fest verdrahtet. Wer regelmäßig auf
AS oder Herkunft schaut, will andere Spalten sehen als jemand, der nur Länder
prüft. Auswahl im Browser speichern (`localStorage`), nicht in den Optionen.

## Bewusst nicht übernommen

- **Benachrichtigungen mit eigenem Regelwerk** (Schwellwerte, Spitzen, E-Mail,
  ntfy, Gotify, MQTT, Webhooks). In Home Assistant ist das doppelt gemoppelt:
  CrowdPanel meldet Sensoren, alles Weitere macht eine Automatisierung — mit
  allen Benachrichtigungswegen, die HA ohnehin schon kennt.
- **Mehrere LAPI-Instanzen gleichzeitig.** Ein HA-Setup hat eine CrowdSec-Engine.
- **OIDC/SSO und Passkeys.** Der übliche Weg führt über Ingress, dort
  authentifiziert der Supervisor. Für den direkten Port reicht TOTP.
- **Nur-Lesen-Modus.** Denkbar als Option, aber niemand hat danach gefragt.
- **Zehn Sprachen.** DE und EN werden gepflegt, alles Weitere veraltet.
