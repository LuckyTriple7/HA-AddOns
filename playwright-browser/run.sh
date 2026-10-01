#!/bin/sh

CDP_PORT=$(jq -r '.cdp_port // 9222' /data/options.json)
IDLE_MINUTES=$(jq -r '.idle_timeout // 5' /data/options.json)
ENABLE_MCP=$(jq -r '.enable_mcp // false' /data/options.json)
MCP_TOKEN=$(jq -r '.mcp_token // ""' /data/options.json)

# Built-in Playwright MCP: fixed container port 17799 (host port is set in the
# add-on network settings), loopback CDP port 9224 that may start Chromium
MCP_PORT=0
LOCAL_CDP_PORT=0
if [ "$ENABLE_MCP" = "true" ]; then
    MCP_PORT=17799
    LOCAL_CDP_PORT=9224
fi

# Find Chromium binary
CHROMIUM_BIN=""
for candidate in chromium chromium-browser google-chrome-stable google-chrome; do
    if command -v "$candidate" >/dev/null 2>&1; then
        CHROMIUM_BIN="$candidate"
        break
    fi
done

if [ -z "$CHROMIUM_BIN" ]; then
    echo "[FATAL] [$(date '+%Y-%m-%d %H:%M:%S')] No Chromium binary found!"
    exit 1
fi

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] CDP proxy starting on port ${CDP_PORT} (lazy Chromium, idle timeout: ${IDLE_MINUTES} min)..."

exec env \
    CHROMIUM_BIN="$CHROMIUM_BIN" \
    EXTERNAL_PORT="$CDP_PORT" \
    INTERNAL_PORT=9223 \
    IDLE_TIMEOUT_MINUTES="$IDLE_MINUTES" \
    CHROMIUM_TMPDIR=/tmp/chromium-profile \
    LOCAL_CDP_PORT="$LOCAL_CDP_PORT" \
    MCP_PORT="$MCP_PORT" \
    MCP_TOKEN="$MCP_TOKEN" \
    MCP_IDLE_MINUTES="$IDLE_MINUTES" \
    NODE_BIN=/usr/local/bin/node \
    python3 /cdp_proxy.py
