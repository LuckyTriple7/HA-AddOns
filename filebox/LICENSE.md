# Lizenzen — FileBox-Add-on

Dieses Add-on besteht aus zwei Teilen mit unterschiedlichen Lizenzen.

## Eigene Dateien

`config.yaml`, `Dockerfile`, `rootfs/`, `translations/`, Symbole und die Markdown-Dateien in diesem Verzeichnis stammen aus diesem Repository und stehen unter der **MIT-Lizenz** (siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## Mitgelieferte Software

| Bestandteil | Lizenz | Quelltext |
|---|---|---|
| **File Browser** | **Apache-2.0** | <https://github.com/filebrowser/filebrowser> |
| `cifs-utils`, `smbclient` (Samba) | **GPL-3.0** | <https://www.samba.org/samba/download/> |
| `ca-certificates`, `curl`, `jq`, `netcat-openbsd` | Debian-Pakete mit jeweils eigener Lizenz | <https://snapshot.debian.org/> |

Die verwendete File-Browser-Fassung steht als `ARG FILEBROWSER_VERSION` im [Dockerfile](Dockerfile).

## Was das für das veröffentlichte Image bedeutet

`ghcr.io/luckytriple7/filebox` enthält das **unveränderte offizielle Binary** von File Browser aus dessen GitHub-Veröffentlichungen. Es wird nur entpackt und nach `/usr/local/bin` gelegt; das Programm selbst wird nicht verändert. Die Konfiguration erfolgt zur Laufzeit über `run.sh` und die Add-on-Optionen.

Nach Apache-2.0 §4(a) muss bei der Weitergabe eine Kopie der Lizenz beiliegen — sie ist über den Link oben zu beziehen. Ein `NOTICE`-Verzeichnis führt File Browser nicht, §4(d) läuft daher leer. Die eigenen Dateien des Add-ons bleiben MIT-lizenziert.

Samba-Bestandteile stehen unter der **GPL-3.0**. Sie werden als unveränderte Debian-Pakete mitgeliefert und nur über die Kommandozeile aufgerufen; ihr Quelltext ist über die oben genannte Quelle zu beziehen.

## Kein Zusammenhang mit dem File-Browser-Projekt

Dieses Add-on wird unabhängig gepflegt. Das File-Browser-Projekt betreibt es nicht und unterstützt es nicht.

Fehlerberichte zu den Add-on-Dateien und Optionen gehören in [dieses Repository](https://github.com/LuckyTriple7/HA-AddOns/issues), Fehler in File Browser selbst zum [Projekt](https://github.com/filebrowser/filebrowser/issues).
