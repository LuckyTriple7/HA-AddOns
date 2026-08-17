# Lizenzen — Signal-Add-on

Dieses Add-on besteht aus mehreren Teilen mit unterschiedlichen Lizenzen.

## Eigene Dateien

Die Chat-Oberfläche (`server.js`, `package.json`, statische Dateien), `config.yaml`, `Dockerfile`, `run.sh`, `translations/`, Symbole und die Markdown-Dateien in diesem Verzeichnis stammen aus diesem Repository und stehen unter der **MIT-Lizenz** (siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## Basisimage und dessen Bestandteile

Das Add-on baut auf `bbernhard/signal-cli-rest-api` auf.

| Bestandteil | Lizenz | Quelltext |
|---|---|---|
| **signal-cli-rest-api** | MIT | <https://github.com/bbernhard/signal-cli-rest-api> |
| **signal-cli** | **GPL-3.0** | <https://github.com/AsamK/signal-cli> |
| **libsignal** | **AGPL-3.0** | <https://github.com/signalapp/libsignal> |

Dazu kommen Node.js, npm und die im [Dockerfile](Dockerfile) genannten Debian-Pakete mit jeweils eigener Lizenz.

> **Hinweis zur Nachvollziehbarkeit:** Der Dockerfile verwendet den beweglichen Tag `latest`. Welche Fassung in einem bestimmten Image steckt, verrät `signal-cli --version` im laufenden Container.

## Was das für das veröffentlichte Image bedeutet

`ghcr.io/luckytriple7/signal` enthält mit signal-cli und libsignal Software unter **GPL-3.0** beziehungsweise **AGPL-3.0**. Für das Gesamtwerk im Image gelten damit die Bedingungen dieser Lizenzen; die eigenen Dateien des Add-ons bleiben einzeln MIT-lizenziert und sind damit vereinbar.

Die Chat-Oberfläche ist ein eigenständiges Programm, das ausschließlich über die HTTP-Schnittstelle von signal-cli-rest-api mit den GPL-Bestandteilen spricht. Sie bindet keinen GPL-Code ein.

Der Quelltext aller Bestandteile ist über die Links oben öffentlich zugänglich.

## Kein Zusammenhang mit Signal

Dieses Add-on wird unabhängig gepflegt. Weder die Signal Foundation noch Signal Messenger LLC betreiben oder unterstützen es. „Signal" ist eine Marke der Signal Foundation. signal-cli ist ein inoffizieller Client, kein Erzeugnis von Signal.

Fehlerberichte zur Chat-Oberfläche und den Optionen gehören in [dieses Repository](https://github.com/LuckyTriple7/HA-AddOns/issues), Fehler in signal-cli zum [Projekt](https://github.com/AsamK/signal-cli/issues).
