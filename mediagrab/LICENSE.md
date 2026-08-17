# Lizenzen — MediaGrab-Add-on

Dieses Add-on besteht aus eigenem Code und mitgelieferter fremder Software.

## Eigene Dateien

Der Anwendungscode, `config.yaml`, `Dockerfile`, `run.sh`, `translations/`, Symbole und die Markdown-Dateien in diesem Verzeichnis stammen aus diesem Repository und stehen unter der **MIT-Lizenz** (siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## Mitgelieferte Software

| Bestandteil | Lizenz | Quelltext |
|---|---|---|
| **ffmpeg** (Alpine-Paket) | **GPL-2.0-or-later AND LGPL-2.1-or-later** | <https://ffmpeg.org/download.html>, Paketbau: <https://gitlab.alpinelinux.org/alpine/aports> |
| **yt-dlp** | Unlicense (gemeinfrei) | <https://github.com/yt-dlp/yt-dlp> |
| **Flask** | BSD-3-Clause | <https://github.com/pallets/flask> |
| **mutagen** | GPL-2.0-or-later | <https://github.com/quodlibet/mutagen> |

Die verwendeten Fassungen stehen in [requirements.txt](requirements.txt); ffmpeg kommt aus den Alpine-Paketquellen der im [Dockerfile](Dockerfile) genannten Alpine-Fassung.

## Was das für das veröffentlichte Image bedeutet

`ghcr.io/luckytriple7/mediagrab` enthält mit ffmpeg und mutagen Software unter **GPL**. Beide werden unverändert als eigenständige Programme bzw. Bibliotheken mitgeliefert und nur über die Kommandozeile beziehungsweise als Python-Modul aufgerufen — der eigene Anwendungscode bleibt davon unberührt und MIT-lizenziert.

Für die GPL-Bestandteile gilt die GPL weiter. Die Bezugsquellen des Quelltextes sind oben genannt; die Alpine-Pakete lassen sich zur jeweiligen Fassung über `apk` und die aports-Quellen nachvollziehen.

> ffmpeg in den Alpine-Paketquellen ist ein GPL-Build. Wer das Add-on als Grundlage für eigene Weitergabe nutzt, sollte das im Blick behalten.
