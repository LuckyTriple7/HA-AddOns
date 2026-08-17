# Lizenzen — Firefox-DE-Add-on

Dieses Add-on besteht aus mehreren Teilen mit unterschiedlichen Lizenzen.

## Eigene Dateien

`config.yaml`, `Dockerfile`, `rootfs/`, `translations/`, Symbole und die Markdown-Dateien in diesem Verzeichnis stammen aus diesem Repository und stehen unter der **MIT-Lizenz** (siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## Mitgelieferte Software

| Bestandteil | Lizenz | Quelltext |
|---|---|---|
| **Firefox ESR** (offizielles Mozilla-Build, deutsch) | **MPL-2.0** | <https://hg.mozilla.org/mozilla-central/>, Veröffentlichungen: <https://releases.mozilla.org/pub/firefox/releases/> |
| **jlesage/baseimage-gui** (VNC-Grundlage) | MIT | <https://github.com/jlesage/docker-baseimage-gui> |
| **noVNC** (im Basisimage enthalten) | **MPL-2.0** (Kernbibliothek) | <https://github.com/novnc/noVNC> |
| GTK3, ALSA, dbus, fontconfig, Schriften, Locales | Debian-Pakete mit jeweils eigener Lizenz | <https://snapshot.debian.org/> |

Die verwendete Firefox-Fassung steht als `ARG FIREFOX_VERSION` im [Dockerfile](Dockerfile), die Fassung des Basisimages in dessen `FROM`-Zeile.

## Was das für das veröffentlichte Image bedeutet

`ghcr.io/luckytriple7/firefox` enthält den **unveränderten offiziellen Firefox-Tarball** von `releases.mozilla.org`. Er wird nur entpackt und über einen Symlink erreichbar gemacht; weder das Programm noch seine Konfigurationsvorgaben werden verändert.

Die MPL-2.0 ist eine dateibezogene Copyleft-Lizenz: die MPL-lizenzierten Bestandteile — Firefox und die noVNC-Kernbibliothek — bleiben unter der MPL-2.0, auch wenn sie mit anderer Software in einem Image liegen. Die eigenen Dateien des Add-ons bleiben MIT-lizenziert.

Nach MPL-2.0 §3.2 muss bei der Weitergabe in ausführbarer Form auf die Herkunft des Quelltextes hingewiesen werden — das leisten die Verlinkungen oben.

## Marke

„Firefox" und „Mozilla" sind Marken der Mozilla Foundation. Die Markenrichtlinie erlaubt die Weitergabe **unveränderter** offizieller Builds unter dem Namen Firefox; genau das geschieht hier. Wer den Dockerfile ändert und Firefox dabei anfasst, muss die Richtlinie erneut prüfen und gegebenenfalls umbenennen.

Dieses Add-on wird unabhängig gepflegt. Mozilla betreibt es nicht und unterstützt es nicht.

Fehlerberichte zu den Add-on-Dateien und Optionen gehören in [dieses Repository](https://github.com/LuckyTriple7/HA-AddOns/issues), Fehler in Firefox selbst zu [Bugzilla](https://bugzilla.mozilla.org/).
