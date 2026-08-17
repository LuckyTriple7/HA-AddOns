# Lizenzen — Collabora-Online-Add-on

Dieses Add-on besteht aus zwei Teilen mit unterschiedlichen Lizenzen.

## Eigene Dateien

`config.yaml`, `Dockerfile`, `run.sh`, `translations/`, Symbole und die Markdown-Dateien in diesem Verzeichnis stammen aus diesem Repository und stehen unter der **MIT-Lizenz** (siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## Collabora Online

Das Add-on kopiert die Nutzlast aus dem offiziellen Image `collabora/code` auf ein eigenes Debian-Laufzeit-Image — `coolwsd` samt Hilfsprogrammen, `/usr/share/coolwsd`, `/etc/coolwsd`, `/opt/collaboraoffice` und `/opt/cool`.

Collabora Online (CODE, Collabora Online Development Edition) steht unter der **Mozilla Public License, Version 2.0**. Es enthält Bestandteile von LibreOffice, die unter der MPL-2.0 und der LGPL-3.0 stehen.

- Quelltext: <https://github.com/CollaboraOnline/online>
- Lizenztext: <https://github.com/CollaboraOnline/online/blob/master/COPYING>
- Herkunft der Binärdateien: Image `collabora/code`, Tag `latest-amd64` zum Zeitpunkt des Builds

> **Hinweis zur Nachvollziehbarkeit:** Der Dockerfile verwendet den beweglichen Tag `latest-amd64`. Welche Fassung in einem bestimmten Image steckt, verrät `coolwsd --version` im laufenden Container.

## Was das für das veröffentlichte Image bedeutet

`ghcr.io/luckytriple7/collabora` enthält Collabora Online in Binärform. Die MPL-2.0 ist eine dateibezogene Copyleft-Lizenz: die MPL-lizenzierten Bestandteile bleiben unter der MPL-2.0, auch wenn sie mit anderer Software in einem Image liegen. Die eigenen Dateien des Add-ons bleiben MIT-lizenziert.

Nach MPL-2.0 §3.2 muss bei der Weitergabe in ausführbarer Form auf die Herkunft des Quelltextes hingewiesen werden — das leistet die Verlinkung oben.

## Marke

„Collabora" und „Collabora Online" sind Marken der Collabora Ltd. Dieses Add-on wird unabhängig gepflegt; Collabora betreibt es nicht und unterstützt es nicht.

Fehlerberichte zu `run.sh`, den Optionen oder der Dokumentation gehören in [dieses Repository](https://github.com/LuckyTriple7/HA-AddOns/issues), Fehler in Collabora Online selbst zum [Projekt](https://github.com/CollaboraOnline/online/issues).
