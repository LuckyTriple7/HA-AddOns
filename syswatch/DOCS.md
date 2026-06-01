# HA SysWatch — Dokumentation

## Voraussetzungen

Dieses Add-on benötigt Zugriff auf den Docker-Socket des Hosts.
In der `config.yaml` ist daher `full_access: true` gesetzt.

## Konfiguration

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `username` | string | `admin` | Login-Benutzername |
| `password` | string | `secret` | Login-Passwort |
| `session_hours` | int | `24` | Session-Dauer in Stunden |
| `refresh_interval` | int | `10` | Standard-Aktualisierungsintervall in Sekunden |
| `show_stopped` | bool | `false` | Gestoppte Container standardmäßig anzeigen |

## Zugriff

Das Web-Interface ist erreichbar unter:

```
http://<HA-IP>:17790
```

## Sicherheit

- Passwortgeschütztes Login
- Brute-Force-Schutz: nach 5 Fehlversuchen innerhalb von 10 Minuten wird die IP für 15 Minuten gesperrt
- Session-Cookies: `HttpOnly`, `SameSite=Lax`
- Cloudflare-Tunnel-kompatibel (CF-Connecting-IP wird ausgewertet)

## Funktionen

- **Tabelle**: sortierbar nach Name, CPU %, RAM %, RAM-Nutzung, NET I/O, DISK I/O, PIDs
- **Verlauf**: CPU-Sparkline der letzten 30 Messwerte (5-Sekunden-Takt)
- **Logs**: letzte 200 Zeilen mit Timestamps in einem Modal
- **Neustart**: Container neu starten (mit Bestätigungsdialog)
- **PWA**: als App auf Desktop und Mobilgerät installierbar
- **Sprache**: DE / EN umschaltbar
