# HA SysWatch — Dokumentation

## Voraussetzungen

Dieses Add-on benötigt Zugriff auf den Docker-Socket des Hosts.
`docker_api: true` in der `config.yaml` bindet `/var/run/docker.sock` korrekt ein
und zeigt den **Docker-Badge** in der HA Add-on UI.

Für gestoppte HA Add-ons (deren Docker-Container HA beim Stoppen entfernt) wird
zusätzlich die **Supervisor API** genutzt (`hassio_api: true`, `hassio_role: manager`).

## Port

`17790`

## Konfiguration

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `username` | string | `admin` | Login-Benutzername |
| `password` | string | `secret` | Login-Passwort (auch für Start/Stop/Neustart/Kill benötigt) |
| `session_hours` | int | `24` | Session-Dauer in Stunden |
| `collect_interval` | int | `3` | Pause zwischen Docker-Abfragen in Sekunden (min. 2) |
| `collect_workers` | int | `16` | Parallele Docker-Stats-Abfragen (4–64) |
| `viewer_timeout` | int | `180` | Idle-Timeout in Sekunden (30–1800) |
| `show_stopped` | bool | `true` | Gestoppte Container standardmäßig anzeigen |

## Performance-Tuning

### collect_interval und collect_workers

Die Abfragezeit hängt von der Anzahl der Container und der Worker-Anzahl ab.
`docker stats --no-stream` fragt intern alle Container parallel ab
und braucht pro Container ~1 s (Docker-Daemon-Messintervall) — das ist der
unvermeidliche Flaschenhals, unabhängig von der Worker-Anzahl.

**Beispiel mit 49 Containern:**

| collect_workers | Abfragezeit | + collect_interval | = Browser-Zyklus |
|---|---|---|---|
| 16 | ~4 s | 3 s | ~7 s |
| 32 | ~2,5 s | 3 s | ~5,5 s |
| 49 | ~2 s | 3 s | ~5 s |
| 49 | ~2 s | 1 s | ~3 s |

Mehr Worker als Container bringt keinen Gewinn — ab dann ist man auf dem gleichen
Level wie `docker stats --no-stream` im Terminal (~2 s).

### collect_workers vs. CPU-Last

| collect_workers | CPU-Last | Geschwindigkeit |
|---|---|---|
| 4–8 | Sehr gering | Langsam bei vielen Containern |
| 16 *(Standard)* | Gering | Guter Kompromiss |
| 32–49 | Spürbar | Schnell |
| >49 | Hoch | Kein weiterer Gewinn |

### viewer_timeout (Idle-Modus)

Wenn kein Browser die Seite geöffnet hat, wechselt der Collector automatisch
in den **Idle-Modus**: nur 2 Worker, 60 s Interval — minimale Systemlast.

Der Browser sendet alle 10 s einen Heartbeat. Bleibt er `viewer_timeout` Sekunden
aus, aktiviert sich der Idle-Modus. Beim nächsten Öffnen wechselt der Collector
sofort zurück in den Aktiv-Modus.

Der **Pause-Button** (⚡) im Header pausiert die Datenerfassung manuell.

## Funktionen

### Container-Tabelle

- **Sortierbare Spalten**: Name, CPU %, RAM %, RAM-Nutzung, NET I/O, DISK I/O, PIDs
- Sortierung (Spalte + Richtung) wird in `localStorage` gespeichert
- **CPU-Sparkline**: Verlauf der letzten 30 Messungen pro Container
- **Status-Badge**: running, exited, paused, stopped
- **Suchfeld**: filtert nach Name oder Image
- **Gestoppte anzeigen**: zeigt/verbirgt nicht laufende Container; Auswahl gespeichert

### Aktionen

Alle destruktiven Aktionen erfordern Passwortbestätigung:

| Button | Beschreibung | Wann sichtbar |
|---|---|---|
| ▶ Start | Container starten (Docker oder Supervisor API) | Gestoppte Container |
| ■ Stop | Container stoppen (SIGTERM, 10 s Timeout) | Laufende Container |
| ↺ Neustart | Container neustarten | Laufende Container |
| ⏻ Kill | Container sofort beenden (SIGKILL) | Laufende Container |
| Logs | Letzte 200 Zeilen mit Timestamps | Immer |

**Gestoppte HA Add-ons:** HA entfernt gestoppte Add-on-Container aus Docker.
SysWatch holt sie über die Supervisor API und zeigt einen ▶-Button zum Starten.

### Port-Übersicht

Über den **Ports**-Button in der Kontrollzeile öffnet sich ein Modal mit allen
Host-Port-Mappings. Die Tabelle ist vollständig sortierbar und hat ein Suchfeld.

### System-Karten

- **SYS CPU**: Auslastung des Hosts in %
- **SYS RAM**: RAM-Nutzung in %, Sub-Label zeigt `genutzt / gesamt`
- **CPU-Takt**: aus `/proc/cpuinfo` (Kerne × Ø GHz)

### Header-Elemente

- **Modus-Dot**: grün = aktiv, gelb = idle, rot = pausiert
- **Zyklus-Label**: zeigt den tatsächlichen Browser-Refresh-Zyklus in Sekunden
- **Countdown**: Sekunden bis zur nächsten Aktualisierung
- **Refresh-Button**: sofortige manuelle Aktualisierung
- **Pause-Button**: pausiert/setzt Datenerfassung fort
- **Light/Dark-Toggle**: wechselt zwischen Hell- und Dunkel-Modus

## Sicherheit

- Passwortgeschütztes Login
- **Brute-Force-Schutz**: nach 5 Fehlversuchen innerhalb von 10 Minuten
  wird die IP für 15 Minuten gesperrt
- **Passwortbestätigung** für alle destruktiven Aktionen (Start, Stop, Neustart, Kill)
- Session-Cookies: `HttpOnly`, `SameSite=Lax`
- Cloudflare-Tunnel-kompatibel (`CF-Connecting-IP` wird ausgewertet)
