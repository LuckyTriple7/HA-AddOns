# Lizenzen — Anubis-Add-on

Dieses Add-on besteht aus zwei Teilen mit unterschiedlichen Lizenzen.

## Eigene Dateien

`config.yaml`, `Dockerfile`, `run.sh`, `policy.default.yaml`, `translations/` und die Markdown-Dateien in diesem Verzeichnis stammen aus diesem Repository und stehen unter der **MIT-Lizenz** (siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## Anubis

Das Add-on kopiert das statische Binary aus dem offiziellen Image `ghcr.io/techarohq/anubis` in ein eigenes, schlankes Alpine-Image. Anubis selbst steht unter der **MIT-Lizenz**.

- Quelltext: <https://github.com/TecharoHQ/anubis>
- Lizenztext: <https://github.com/TecharoHQ/anubis/blob/main/LICENSE>
- Verwendete Fassung: siehe `ARG ANUBIS_VERSION` im [Dockerfile](Dockerfile)

## Was das für das veröffentlichte Image bedeutet

`ghcr.io/luckytriple7/anubis` enthält nur das Anubis-Binary aus dem Original-Image, mit `run.sh` als eigenem Entrypoint davor. Die Anwendung selbst wird nicht verändert. Da beide Teile unter der MIT-Lizenz stehen, gilt sie auch für das Gesamtbild.

## Kein Zusammenhang mit dem Anubis-Projekt

Dieses Add-on wird unabhängig gepflegt. Das Anubis-Projekt (Techaro) betreibt es nicht und unterstützt es nicht.

Fehlerberichte zu `run.sh`, den Optionen, der mitgelieferten Policy oder der Dokumentation gehören in [dieses Repository](https://github.com/LuckyTriple7/HA-AddOns/issues). Fehler in Anubis selbst bittet das Projekt zuerst [dort](https://github.com/TecharoHQ/anubis/issues) zu melden.
