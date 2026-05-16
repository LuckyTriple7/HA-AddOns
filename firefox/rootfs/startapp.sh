#!/bin/sh
set -e

PROFILE_DIR=/data/profile
mkdir -p "$PROFILE_DIR"
mkdir -p /share/firefox

OPTIONS=/data/options.json

read_opt() {
    [ -f "$OPTIONS" ] && jq -r ".${1} // empty" "$OPTIONS" 2>/dev/null || true
}

MEMORY_LIMIT_MB=$(read_opt memory_limit_mb)
FF_OPEN_URL=$(read_opt FF_OPEN_URL)
FF_KIOSK=$(read_opt FF_KIOSK)
FF_CUSTOM_ARGS=$(read_opt FF_CUSTOM_ARGS)

cat > "$PROFILE_DIR/user.js" << 'USERJS'
user_pref("intl.locale.requested", "de");
user_pref("browser.search.region", "DE");
user_pref("browser.search.isUS", false);
user_pref("layers.acceleration.disabled", true);
user_pref("gfx.webrender.all", false);
user_pref("gfx.webrender.software", true);
user_pref("media.ffmpeg.vaapi.enabled", false);
user_pref("browser.download.folderList", 2);
user_pref("browser.download.dir", "/share/firefox");
USERJS

if [ "${MEMORY_LIMIT_MB:-0}" -gt 0 ] 2>/dev/null; then
    DISK_CACHE_KB=$(( MEMORY_LIMIT_MB * 256 ))
    MEM_CACHE_KB=$(( MEMORY_LIMIT_MB * 128 ))
    cat >> "$PROFILE_DIR/user.js" << MEMJS
user_pref("browser.cache.disk.capacity", ${DISK_CACHE_KB});
user_pref("browser.cache.memory.capacity", ${MEM_CACHE_KB});
user_pref("dom.ipc.processCount", 1);
user_pref("browser.sessionhistory.max_total_viewers", 1);
user_pref("media.memory_cache_max_size", ${MEM_CACHE_KB});
MEMJS
fi

FF_ARGS="--profile $PROFILE_DIR --no-remote"

[ "${FF_KIOSK:-0}" = "1" ] && FF_ARGS="$FF_ARGS --kiosk"
[ -n "$FF_CUSTOM_ARGS" ] && FF_ARGS="$FF_ARGS $FF_CUSTOM_ARGS"
[ -n "$FF_OPEN_URL" ] && FF_ARGS="$FF_ARGS $FF_OPEN_URL"

export LIBGL_ALWAYS_SOFTWARE=1
export MOZ_DISABLE_RDD_SANDBOX=1

# shellcheck disable=SC2086
exec /usr/local/bin/firefox $FF_ARGS
