# Firefox

Firefox-Browser direkt als Home Assistant Add-on — mit persistentem Profil, deutscher Sprache und optionaler RAM-Begrenzung.

## Installation

Dieses Add-on ist Teil des [LuckyTriple7 HA Add-Ons Repository](https://github.com/LuckyTriple7/HA-AddOns).

## Konfiguration

| Option | Standard | Beschreibung |
|---|---|---|
| `memory_limit_mb` | `0` | RAM-Limit für Firefox in MB. `0` = kein Limit. Empfehlung: `512`–`2048`. |

## RAM-Begrenzung

Firefox kann ohne Einschränkung sehr viel RAM verbrauchen. Mit `memory_limit_mb` werden folgende Firefox-Einstellungen über `user.js` gesetzt:

- **Disk-Cache**: 25 % des Limits (in KB)
- **Memory-Cache**: 12,5 % des Limits (in KB)
- **Content-Prozesse**: nur 1 (statt Standard: 8)
- **Back/Forward-Cache**: deaktiviert

Beispiel: `memory_limit_mb: 1024` → 256 MB Disk-Cache, 128 MB Memory-Cache.

## Technischer Aufbau

Das Add-on baut sein eigenes Docker-Image auf Basis von `debian:bookworm-slim`:

- **Firefox ESR** — aktuell aus Debian-Paketen, inklusive `firefox-esr-l10n-de`
- **Xvfb** — virtuelles Display
- **x11vnc** — VNC-Server auf dem virtuellen Display
- **noVNC + websockify** — Browser-basierter VNC-Client auf Port 5800

## Automatische Updates

GitHub Actions prüft täglich die aktuelle Firefox ESR Version via [Mozilla Product Details API](https://product-details.mozilla.org/1.0/firefox_versions.json). Bei einer neuen Version wird automatisch ein neues Docker-Image gebaut, zu GHCR gepusht und ein Pull Request erstellt.

## Ursprung

Inspiriert von [mincka/ha-addons/firefox](https://github.com/mincka/ha-addons/tree/main/firefox).
