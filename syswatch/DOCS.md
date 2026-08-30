# HA SysWatch — Dokumentation

## Voraussetzungen

Dieses Add-on benötigt Zugriff auf den Docker-Socket des Hosts.
`docker_api: true` in der `config.yaml` bindet `/var/run/docker.sock` korrekt ein.

Für gestoppte HA Add-ons (deren Docker-Container HA beim Stoppen entfernt) wird
zusätzlich die **Supervisor API** genutzt (`hassio_api: true`, `hassio_role: manager`).

## Port

`17790`

## Konfiguration

### Allgemein

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `username` | string | `admin` | Login-Benutzername |
| `password` | string | `secret` | Login-Passwort (auch für Start/Stop/Neustart/Kill benötigt) |
| `session_hours` | int | `24` | Session-Dauer in Stunden |
| `show_stopped` | bool | `true` | Gestoppte Container standardmäßig anzeigen |
| `verbose_log` | bool | `false` | Pro Zyklus Anzahl Container, Worker und Dauer loggen |

### Performance

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `collect_interval` | int | `3` | Pause zwischen Docker-Abfragen in Sekunden (min. 2) |
| `collect_workers` | int | `16` | Parallele Docker-Stats-Abfragen (4–64) |
| `viewer_timeout` | int | `180` | Idle-Timeout in Sekunden (30–1800) |
| `size_interval` | int | `15` | Abstand der Größenabfrage (`docker system df`) in Minuten (0 = aus, 1–1440) |

### Telegram-Benachrichtigungen

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `telegram_bot_token` | string | `""` | Bot-Token (leer = komplett deaktiviert) |
| `telegram_chat_id` | string | `""` | Empfänger-Chat-ID (**optional** — wird automatisch erkannt) |
| `notify_cpu_threshold` | int | `0` | CPU-Schwellenwert in % (0 = aus) |
| `notify_ram_threshold` | int | `0` | RAM-Schwellenwert in % (0 = aus) |
| `notify_disk_threshold` | int | `0` | Speicher-Schwellenwert in % belegt (0 = aus) |
| `notify_over_duration` | int | `0` | Sekunden über Schwellenwert vor Alarm-Auslösung |
| `notify_clear_duration` | int | `120` | Sekunden unter Schwellenwert vor Entwarnung |

## Performance-Tuning

### collect_interval und collect_workers

`docker stats --no-stream` braucht pro Container ~1 s (Docker-Daemon-Messintervall) —
das ist der unvermeidliche Flaschenhals, unabhängig von der Worker-Anzahl.

**Beispiel mit 49 Containern:**

| collect_workers | Abfragezeit | + collect_interval | = Browser-Zyklus |
|---|---|---|---|
| 16 | ~4 s | 3 s | ~7 s |
| 32 | ~2,5 s | 3 s | ~5,5 s |
| 49 | ~2 s | 3 s | ~5 s |
| 49 | ~2 s | 1 s | ~3 s |

### viewer_timeout (Idle-Modus)

Wenn kein Browser geöffnet ist, wechselt der Collector in den **Idle-Modus**:
nur 2 Worker, 60 s Interval — minimale Systemlast. Beim nächsten Öffnen sofort zurück in Aktiv-Modus.
Der **Pause-Button** (⚡) pausiert die Datenerfassung manuell.

## Funktionen

### Übersichts-Kacheln

| Kachel | Inhalt | Klickbar |
|---|---|---|
| HA Status | Supervisor / Support / Health — grün / gelb / rot | — |
| Laufend | Laufende Container / Gesamt | — |
| CPU Gesamt | Summe CPU aller laufenden Container | — |
| RAM Genutzt | Summe RAM aller laufenden Container | — |
| SYS CPU | Host-CPU-Auslastung als Balken + % | ✅ → 24h-Chart |
| SYS RAM | Host-RAM-Auslastung als Balken + % | ✅ → 24h-Chart |
| Speicher frei | Freier Platz der Datenpartition, Balken = Belegung | ✅ Links → Detail-Dialog, Rechts → Größenabfrage |

**Balken-Farbskala (SYS CPU / SYS RAM / Speicher):** grün ≤70 % · gelb ≤80 % · orange ≤90 % · rot >90 %

Der **Footer** zeigt HA Core-, Supervisor- und OS-Version (60 s Cache).

### 24h-Verlaufscharts

Klick auf **SYS CPU** oder **SYS RAM** öffnet ein Diagramm mit dem 24-Stunden-Verlauf:
- Farbkodierte Linie (grün/gelb/orange/rot nach Schwellenwert)
- Area-Fill in Durchschnittsfarbe
- Zeitachse mit Stunden-Markierungen
- Aktueller Wert als farbiger Punkt

