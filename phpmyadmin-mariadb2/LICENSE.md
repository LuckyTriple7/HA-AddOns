# Lizenzen — phpMyAdmin-Add-on

Dieses Add-on besteht aus zwei Teilen mit unterschiedlichen Lizenzen.

## Eigene Dateien

`config.yaml`, `Dockerfile`, `rootfs/`, `translations/`, Symbole und die Markdown-Dateien in diesem Verzeichnis stammen aus diesem Repository und stehen unter der **MIT-Lizenz** (siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## phpMyAdmin

Das Add-on lädt beim Bau die offizielle Veröffentlichung von phpMyAdmin herunter und legt sie nach `/var/www/phpmyadmin`. Die verwendete Fassung steht im [Dockerfile](Dockerfile).

phpMyAdmin steht unter der **GPL-2.0**.

- Quelltext: <https://github.com/phpmyadmin/phpmyadmin>
- Veröffentlichungen: <https://files.phpmyadmin.net/phpMyAdmin/>

## Weitere Bestandteile

Basisimage `ghcr.io/hassio-addons/base` (MIT) sowie nginx, PHP und die im [Dockerfile](Dockerfile) genannten Alpine-Pakete, jeweils mit eigener Lizenz.

## Was das für das veröffentlichte Image bedeutet

`ghcr.io/luckytriple7/phpmyadmin-mariadb2` enthält phpMyAdmin in unveränderter Form; lediglich der Pfad zur Konfigurationsdatei wird angepasst und nicht benötigte Verzeichnisse (`setup`, `examples`, `test`, `po`) werden entfernt. Für diesen Bestandteil gilt die **GPL-2.0** weiter, der Quelltext ist über die Links oben zu beziehen. Die eigenen Dateien des Add-ons bleiben MIT-lizenziert.

## Kein Zusammenhang mit dem phpMyAdmin-Projekt

Dieses Add-on wird unabhängig gepflegt. Das phpMyAdmin-Projekt betreibt es nicht und unterstützt es nicht.

Fehlerberichte zu den Add-on-Dateien und Optionen gehören in [dieses Repository](https://github.com/LuckyTriple7/HA-AddOns/issues), Fehler in phpMyAdmin selbst zum [Projekt](https://github.com/phpmyadmin/phpmyadmin/issues).
