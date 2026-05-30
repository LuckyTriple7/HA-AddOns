# WebDock – Dokumentation

## Übersicht

WebDock ist ein passwortgeschützter Startportal für bis zu 10 interne Web-Dienste (z. B. Grafana, Portainer, Node-RED, Frigate, ...). Die Startseite zeigt alle konfigurierten Dienste mit Online-Status-Anzeige (grüner/roter Punkt) und ermöglicht den direkten Zugriff über einen eingebauten Reverse-Proxy.

## Konfiguration

### Benutzername & Passwort

```yaml
username: "admin"
password: "geheim"
session_hours: 24
```

### Web-Dienste anlegen

Bis zu 10 Dienste können in der `sites`-Liste konfiguriert werden:

```yaml
sites:
  - name: "Grafana"
    host: "192.168.1.100"
    port: 3000
    icon: "grafana.png"
    enabled: true
  - name: "Portainer"
    host: "192.168.1.100"
    port: 9000
    icon: "portainer.png"
    enabled: true
```

| Feld      | Beschreibung                                               |
|-----------|-------------------------------------------------------------|
| `name`    | Anzeigename des Dienstes                                   |
| `host`    | IP-Adresse des Dienstes (z. B. `192.168.1.100`)            |
| `port`    | Port des Dienstes                                          |
| `icon`    | Dateiname einer PNG-Datei im addon_config-Ordner (optional)|
| `enabled` | `true` / `false` – Dienst anzeigen oder ausblenden         |

### Icons hinterlegen

PNG-Dateien einfach in den **addon_config**-Ordner des Add-ons legen (über den Datei-Editor oder SSH):

```
/addon_configs/web-dock/mein-icon.png
```

Im `icon`-Feld dann nur den Dateinamen angeben: `icon: "mein-icon.png"`.

Falls kein Icon angegeben oder die Datei nicht gefunden wird, erscheint ein Standard-Globus-Symbol.

## Zugriff

Das Portal ist unter Port **17780** erreichbar.  
Jeder Dienst wird unter `/proxy/site0/`, `/proxy/site1/`, ... weitergeleitet.