Die Daten werden **minütlich** in einer SQLite-Datenbank gespeichert
(`/config/syswatch_history.db`, max. 1440 Einträge = 24 h) und überleben Neustarts.

### CPU-Temperatur

Unterhalb des CPU-Charts werden alle verfügbaren Kern-Temperaturen angezeigt
(Package + Core 0–N), ausgelesen aus `/sys/class/hwmon/` (`coretemp`/`k10temp`-Treiber).

**Farbskala:** grün < 60°C · gelb < 75°C · orange < 90°C · rot ≥ 90°C

Klick auf einen Temperaturwert öffnet das **Temperatur-Verlaufsdiagramm (24h)**:
- Y-Achse in °C
- Gestrichelte Referenzlinien bei 60 / 75 / 90°C
- ← Zurück-Button navigiert zurück zum CPU-Chart

Lüfterdrehzahlen werden angezeigt wenn `fan*_input`-Einträge in `hwmon` vorhanden sind
(hardware- und treiberabhängig).

### Container-Tabelle

- **Sortierbare Spalten**: Name, CPU %, RAM %, RAM-Nutzung, NET I/O, DISK I/O, PIDs, Größe
- Sortierung wird in `localStorage` gespeichert
- **CPU-Sparkline**: Verlauf der letzten 30 Messungen pro Container
- **Status-Badge**: running, exited, paused, stopped
- **Suchfeld**: filtert nach Name oder Image

### Speicherplatz und Container-Größen

**Kachel „Speicher frei“** zeigt den freien Platz der HA-Datenpartition. Die Werte kommen
primär von der Supervisor-API (`/host/info`), Fallback ist `statvfs` auf `/config`, `/data`
oder `/`. Der Tooltip listet die Docker-Aufteilung (Images / Container / Volumes) samt
Zeitstempel der letzten Größenabfrage. Ein Klick startet die Abfrage sofort neu.

**Linksklick auf die Kachel** öffnet den Dialog **Speicherplatz** mit:

- Datenpartition: Balken, freier/belegter Platz, Quelle der Werte
- Docker-Aufteilung: Images, Container, Volumes, Build-Cache, Gesamtsumme und
  **freigebbar** (Summe der exklusiven Layer aller Images ohne Container)
- **Größte Images** (Top 25) mit Größe, geteiltem Anteil und Anzahl nutzender Container —
  ungenutzte Images sind gelb markiert
- **Größte Container** (Top 10) mit `SizeRw` und `SizeRootFs`
- **Größte Volumes** (Top 15), unbenutzte gelb markiert

**Rechtsklick auf die Kachel** startet die Größenabfrage sofort; im Dialog macht das der
Button „Neu berechnen“. Die Oberfläche pollt danach alle 3 s, bis ein neuer Zeitstempel
vorliegt — der Scan darf also ruhig Minuten dauern.

**Hinweis zu Image-Größen:** `Size` einer Image-Zeile enthält gemeinsam genutzte Layer mit,
`davon geteilt` beziffert diesen Anteil. Beim Löschen wird nur die Differenz frei. Die
Zeile „Images“ in der Docker-Aufteilung nutzt deshalb `LayersSize` (entdoppelt) und ist
kleiner als die Summe der Einzelzeilen.

**Spalte „Größe“** zeigt pro Container `SizeRw` — die beschreibbare Schicht, also alles was
seit dem Image dazugekommen ist. Der Tooltip nennt zusätzlich `SizeRootFs` (inkl. aller
Image-Layer). Solange noch keine Abfrage gelaufen ist, steht dort `…`.

Die Daten stammen aus `docker system df`. Diese Abfrage scannt das Dateisystem und dauert je
nach System Sekunden bis Minuten — sie läuft deshalb in einem **eigenen Hintergrund-Thread**
und standardmäßig nur alle 15 Minuten (`size_interval`), unabhängig vom Stats-Zyklus.

> **Wichtig:** Docker-Logfiles (`/var/lib/docker/containers/<id>/<id>-json.log`) zählen
> **nicht** zu `SizeRw`. Ein Container mit kleiner Größe kann die Platte trotzdem über sein
> Log füllen. Dagegen hilft ein Log-Limit in `/etc/docker/daemon.json`
> (`"log-opts": {"max-size": "10m", "max-file": "3"}`) — das ist eine Host-Einstellung, die
> SysWatch nicht setzen kann. Der Speicher-Alarm (`notify_disk_threshold`) schlägt aber
> unabhängig von der Ursache an, bevor die Platte voll läuft.

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

