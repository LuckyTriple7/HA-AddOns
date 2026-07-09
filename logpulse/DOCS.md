# LogPulse – Dokumentation

## Übersicht

LogPulse liest `systemd-journald` direkt (`/var/log/journal`, read-only über das Supervisor-Flag `journald: true`) und persistiert daraus **alle** Log-Einträge dauerhaft in einer lokalen SQLite-Datenbank: Home Assistant Core, Supervisor, sowie sämtliche Docker-Addon-Container — ohne dass die einzelnen Add-ons dafür angepasst werden müssen.

Im Gegensatz zu reinen Syslog-Forwarder-Addons (z.B. `mib1185/ha-addon-syslog`) sendet LogPulse nichts an einen externen Server, sondern bietet eine durchsuchbare, filterbare Web-Oberfläche direkt in Home Assistant.

---

## Abgrenzung zu SysWatch

- **SysWatch**: Ressourcen-Monitoring (CPU/RAM/Netzwerk/Disk-I/O) + flüchtiger Docker-Log-Tail (letzte 200 Zeilen pro Container, keine Persistenz, verschwindet bei Container-Neustart).
- **LogPulse**: journald-basiert, persistiert *alle* Logs dauerhaft, durchsuchbar (Volltext, Level, Quelle, Zeitraum), kein Docker-Socket-Zugriff nötig.

---

## Add-on Optionen

| Option | Beschreibung | Standard |
|---|---|---|
| `username` | Benutzername für das Web-Interface (nur beim Direktzugriff auf Port 17795 relevant) | `admin` |
| `password` | Passwort für das Web-Interface | `secret` |
| `session_hours` | Gültigkeit einer Login-Session in Stunden | `24` |
| `retention_days` | Log-Einträge älter als diese Anzahl Tage werden automatisch gelöscht | `14` |
| `max_db_size_mb` | Deckelt die Größe der lokalen Log-Datenbank (älteste Einträge zuerst gelöscht) | `300` |
| `poll_timeout_ms` | Intervall, in dem auf neue journald-Einträge geprüft wird | `5000` |
| `verbose_log` | Zusätzliche Debug-Ausgaben im Konsolen-Tab | `false` |

---

## Web-UI

- **Live**: Log-Strom mit Volltextsuche, Level-Filter (DEBUG/INFO/WARNING/ERROR/CRITICAL), Quellen-Filter (HA Core / Supervisor / Add-ons / System)
- **Quellen**: Übersicht aller erkannten Log-Quellen mit Eintrags-Anzahl
- **Gespeichert**: Filter-Kombinationen als Preset speichern (lokal im Browser)
- **Konsole**: Eigendiagnose von LogPulse selbst (Startup-/Fehlermeldungen der App)

---

## Log-Level-Erkennung

Docker setzt bei allen Containern nur grob `stdout → INFO` / `stderr → ERROR` als journald-Priorität — unabhängig vom tatsächlichen Log-Level der Anwendung. LogPulse erkennt das echte Level stattdessen über:

1. Text-Präfix `[INFO]`/`[WARN]`/`[ERROR]` (Format der eigenen Add-ons wie CardBoard, SysWatch, GitPulse)
2. Python-logging-Format von HA Core/Supervisor (`<timestamp> LEVEL (thread) [module] msg`)
3. Fallback: letztes erkanntes Level derselben Quelle (für Traceback-Folgezeilen ohne eigenes Prefix)

---

## Bekannte Einschränkungen

- **Kein Backfill über Boot-Grenzen**: Es werden nur Einträge seit dem letzten Boot erfasst (`this_boot()`). Historie vor der Erstinstallation fehlt.
- **Journal-Rotation auf dem Host**: Falls journald auf dem Host mit knappem `SystemMaxUse` konfiguriert ist, können Einträge bereits vor LogPulse-Ingest rotiert worden sein.
- **Multi-Zeilen-Tracebacks**: journald liefert jede Zeile einzeln. Die Level-Vererbung (siehe oben) mildert das, gruppiert Tracebacks aber nicht zu einem einzelnen Eintrag.
- **AppArmor**: LogPulse liefert (wie sein Vorbild `mib1185/ha-addon-syslog`) kein eigenes `apparmor.txt` aus und verlässt sich auf das Supervisor-Standardprofil + `journald: true`. Falls nach der Installation `apparmor="DENIED"`-Einträge in den Host-Logs auftauchen, bitte im Repo melden.
