# Firefox DE

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Docker](https://img.shields.io/badge/docker-ghcr.io-blue?style=flat-square&logo=docker)

Firefox-Browser direkt als Home Assistant Add-on — in der HA-Seitenleiste via noVNC, deutschsprachig, mit persistentem Profil.

## Installation

Dieses Add-on ist Teil des [LuckyTriple7 HA Add-Ons Repository](https://github.com/LuckyTriple7/HA-AddOns).

## Konfiguration

| Option | Standard | Beschreibung |
|---|---|---|
| `DISPLAY_WIDTH` | `1280` | Breite des virtuellen Displays in Pixel |
| `DISPLAY_HEIGHT` | `720` | Höhe des virtuellen Displays in Pixel |
| `DARK_MODE` | `0` | Dunkelmodus für die noVNC-Oberfläche (`1` = ein) |
| `VNC_PASSWORD` | `` | Optionales Passwort für den VNC-Zugriff |
| `KEEP_APP_RUNNING` | `1` | Firefox bei Absturz automatisch neu starten |
| `TZ` | `Europe/Berlin` | Zeitzone |
| `FF_OPEN_URL` | `` | URL die beim Start geöffnet wird |
| `FF_KIOSK` | `0` | Kiosk-Modus (`1` = ein, kein Browser-Chrome) |
| `FF_CUSTOM_ARGS` | `` | Zusätzliche Firefox-Startparameter |
| `memory_limit_mb` | `0` | RAM-Limit in MB. `0` = kein Limit. Empfehlung: `512`–`2048`. |

## Zwischenablage (Copy/Paste)

Die Zwischenablage funktioniert nur wenn das Add-on über die HA-Seitenleiste geöffnet wird (HTTPS-Ingress). Direktzugriff über `http://IP:5800` unterstützt keine Clipboard-Synchronisation.

## RAM-Begrenzung

Mit `memory_limit_mb` werden folgende Firefox-Einstellungen gesetzt:

- **Disk-Cache**: 25 % des Limits
- **Memory-Cache**: 12,5 % des Limits
- **Content-Prozesse**: nur 1 (statt Standard: 8)
- **Back/Forward-Cache**: deaktiviert

## Technischer Aufbau

- **Base-Image**: `jlesage/baseimage-gui` — VNC, noVNC und Window Manager bereits enthalten
- **Firefox ESR** — deutsche Version, direkt von Mozilla geladen
- **Software-Rendering** — kein GPU erforderlich (`LIBGL_ALWAYS_SOFTWARE`, `gfx.webrender.software`)
- **Persistentes Profil** in `/data/profile`
- **Downloads** in `/share/firefox`
- Nur **amd64**

## Automatische Updates

GitHub Actions prüft täglich die aktuelle Firefox ESR Version. Bei einer neuen Version wird automatisch ein neues Docker-Image gebaut und zu GHCR gepusht.
