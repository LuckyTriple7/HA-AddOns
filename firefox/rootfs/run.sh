#!/bin/bash
set -e

# HA Add-on Optionen lesen
MEMORY_LIMIT_MB=0
if [ -f /data/options.json ]; then
    MEMORY_LIMIT_MB=$(jq -r '.memory_limit_mb // 0' /data/options.json 2>/dev/null || echo "0")
fi

# Persistentes Firefox-Profil
PROFILE_DIR=/data/profile
mkdir -p "$PROFILE_DIR"

# Downloads nach /share/firefox (HA shared directory, für alle Add-ons zugänglich)
mkdir -p /share/firefox

# user.js: Sprache, Software-Rendering, Download-Ordner
{
    echo 'user_pref("intl.locale.requested", "de");'
    echo 'user_pref("browser.search.region", "DE");'
    echo 'user_pref("browser.search.isUS", false);'
    echo 'user_pref("layers.acceleration.disabled", true);'
    echo 'user_pref("gfx.webrender.all", false);'
    echo 'user_pref("browser.download.folderList", 2);'
    echo 'user_pref("browser.download.dir", "/share/firefox");'
} > "$PROFILE_DIR/user.js"

if [ "${MEMORY_LIMIT_MB:-0}" -gt 0 ] 2>/dev/null; then
    DISK_CACHE_KB=$(( MEMORY_LIMIT_MB * 256 ))
    MEM_CACHE_KB=$(( MEMORY_LIMIT_MB * 128 ))
    cat >> "$PROFILE_DIR/user.js" << EOF
user_pref("browser.cache.disk.capacity", ${DISK_CACHE_KB});
user_pref("browser.cache.memory.capacity", ${MEM_CACHE_KB});
user_pref("dom.ipc.processCount", 1);
user_pref("browser.sessionhistory.max_total_viewers", 1);
user_pref("media.memory_cache_max_size", ${MEM_CACHE_KB});
EOF
fi

cleanup() {
    kill "$XVNC_PID" "$NOVNC_PID" 2>/dev/null || true
    [ -n "${DBUS_SESSION_BUS_PID:-}" ] && kill "$DBUS_SESSION_BUS_PID" 2>/dev/null || true
}
trap cleanup EXIT

# TigerVNC starten — virtuelles Display + VNC-Server in einem
# Unterstützt resize=remote: passt die Auflösung dynamisch an den Browser an
Xvnc :1 -geometry 1280x800 -depth 24 -rfbport 5900 -SecurityTypes None &
XVNC_PID=$!
sleep 1

# DBus starten
eval "$(dbus-launch --sh-syntax 2>/dev/null)" || true

# Openbox Window Manager starten — nötig damit Firefox-Menüs/Popups korrekt funktionieren
DISPLAY=:1 openbox &

# noVNC / WebSocket-Proxy starten
websockify --web /usr/share/novnc/ 5800 localhost:5900 &
NOVNC_PID=$!
sleep 1

# Firefox starten
export DISPLAY=:1
export HOME=/data
firefox-esr --profile "$PROFILE_DIR" --no-remote
