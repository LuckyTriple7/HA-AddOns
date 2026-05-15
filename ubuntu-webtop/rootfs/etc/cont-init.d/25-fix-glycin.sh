#!/usr/bin/with-contenv bash
# glycin speichert Loader-Binaries im User-Cache (/config/.cache/glycin/).
# Auch wenn die System-Binaries entfernt wurden, nutzt glycin die gecachte Kopie
# und ruft bwrap auf – das in HA-Containern nicht funktioniert (kein bwrap --unshare-all).
# Lösung: Cache beim Start löschen, damit kein gecachter glycin-Loader verwendet wird.

if [ -d "/config/.cache/glycin" ]; then
    rm -rf "/config/.cache/glycin"
    echo "[ubuntu-webtop] glycin-Cache gelöscht (verhindert bwrap-Crash bei SVG-Icons)"
fi
