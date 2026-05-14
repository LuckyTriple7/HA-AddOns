#!/usr/bin/with-contenv bash
# LinuxServer nutzt /config als Home-Verzeichnis für den abc-User.
# /config ist der addon_config-Mount von Home Assistant (persistent über Updates).
# Sicherstellen, dass /config für abc beschreibbar ist.

chmod 755 /config 2>/dev/null || true
echo "[ubuntu-webtop] /config bereit (addon_config-Mount)"
