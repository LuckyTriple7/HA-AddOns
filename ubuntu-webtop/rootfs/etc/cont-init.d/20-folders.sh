#!/usr/bin/with-contenv bash
# Stellt sicher, dass das persistente Benutzerverzeichnis existiert.
# /config ist der addon_config-Mount von Home Assistant und bleibt über Updates erhalten.

set -e

DATA_DIR="/config/data"

mkdir -p "${DATA_DIR}"
chown abc:abc "${DATA_DIR}"

echo "[ubuntu-webtop] Benutzerverzeichnis bereit: ${DATA_DIR}"
