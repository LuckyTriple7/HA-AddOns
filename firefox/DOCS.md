# Firefox DE

Firefox-Browser direkt in der Home Assistant Seitenleiste — deutschsprachig, mit persistentem Profil.

## Zugriff

Das Add-on öffnet sich direkt über die HA-Seitenleiste via Ingress (HTTPS).

> **Hinweis:** Die Zwischenablage (Copy/Paste) funktioniert nur über den Ingress-Zugang, nicht über den direkten Port.

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `DISPLAY_WIDTH` | `1280` | Breite des virtuellen Displays in Pixel |
| `DISPLAY_HEIGHT` | `720` | Höhe des virtuellen Displays in Pixel |
| `DARK_MODE` | `0` | Dunkelmodus für die noVNC-Oberfläche (`1` = ein) |
| `VNC_PASSWORD` | — | Optionales Passwort für den VNC-Zugriff |
| `KEEP_APP_RUNNING` | `1` | Firefox bei Absturz automatisch neu starten |
| `TZ` | `Europe/Berlin` | Zeitzone |
| `FF_OPEN_URL` | — | URL die beim Start automatisch geöffnet wird |
| `FF_KIOSK` | `0` | Kiosk-Modus (`1` = ein, kein Browser-Chrome) |
| `FF_CUSTOM_ARGS` | — | Zusätzliche Firefox-Startparameter |
| `memory_limit_mb` | `0` | RAM-Limit in MB (`0` = kein Limit, Empfehlung: 512–2048) |

## RAM-Begrenzung

Mit `memory_limit_mb` werden folgende Firefox-Einstellungen automatisch gesetzt:

- Disk-Cache: 25 % des Limits
- Memory-Cache: 12,5 % des Limits
- Content-Prozesse: nur 1 (statt Standard 8)
- Back/Forward-Cache: deaktiviert

## Persistente Daten

- **Profil:** `/data/profile` — bleibt über Neustarts und Updates erhalten
- **Downloads:** `/share/firefox`

---

# Firefox DE (English)

Firefox browser directly in the Home Assistant sidebar — German language, with persistent profile.

## Access

The add-on opens directly via the HA sidebar through Ingress (HTTPS).

> **Note:** The clipboard (copy/paste) only works via Ingress access, not via the direct port.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `DISPLAY_WIDTH` | `1280` | Width of the virtual display in pixels |
| `DISPLAY_HEIGHT` | `720` | Height of the virtual display in pixels |
| `DARK_MODE` | `0` | Dark mode for the noVNC interface (`1` = on) |
| `VNC_PASSWORD` | — | Optional password for VNC access |
| `KEEP_APP_RUNNING` | `1` | Automatically restart Firefox if it crashes |
| `TZ` | `Europe/Berlin` | Timezone |
| `FF_OPEN_URL` | — | URL to open automatically on startup |
| `FF_KIOSK` | `0` | Kiosk mode (`1` = on, no browser chrome) |
| `FF_CUSTOM_ARGS` | — | Additional Firefox startup arguments |
| `memory_limit_mb` | `0` | RAM limit in MB (`0` = no limit, recommended: 512–2048) |

## RAM Limit

With `memory_limit_mb` set, the following Firefox settings are applied automatically:

- Disk cache: 25% of the limit
- Memory cache: 12.5% of the limit
- Content processes: 1 only (instead of default 8)
- Back/forward cache: disabled

## Persistent Data

- **Profile:** `/data/profile` — survives restarts and updates
- **Downloads:** `/share/firefox`
