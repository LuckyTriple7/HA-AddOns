#!/usr/bin/with-contenv bash
# Selkies-Video-Einstellungen über die s6-Container-Umgebung setzen.
# Diese Werte landen in /var/run/s6/container_environment/ und werden
# von allen s6-Services (inkl. Selkies) beim Start gelesen.

S6_ENV="/var/run/s6/container_environment"
mkdir -p "${S6_ENV}"

# Maximale Framerate auf 30fps begrenzen (Standard 60fps bei großen Auflösungen
# wie 3440x1270 führt zu Backpressure und eingefrorenem Browser-Fenster)
[ ! -f "${S6_ENV}/SELKIES_FRAMERATE" ] && printf '30' > "${S6_ENV}/SELKIES_FRAMERATE"

# AT-SPI Accessibility Bus deaktivieren (nicht verfügbar in HA-Containern)
printf '1' > "${S6_ENV}/NO_AT_BRIDGE"

echo "[ubuntu-webtop] Selkies: Framerate auf 30fps begrenzt (verhindert Backpressure-Freeze)"
