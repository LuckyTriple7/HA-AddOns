# LogPulse

Zentrale, durchsuchbare Log-Historie aus journald — Home Assistant Core, Supervisor und alle Add-on-Container.

Liest `/var/log/journal` direkt (keine Weiterleitung an externe Server, kein `full_access`/`docker_api` nötig) und persistiert alle Einträge lokal in SQLite. Web-UI mit Volltextsuche, Level- und Quellen-Filtern.

Siehe [DOCS.md](DOCS.md) für Details, Optionen und Abgrenzung zu [SysWatch](../syswatch/).
