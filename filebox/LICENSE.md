# Lizenzen — FileBox-Add-on

Dieses Add-on besteht aus zwei Teilen mit unterschiedlichen Lizenzen.

## Eigene Dateien

`config.yaml`, `Dockerfile`, `rootfs/`, `translations/`, Symbole und die Markdown-Dateien in diesem Verzeichnis stammen aus diesem Repository und stehen unter der **MIT-Lizenz** (siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## Mitgelieferte Software

| Bestandteil | Lizenz | Quelltext |
|---|---|---|
| **FileBrowser Quantum** | **Apache-2.0** | <https://github.com/gtsteffaniak/filebrowser> |
| `cifs-utils`, `smbclient` (Samba) | **GPL-3.0** | <https://www.samba.org/samba/download/> |
| `ca-certificates`, `curl`, `jq`, `netcat-openbsd` | Debian-Pakete mit jeweils eigener Lizenz | <https://snapshot.debian.org/> |

Die verwendete FileBrowser-Quantum-Fassung steht als `ARG FILEBROWSER_VERSION` im [Dockerfile](Dockerfile).

## Was das für das veröffentlichte Image bedeutet

`ghcr.io/luckytriple7/filebox` enthält das **unveränderte offizielle Binary** von FileBrowser Quantum aus dessen GitHub-Veröffentlichungen. Es wird nur heruntergeladen und nach `/usr/local/bin` gelegt; das Programm selbst wird nicht verändert. Die Konfiguration erfolgt zur Laufzeit über `run.sh` und die Add-on-Optionen.

Nach Apache-2.0 §4(a) muss bei der Weitergabe eine Kopie der Lizenz beiliegen — sie ist über den Link oben zu beziehen. Eine `NOTICE`-Datei führt FileBrowser Quantum nicht, §4(d) läuft daher leer. Die eigenen Dateien des Add-ons bleiben MIT-lizenziert.

Samba-Bestandteile stehen unter der **GPL-3.0**. Sie werden als unveränderte Debian-Pakete mitgeliefert und nur über die Kommandozeile aufgerufen; ihr Quelltext ist über die oben genannte Quelle zu beziehen.

## Kein Zusammenhang mit dem FileBrowser-Quantum-Projekt

Dieses Add-on wird unabhängig gepflegt. Das FileBrowser-Quantum-Projekt betreibt es nicht und unterstützt es nicht.

Fehlerberichte zu den Add-on-Dateien und Optionen gehören in [dieses Repository](https://github.com/LuckyTriple7/HA-AddOns/issues), Fehler in FileBrowser Quantum selbst zum [Projekt](https://github.com/gtsteffaniak/filebrowser/issues).
