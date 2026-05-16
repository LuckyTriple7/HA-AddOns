#!/bin/sh
set -e

PROFILE_DIR=/data/profile
mkdir -p "$PROFILE_DIR"
mkdir -p /share/firefox

MEMORY_LIMIT_MB=0
if [ -f /data/options.json ]; then
    MEMORY_LIMIT_MB=$(jq -r '.memory_limit_mb // 0' /data/options.json 2>/dev/null || echo "0")
fi

cat > "$PROFILE_DIR/user.js" << 'USERJS'
user_pref("intl.locale.requested", "de");
user_pref("browser.search.region", "DE");
user_pref("browser.search.isUS", false);
user_pref("layers.acceleration.disabled", true);
user_pref("gfx.webrender.all", false);
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

exec /usr/local/bin/firefox --profile "$PROFILE_DIR" --no-remote
