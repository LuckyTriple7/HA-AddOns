#!/bin/sh

CDP_PORT=$(jq -r '.cdp_port // 9222' /data/options.json)
IDLE_MINUTES=$(jq -r '.idle_timeout // 5' /data/options.json)

# Find Chromium binary
CHROMIUM_BIN=""
for candidate in chromium chromium-browser google-chrome-stable google-chrome; do
    if command -v "$candidate" >/dev/null 2>&1; then
        CHROMIUM_BIN="$candidate"
        break
    fi
done

if [ -z "$CHROMIUM_BIN" ]; then
    echo "[FATAL] No Chromium binary found!"
    exit 1
fi

echo "[INFO] CDP proxy starting on port ${CDP_PORT} (lazy Chromium, idle timeout: ${IDLE_MINUTES} min)..."

exec env \
    CHROMIUM_BIN="$CHROMIUM_BIN" \
    EXTERNAL_PORT="$CDP_PORT" \
    INTERNAL_PORT=9223 \
    IDLE_TIMEOUT_MINUTES="$IDLE_MINUTES" \
    CHROMIUM_TMPDIR=/tmp/chromium-profile \
    python3 /cdp_proxy.py
