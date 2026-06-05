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

### Telegram-Benachrichtigungen

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `telegram_bot_token` | string | `""` | Bot-Token (leer = komplett deaktiviert) |
| `telegram_chat_id` | string | `""` | Empfänger-Chat-ID (**optional** — wird automatisch erkannt) |
| `notify_cpu_threshold` | int | `0` | CPU-Schwellenwert in % (0 = aus) |
| `notify_ram_threshold` | int | `0` | RAM-Schwellenwert in % (0 = aus) |
| `notify_over_duration` | int | `0` | Sekunden über Schwellenwert vor Alarm-Auslösung |
| `notify_clear_duration` | int | `120` | Sekunden unter Schwellenwert vor Entwarnung |

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

### Übersichts-Kacheln

- **HA Status**: Supervisor / Support / Health aus der Supervisor API — grün / gelb / rot
- **Laufend**: Anzahl laufender Container, Sub-Label zeigt Gesamtanzahl
- **CPU Gesamt**: Summe CPU aller laufenden Container
- **RAM Genutzt**: Summe RAM aller laufenden Container
- **SYS CPU / SYS RAM**: Host-Auslastung aus `/proc`

Der **Footer** zeigt HA Core-, Supervisor- und OS-Version (60 s Cache).

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
Ein Klick auf einen Host-Port öffnet `http://<host-ip>:<port>` direkt im Browser.
Die Host-IP wird automatisch aus der Supervisor Netzwerk-API gelesen.

### Telegram-Benachrichtigungen

#### Einrichtung

1. Bot erstellen via `@BotFather` → `/newbot` — Token kopieren
2. `telegram_bot_token` in der Add-on-Konfiguration eintragen
3. Bot in Telegram öffnen und `/start` schicken
4. SysWatch erkennt die Chat-ID automatisch und sendet eine Bestätigung — fertig

`telegram_chat_id` ist **optional**. Wird sie leer gelassen, lernt SysWatch sie
automatisch beim ersten Kontakt. Wird sie explizit gesetzt, wird nur genau diese
Chat-ID akzeptiert (empfohlen für geteilte Bots).

Token leer → Telegram komplett deaktiviert (kein Polling, kein Log-Eintrag).

#### Benachrichtigungsereignisse

| Ereignis | Nachricht |
|---|---|
| Add-on gestartet (einmalig) | 🟢 HA SysWatch gestartet — mit HA-Version, Container-Anzahl, Host-IP |
| Container crasht / von HA gestoppt | 💥 Container unerwartet gestoppt + **▶ Starten**-Button |
| Container startet (nicht via SysWatch) | ▶️ Container gestartet |
| CPU über Schwellenwert | ⚠️ Hohe CPU-Last + Top 5 CPU-Verbraucher |
| CPU zurück unter Schwellenwert | ✅ CPU-Last normal |
| RAM über Schwellenwert | ⚠️ Hohe RAM-Auslastung + Top 5 RAM-Verbraucher (GiB + %) |
| RAM zurück unter Schwellenwert | ✅ RAM-Auslastung normal |

Stop/Kill/Start über die SysWatch-UI löst **keine** Benachrichtigung aus.
CPU/RAM-Alerts haben einen 10-Minuten-Cooldown zwischen gleichen Meldungen.

#### Inline-Keyboard — Container per Telegram starten

Wenn ein Container unerwartet stoppt, enthält die Telegram-Nachricht einen
**▶ Starten**-Button. Ein Klick startet den Container direkt aus Telegram heraus
(Docker-Versuch, Fallback auf Supervisor API). Die Nachricht wird dann automatisch
auf ✅ aktualisiert sobald der Container wieder läuft — der Button verschwindet.

#### Top-5-Verbraucher in Alerts

CPU-Alarme zeigen die 5 Container mit der höchsten CPU-Last.
RAM-Alarme zeigen die 5 Container mit dem höchsten RAM-Verbrauch (Größe + %):

```
Top 5 RAM:
  1. addon_nextcloud: 1.8 GiB (18.4%)
  2. homeassistant: 1.2 GiB (12.1%)
  3. addon_collabora: 876.3 MiB (8.7%)
  ...
```

#### Logging

Jede ausgehende Telegram-Nachricht erscheint im HA-Add-on-Log:
```
[Telegram] → 🟢 HA SysWatch gestartet …
[Telegram] Gesendet.
[Telegram] Fehlgeschlagen: …   ← bei Netzwerkproblemen
```

#### Verzögerungslogik

- `notify_over_duration = 60`: CPU/RAM muss 60 s ununterbrochen über dem Schwellenwert
  liegen bevor der Alarm ausgelöst wird — verhindert Alarme bei kurzen Spitzen
- `notify_clear_duration = 120`: CPU/RAM muss 120 s ununterbrochen unter dem
  Schwellenwert liegen bevor die Entwarnung gesendet wird

### Header-Elemente

- **Modus-Dot**: grün = aktiv, gelb = idle, rot = pausiert
- **Zyklus-Label**: zeigt den tatsächlichen Browser-Refresh-Zyklus in Sekunden
- **Countdown**: Sekunden bis zur nächsten Aktualisierung
- **📨 Test**: sendet sofort eine Test-Telegram-Nachricht mit aktuellen Top-5-Werten (nur Desktop)
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
- Telegram-Callbacks: nur konfigurierte oder auto-erkannte Chat-ID wird akzeptiert

## Gesicherter Modus (Protection Mode)

Nach der Installation zeigt HA eine Warnung: **"Gesicherter Modus deaktiviert"**.
Das ist korrekt und muss manuell bestätigt werden.

SysWatch benötigt `docker_api: true` um den Docker-Socket (`/var/run/docker.sock`)
einzubinden — ohne diesen können keine Container-Stats gelesen werden.
HA deaktiviert den gesicherten Modus automatisch wenn `docker_api: true` gesetzt ist.

**In der HA Add-on UI:** Reiter „Info" → Schalter „Gesicherter Modus" auf **Aus** stellen.
