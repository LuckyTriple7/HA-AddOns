# Lizenzen — Nextcloud-Add-on

Dieses Add-on besteht aus mehreren Teilen mit unterschiedlichen Lizenzen.

## Eigene Dateien

`config.yaml`, `Dockerfile`, `rootfs/`, `translations/`, Symbole und die Markdown-Dateien in diesem Verzeichnis stammen aus diesem Repository und stehen unter der **MIT-Lizenz** (siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## Nextcloud

Das Add-on baut auf `lscr.io/linuxserver/nextcloud` auf (Fassung siehe `FROM` im [Dockerfile](Dockerfile)).

- **Nextcloud Server** — **AGPL-3.0**
  Quelltext: <https://github.com/nextcloud/server>
- **LinuxServer.io-Imagebau** — **GPL-3.0**
  Quelltext: <https://github.com/linuxserver/docker-nextcloud>

## Weitere Bestandteile

- **ttyd** (Web-Terminal) — MIT, <https://github.com/tsl0922/ttyd>
- `cifs-utils`, `samba-client`, `mariadb-client`, `jq`, `curl`, `netcat-openbsd` aus den Alpine-Paketquellen, jeweils mit eigener Lizenz

## Was das für das veröffentlichte Image bedeutet

`ghcr.io/luckytriple7/nextcloud` enthält Nextcloud vollständig und ergänzt es um zusätzliche Pakete und eigene Init-Skripte. Es ist damit eine **geänderte Fassung einer AGPL-Arbeit** und steht als Ganzes unter der **AGPL-3.0**. Die MIT-Lizenz der eigenen Dateien ist damit vereinbar; sie gilt für diese Dateien einzeln, nicht für das Gesamtwerk im Image.

### Art der Änderung

Gegenüber dem LinuxServer.io-Image kommen hinzu: Pakete für SMB-Einbindungen und Datenbankzugriff, `ttyd` für ein Web-Terminal über Ingress, ein zusätzlicher s6-Dienst zur WOPI-Aktualisierung sowie `ha-config.sh`, das die Add-on-Optionen in die Nextcloud-Konfiguration überträgt. Nextcloud selbst wird nicht verändert.

### Quelltext

Der vollständige Quelltext besteht aus diesem Verzeichnis und den oben verlinkten Projekten in der im Dockerfile genannten Fassung. Beides ist öffentlich zugänglich.

## Kein Zusammenhang mit den Projekten

Dieses Add-on wird unabhängig gepflegt. Weder Nextcloud GmbH noch LinuxServer.io betreiben oder unterstützen es. „Nextcloud" ist eine Marke der Nextcloud GmbH.

Fehlerberichte zu den Add-on-Skripten und Optionen gehören in [dieses Repository](https://github.com/LuckyTriple7/HA-AddOns/issues), Fehler in Nextcloud selbst zum [Projekt](https://github.com/nextcloud/server/issues).
