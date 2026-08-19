# CrowdPanel

**CrowdSec-Bedienpanel für Home Assistant** · [English](README.en.md)

Sperren ansehen, anlegen und aufheben — ohne `cscli` auf der Kommandozeile.
CrowdPanel spricht mit der lokalen API einer bestehenden CrowdSec-Installation
und macht daraus eine Weboberfläche.

## Funktionen

- **Übersicht** — aktive Sperren, Alarme der letzten 24 Stunden, häufigste Länder und Szenarien
- **Sperren** — filtern nach Bereich, Art und Herkunft; einzeln oder gesammelt aufheben
- **Neue Sperre** — einzelne IP, CIDR-Bereich, ganzes Land oder ganzes Netz (AS), mit frei wählbarer Dauer und Grund
- **Alarme** — was CrowdSec erkannt hat, mit Ereignissen und auslösender Log-Zeile
- **IP prüfen** — aktive Sperren, Alarmverlauf und Allowlist-Treffer zu einer Adresse
- **Ausnahmen** — Allowlists aus der CrowdSec-Datenbank und Whitelist-Parser im Klartext, mit Erklärung des Unterschieds
- **Zwei-Faktor-Anmeldung** — TOTP für den direkten Port, QR-Code lokal erzeugt, Backup-Codes
- Dark / Light · DE / EN · HA Ingress · PWA

## Schnellstart

1. Maschinen-Zugang in CrowdSec anlegen:
   ```sh
   CS=$(docker ps --format '{{.Names}}' | grep -i crowdsec)
   CFG=/config/.storage/crowdsec/config/config.yaml
   PW=$(openssl rand -hex 22)
   docker exec $CS cscli -c $CFG machines add crowdpanel --password "$PW" -f -
   echo "$PW"
   ```
   `-c $CFG` und `-f -` sind beide Pflicht, `--force` wäre falsch → [DOCS.md](DOCS.md#schritt-1--maschinen-zugang-in-crowdsec-anlegen)
2. `lapi_url`, `machine_id` und `machine_password` in den Add-on-Optionen eintragen
3. `password` ändern und Add-on starten

## Ports

| Port | Funktion |
|------|----------|
| `17797` | Web-UI (direkt, mit Anmeldung — über Ingress ohne) |

## Abgrenzung

CrowdPanel ersetzt keinen Bouncer und liest keine Logs. Es verwaltet nur die
Entscheidungen in der CrowdSec-Engine; durchgesetzt werden sie weiterhin von den
Bouncern, zum Beispiel dem in [NPMplus](../npmplus/).

Nicht enthalten sind `cscli bouncers list`, `machines list`, `metrics` und
`hub list` — diese Befehle lesen die lokale CrowdSec-Datenbank statt der API.

## Dokumentation

Vollständige Einrichtung, alle Optionen, Fehlersuche: **[DOCS.md](DOCS.md)**
