# Lizenzen — NPMplus-Add-on

Dieses Add-on besteht aus zwei Teilen mit unterschiedlichen Lizenzen.

## Eigene Dateien

`config.yaml`, `Dockerfile`, `run.sh`, `translations/`, `icon.png`, `logo.png` und die Markdown-Dateien in diesem Verzeichnis stammen aus diesem Repository und stehen unter der **MIT-Lizenz** (siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## NPMplus

Das Add-on baut auf dem offiziellen Image `docker.io/zoeyvid/npmplus` auf. NPMplus steht unter der **GNU Affero General Public License, Version 3 oder später** und ist ein Fork des MIT-lizenzierten nginx-proxy-manager.

- Quelltext: <https://github.com/ZoeyVid/NPMplus>
- Lizenztext: <https://github.com/ZoeyVid/NPMplus/blob/develop/COPYING>
- Verwendete Fassung: siehe `ARG NPMPLUS_VERSION` im [Dockerfile](Dockerfile)

Zusätzlich enthält das Image weitere Bestandteile mit eigenen Lizenzen, unter anderem nginx, GoAccess, Certbot und den CrowdSec-Bouncer.

## Was das für das veröffentlichte Image bedeutet

`ghcr.io/luckytriple7/npmplus` enthält NPMplus vollständig und ersetzt dessen Entrypoint durch `run.sh`. Es ist damit eine **geänderte Fassung einer AGPL-Arbeit** und steht als Ganzes unter der **AGPL-3.0-or-later**. Die MIT-Lizenz der eigenen Dateien ist damit vereinbar; sie gilt für diese Dateien einzeln, nicht für das Gesamtwerk im Image.

### Art der Änderung

Der Entrypoint wird durch `run.sh` ersetzt. Das Skript liest `/data/options.json`, übersetzt die Add-on-Optionen in die Umgebungsvariablen, die NPMplus erwartet, richtet Logs und den CrowdSec-Bouncer ein und übergibt anschließend an das Original-Init des Images. Die Anwendung selbst wird nicht verändert, es kommt kein RUN-Layer hinzu.

### Quelltext

Der vollständige Quelltext der geänderten Fassung besteht aus:

1. diesem Verzeichnis (die eigenen Dateien), und
2. dem Quelltext von NPMplus in der oben genannten Fassung.

Beides ist öffentlich zugänglich. Wer eine Kopie auf anderem Weg benötigt, kann sie über die Issues dieses Repositories anfordern.

## Kein Zusammenhang mit dem NPMplus-Projekt

Dieses Add-on wird unabhängig gepflegt. Das NPMplus-Projekt betreibt es nicht und unterstützt es nicht.

Fehlerberichte zu `run.sh`, den Optionen oder der Dokumentation gehören in [dieses Repository](https://github.com/LuckyTriple7/HA-AddOns/issues). Fehler in NPMplus selbst bittet das Projekt zuerst [dort](https://github.com/ZoeyVid/NPMplus/issues) zu melden.