**Ports**-Button → Modal mit allen Host-Port-Mappings (sortierbar, Suchfeld).
Klick auf einen Host-Port öffnet `http://<host-ip>:<port>` direkt im Browser.
Die Host-IP wird automatisch aus der Supervisor Netzwerk-API gelesen.

### Telegram-Benachrichtigungen

#### Einrichtung

1. Bot erstellen via `@BotFather` → `/newbot` — Token kopieren
2. `telegram_bot_token` in der Add-on-Konfiguration eintragen
3. Bot in Telegram öffnen und `/start` schicken
4. SysWatch erkennt die Chat-ID automatisch und bestätigt per Nachricht

`telegram_chat_id` ist **optional**. Leer lassen → automatische Erkennung.
Explizit setzen → nur diese Chat-ID wird akzeptiert (empfohlen bei geteilten Bots).
**Token leer → Telegram komplett deaktiviert** (kein Polling, kein Log-Eintrag).

#### Benachrichtigungsereignisse

| Ereignis | Nachricht |
|---|---|
| Add-on gestartet (einmalig) | 🟢 Startmeldung mit HA/Supervisor/OS-Version, Container-Anzahl, Host-IP |
| Container crasht / von HA gestoppt | 💥 Alert + **▶ Starten**-Button |
| Container startet (nicht via SysWatch) | ▶️ Container gestartet |
| CPU über Schwellenwert | ⚠️ CPU-Alert + Top 5 CPU-Verbraucher |
| CPU wieder normal | ✅ Entwarnung |
| RAM über Schwellenwert | ⚠️ RAM-Alert + Top 5 Verbraucher (GiB + %) |
| RAM wieder normal | ✅ Entwarnung |

Stop/Kill/Start über die SysWatch-UI löst **keine** Benachrichtigung aus.
CPU/RAM-Alerts haben einen 10-Minuten-Cooldown zwischen gleichen Meldungen.

#### Inline-Keyboard — Container per Telegram starten

Wenn ein Container unerwartet stoppt, enthält die Nachricht einen **▶ Starten**-Button.
Klick startet den Container direkt aus Telegram (Docker, Fallback: Supervisor API).
Die Nachricht wird auf ✅ aktualisiert sobald der Container wieder läuft.

#### Top-5-Verbraucher in Alerts

CPU-Alarme zeigen die 5 Container mit der höchsten CPU-Last.
RAM-Alarme zeigen die 5 Container mit dem höchsten RAM-Verbrauch:

```
Top 5 RAM:
  1. addon_nextcloud: 1.8 GiB (18.4%)
  2. homeassistant: 1.2 GiB (12.1%)
  3. addon_collabora: 876.3 MiB (8.7%)
```

#### Verzögerungslogik

- `notify_over_duration = 60`: CPU/RAM muss 60 s dauerhaft über dem Schwellenwert liegen
  bevor der Alarm ausgelöst wird — verhindert Alarme bei kurzen Spitzen
- `notify_clear_duration = 120`: CPU/RAM muss 120 s dauerhaft darunter liegen
  bevor die Entwarnung gesendet wird

### Header-Elemente

| Element | Funktion |
|---|---|
| Modus-Dot | grün = aktiv, gelb = idle, rot = pausiert |
| Zyklus-Label | tatsächlicher Browser-Refresh-Zyklus in Sekunden |
| Countdown | Sekunden bis zur nächsten Aktualisierung |
| 📨 Test | Test-Telegram-Nachricht senden (nur Desktop) |
| ⟳ Refresh | sofortige manuelle Aktualisierung |
| ⚡ Pause | Datenerfassung pausieren / fortsetzen |
| ☀/🌙 | Hell/Dunkel-Modus wechseln |

## Sicherheit

- Passwortgeschütztes Login
- **Brute-Force-Schutz**: nach 5 Fehlversuchen / 10 Minuten → IP 15 Minuten gesperrt
- **Passwortbestätigung** für Start, Stop, Neustart, Kill
- Session-Cookies: `HttpOnly`, `SameSite=Lax`
- Cloudflare-Tunnel-kompatibel (`CF-Connecting-IP`)
- Telegram-Callbacks: nur konfigurierte oder auto-erkannte Chat-ID akzeptiert

## Gesicherter Modus (Protection Mode)

Nach der Installation zeigt HA: **"Gesicherter Modus deaktiviert"** — das ist korrekt.

SysWatch benötigt `docker_api: true` für den Docker-Socket.
HA deaktiviert den gesicherten Modus automatisch wenn `docker_api: true` gesetzt ist.

**In der HA Add-on UI:** Reiter „Info" → Schalter „Gesicherter Modus" auf **Aus** stellen.
