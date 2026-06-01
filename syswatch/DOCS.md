# HA SysWatch — Dokumentation

## Voraussetzungen

Dieses Add-on benötigt Zugriff auf den Docker-Socket des Hosts.
In der `config.yaml` ist `docker_api: true` gesetzt, was den Socket
(`/var/run/docker.sock`) korrekt einbindet und den **Docker-Badge**
in der HA Add-on UI anzeigt.

## Port

`17790`

## Konfiguration

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `username` | string | `admin` | Login-Benutzername |
| `password` | string | `secret` | Login-Passwort (auch für Neustart/Kill benötigt) |
| `session_hours` | int | `24` | Session-Dauer in Stunden |
| `collect_interval` | int | `3` | Pause zwischen Docker-Abfragen in Sekunden (min. 2) |
| `collect_workers` | int | `16` | Parallele Docker-Stats-Abfragen (4–64) |
| `viewer_timeout` | int | `180` | Idle-Timeout in Sekunden (30–1800) |
| `show_stopped` | bool | `false` | Gestoppte Container standardmäßig anzeigen |

## Performance-Tuning

### collect_interval und collect_workers

Die Abfragezeit hängt von der Anzahl der Container und der Worker-Anzahl ab.
`docker stats --no-stream` fragt intern ebenfalls alle Container parallel ab
und braucht pro Container ~1s (Docker-Daemon-Messintervall) — das ist der
unvermeidliche Flaschenhals, unabhängig von der Worker-Anzahl.

**Beispiel mit 49 Containern:**

| collect_workers | Abfragezeit | + collect_interval | = Browser-Zyklus |
|---|---|---|---|
| 16 | ~4s | 3s | ~7s |
| 32 | ~2.5s | 3s | ~5.5s |
| 49 | ~2s | 3s | ~5s |
| 49 | ~2s | 1s | ~3s |

Mehr als so viele Worker wie Container bringt nichts — ab dann ist man
auf dem gleichen Level wie `docker stats --no-stream` im Terminal (~2s).

### collect_workers vs. CPU-Last

- **4–8 Worker**: Sehr wenig CPU-Last, langsam bei vielen Containern
- **16** *(Standard)*: Guter Kompromiss
- **32–49**: Schnell, spürbar mehr Last
- **>49**: Kein Gewinn mehr, nur mehr Overhead

### viewer_timeout (Idle-Modus)

Wenn kein Browser die Seite geöffnet hat, wechselt der Collector automatisch
in den **Idle-Modus**: nur 2 Worker, 60s Interval — minimale Systemlast.

Der Browser sendet alle 10s einen Heartbeat. Kommt kein Heartbeat innerhalb
von `viewer_timeout` Sekunden, aktiviert sich der Idle-Modus. Beim nächsten
Öffnen der Seite wechselt der Collector sofort zurück.

Der **Pause-Button** (⚡) im Header pausiert die Datenerfassung manuell und
versetzt das Backend sofort in den Idle-Modus.

## Sicherheit

- Passwortgeschütztes Login
- **Brute-Force-Schutz**: nach 5 Fehlversuchen innerhalb von 10 Minuten
  wird die IP für 15 Minuten gesperrt
- **Passwort-Bestätigung** für destruktive Aktionen (Neustart, Kill)
- Session-Cookies: `HttpOnly`, `SameSite=Lax`
- Cloudflare-Tunnel-kompatibel (CF-Connecting-IP wird ausgewertet)

## Funktionen

- **Sortierbare Tabelle**: Name, CPU %, RAM %, RAM-Nutzung, NET I/O, DISK I/O, PIDs
- **CPU-Sparkline**: Verlauf der letzten 30 Messungen pro Container
- **Logs**: letzte 200 Zeilen mit Timestamps in einem Modal
- **Neustart** und **Kill (SIGKILL)**: mit Passwort-Bestätigung
- **Auto-Refresh**: Browser passt Interval automatisch an den Backend-Zyklus an
- **Performance-Modus**: Pause-Button + automatischer Idle-Modus
- **System-Stats**: CPU % und RAM % des Hosts (aus `/proc/stat` / `/proc/meminfo`)
- **CPU-Takt**: Kerne × GHz aus `/proc/cpuinfo`
- **Light/Dark Mode**: persistiert in localStorage
- **PWA**: als App auf Desktop und Mobilgerät installierbar
- **Sprache**: DE / EN umschaltbar
