#!/bin/bash
set -e

export HA_TOKEN="$SUPERVISOR_TOKEN"
export HA_URL="http://supervisor/core"
PERSIST_DIR=/homeassistant/.claudecode
NPM_GLOBAL_DIR="$PERSIST_DIR/npm-global"
# Prepend writable npm prefix to PATH so any installed update takes priority over the image binary
export PATH="$NPM_GLOBAL_DIR/bin:$PATH"

mkdir -p "$PERSIST_DIR/config" "$NPM_GLOBAL_DIR" /root/.config

# Write CLAUDE.md for Claude's context
cat > "$PERSIST_DIR/CLAUDE.md" << 'CLAUDEMD'
# Claude Code - Home Assistant Add-on

## Path Mapping

In this add-on container, paths are mapped differently than HA Core:
- `/homeassistant` = HA config directory (equivalent to `/config` in HA Core)
- `/config` does NOT exist - always use `/homeassistant`

When users mention `/config/...`, translate to `/homeassistant/...`

## Available Paths

| Path | Description | Access |
|------|-------------|--------|
| `/homeassistant` | HA configuration | read-write |
| `/share` | Shared folder | read-write |
| `/media` | Media files | read-write |
| `/ssl` | SSL certificates | read-only |
| `/backup` | Backups | read-only |

## Home Assistant Integration

Use the `homeassistant` MCP server to query entities and call services.

## Reading Home Assistant Logs

**Log levels (from most to least verbose):**
- `debug` - Only shown if explicitly enabled in configuration.yaml
- `info` - General information, shown by default
- `warning` - Warnings, always shown
- `error` - Errors, always shown

**Commands to read logs:**
```bash
# View recent logs (ha CLI)
ha core logs 2>&1 | tail -100

# Filter by keyword
ha core logs 2>&1 | grep -i keyword

# Filter errors only
ha core logs 2>&1 | grep -iE "(error|exception)"

# Alternative: read log file directly
tail -100 /homeassistant/home-assistant.log
```

**To enable debug logging for an integration**, add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.YOUR_INTEGRATION: debug
```

**Key insight:** `_LOGGER.debug()` calls are invisible unless the logger level is set to debug. Use `_LOGGER.info()` or `_LOGGER.warning()` for logs that should always appear.
CLAUDEMD

# Persistence symlinks — keep Claude auth and config across container rebuilds
[ ! -L /root/.claude ] && { rm -rf /root/.claude; ln -s "$PERSIST_DIR" /root/.claude; }
[ ! -L /root/.config/claude-code ] && { rm -rf /root/.config/claude-code; ln -s "$PERSIST_DIR/config" /root/.config/claude-code; }
[ ! -L /root/.claude.json ] && { touch "$PERSIST_DIR/.claude.json"; rm -f /root/.claude.json; ln -s "$PERSIST_DIR/.claude.json" /root/.claude.json; }

# Persist ~/.local/bin and ~/.local/share/claude across container rebuilds.
# claude update stores symlinks in local-bin and actual version binaries in local-share-claude.
# Without persisting both, the symlink survives but points to a missing binary after rebuild.
mkdir -p "$PERSIST_DIR/local-bin"
[ ! -L /root/.local/bin ] && { rm -rf /root/.local/bin; ln -s "$PERSIST_DIR/local-bin" /root/.local/bin; }
# Remove stale claude from local-bin — AppArmor blocks exec from /root/.local/bin/
rm -f "$PERSIST_DIR/local-bin/claude" 2>/dev/null || true

mkdir -p "$PERSIST_DIR/local-share-claude" /root/.local/share
[ ! -L /root/.local/share/claude ] && { rm -rf /root/.local/share/claude; ln -s "$PERSIST_DIR/local-share-claude" /root/.local/share/claude; }

# Report active version (npm-global/bin is first in PATH, so updated version is used automatically)
if [ -f "$NPM_GLOBAL_DIR/bin/claude" ]; then
    echo "[INFO] Using npm-updated Claude Code: $(claude --version 2>/dev/null)"
fi

# Read options from HA config
FONT_SIZE=$(jq -r '.terminal_font_size // 14' /data/options.json)
THEME=$(jq -r --arg d dark '.terminal_theme // $d' /data/options.json)
SESSION_PERSIST=$(jq -r '.session_persistence // true' /data/options.json)
CLAUDE_AUTOSTART=$(jq -r '.claude_autostart // false' /data/options.json)
ENABLE_MCP=$(jq -r '.enable_mcp // true' /data/options.json)
ENABLE_PLAYWRIGHT=$(jq -r '.enable_playwright_mcp // false' /data/options.json)
PLAYWRIGHT_HOST=$(jq -r --arg d '' '.playwright_cdp_host // $d' /data/options.json)

# Auto-detect Playwright Browser hostname if not explicitly set
if [ -z "$PLAYWRIGHT_HOST" ] && [ "$ENABLE_PLAYWRIGHT" = "true" ]; then
    echo '[INFO] Auto-detecting Playwright Browser hostname...'
    PLAYWRIGHT_HOST=$(curl -s -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/addons \
        | jq -r --arg s1 playwright-browser --arg s2 _playwright-browser \
          '.data.addons[] | select(.slug | (endswith($s1) or endswith($s2))) | .hostname' | head -1)
    if [ -n "$PLAYWRIGHT_HOST" ] && [ "$PLAYWRIGHT_HOST" != "null" ]; then
        echo "[INFO] Found Playwright Browser: $PLAYWRIGHT_HOST"
    else
        echo '[WARN] Playwright Browser add-on not found, using default hostname'
        PLAYWRIGHT_HOST="playwright-browser"
    fi
fi

# Auto-update Claude Code on startup if enabled
AUTO_UPDATE=$(jq -r '.auto_update_claude // true' /data/options.json)
if [ "$AUTO_UPDATE" = "true" ]; then
    CURRENT_VER=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    LATEST_VER=$(npm show @anthropic-ai/claude-code version 2>/dev/null)
    if [ -n "$LATEST_VER" ] && [ -n "$CURRENT_VER" ] && [ "$CURRENT_VER" != "$LATEST_VER" ]; then
        echo "[INFO] Updating Claude Code from $CURRENT_VER to $LATEST_VER..."
        # Install into the writable persisted prefix — avoids read-only Docker layer restriction
        # that blocks `claude update` (which tries to update the npm global in /usr/local)
        npm install -g "@anthropic-ai/claude-code@$LATEST_VER" \
            --prefix "$NPM_GLOBAL_DIR" --no-fund --no-audit 2>&1 || true
        echo "[INFO] Claude Code update complete: $(claude --version 2>/dev/null)"
    else
        echo "[INFO] Claude Code $CURRENT_VER is up to date"
    fi
fi

# Set Claude model
MODEL=$(jq -r --arg d claude-sonnet-4-6 '.model // $d' /data/options.json)
export ANTHROPIC_MODEL="$MODEL"
echo "[INFO] Using Claude model: $MODEL"

# Export memory + custom commands to addon config folder
EXPORT_MEMORY=$(jq -r '.export_memory // false' /data/options.json)
EXPORT_MEMORY_INTERVAL=$(jq -r '.export_memory_interval // 60' /data/options.json)

do_memory_export() {
    MEMORY_SRC="$PERSIST_DIR/projects/-homeassistant/memory"
    if [ -d "$MEMORY_SRC" ]; then
        mkdir -p /config/memory
        cp -a "$MEMORY_SRC/." /config/memory/
        echo "[INFO] Memory exported: $(ls /config/memory/*.md 2>/dev/null | wc -l) file(s) → /config/memory/"
    else
        echo "[INFO] No memory directory found at $MEMORY_SRC — skipping"
    fi
    COMMANDS_SRC="$PERSIST_DIR/commands"
    if [ -d "$COMMANDS_SRC" ] && [ -n "$(ls -A "$COMMANDS_SRC" 2>/dev/null)" ]; then
        mkdir -p /config/commands
        cp -a "$COMMANDS_SRC/." /config/commands/
        echo "[INFO] Commands exported: $(ls /config/commands/ 2>/dev/null | wc -l) file(s) → /config/commands/"
    else
        echo "[INFO] No custom commands found — skipping"
    fi
}

if [ "$EXPORT_MEMORY" = "true" ]; then
    echo "[INFO] Exporting Claude memory and commands to /config/..."
    do_memory_export
    if [ "$EXPORT_MEMORY_INTERVAL" -gt 0 ] 2>/dev/null; then
        (while true; do
            sleep $(( EXPORT_MEMORY_INTERVAL * 60 ))
            echo "[INFO] Scheduled memory export..."
            do_memory_export
        done) &
        echo "[INFO] Memory export scheduled every ${EXPORT_MEMORY_INTERVAL} minute(s)"
    fi
else
    echo "[INFO] Memory export disabled"
fi

# Configure MCP servers
claude mcp remove homeassistant -s user 2>/dev/null || true
claude mcp remove playwright -s user 2>/dev/null || true

if [ "$ENABLE_MCP" = "true" ]; then
    claude mcp add-json homeassistant '{"command":"hass-mcp"}' -s user
    SETTINGS_FILE=/root/.claude/settings.json
    ALLOWED_TOOLS='[
      "mcp__homeassistant__get_version",
      "mcp__homeassistant__get_entity",
      "mcp__homeassistant__list_entities",
      "mcp__homeassistant__search_entities_tool",
      "mcp__homeassistant__domain_summary_tool",
      "mcp__homeassistant__list_automations",
      "mcp__homeassistant__get_history",
      "mcp__homeassistant__get_error_log",
      "Read(/homeassistant/**)",
      "Read(/config/**)",
      "Read(/share/**)",
      "Read(/media/**)",
      "Glob(/homeassistant/**)",
      "Glob(/config/**)",
      "Grep(/homeassistant/**)",
      "Grep(/config/**)"
    ]'
    jq --argjson tools "$ALLOWED_TOOLS" \
        '.permissions.allow = ($tools + (.permissions.allow // []) | unique)' \
        "$SETTINGS_FILE" > /tmp/settings.tmp && mv /tmp/settings.tmp "$SETTINGS_FILE"
    jq --arg token "$SUPERVISOR_TOKEN" \
        '.mcpServers.homeassistant.env.HASS_TOKEN = $token' \
        "$SETTINGS_FILE" > /tmp/settings.tmp && mv /tmp/settings.tmp "$SETTINGS_FILE"
    echo '[INFO] MCP configured with Home Assistant integration'
    echo '[INFO] Pre-authorized read-only MCP tools'
else
    echo '[INFO] MCP disabled'
fi

if [ "$ENABLE_PLAYWRIGHT" = "true" ]; then
    # Auto-detect Playwright browser add-on and forward port 80 → 9222 via socat.
    # Playwright MCP requires the CDP endpoint on port 80; socat bridges to the add-on's port 9222.
    if getent hosts "$PLAYWRIGHT_HOST" > /dev/null 2>&1; then
        socat TCP-LISTEN:80,fork TCP:"$PLAYWRIGHT_HOST":9222 &
        echo "[INFO] socat forwarding localhost:80 → $PLAYWRIGHT_HOST:9222"
    fi
    claude mcp add-json playwright \
        '{"command":"npx","args":["--no-install","@playwright/mcp","--cdp-endpoint","http://localhost:80"]}' \
        -s user
    echo "[INFO] Playwright MCP enabled (CDP: http://localhost:80 → ${PLAYWRIGHT_HOST}:9222)"
    echo '[INFO] Make sure the Playwright Browser add-on is installed and running'
else
    echo '[INFO] Playwright MCP disabled'
fi

# Set terminal colors based on theme
if [ "$THEME" = "dark" ]; then
    COLORS='background=#1e1e2e,foreground=#cdd6f4,cursor=#f5e0dc'
else
    COLORS='background=#eff1f5,foreground=#4c4f69,cursor=#dc8a78'
fi

# Set shell command based on session persistence and autostart settings
if [ "$CLAUDE_AUTOSTART" = "true" ]; then
    cat > /tmp/claude-start.sh << 'EOF'
#!/bin/bash
claude
exec bash --login
EOF
    chmod +x /tmp/claude-start.sh
    if [ "$SESSION_PERSIST" = "true" ]; then
        SHELL_CMD='tmux new-session -A -s claude /tmp/claude-start.sh'
    else
        SHELL_CMD='/tmp/claude-start.sh'
    fi
else
    if [ "$SESSION_PERSIST" = "true" ]; then
        SHELL_CMD='tmux new-session -A -s claude'
    else
        SHELL_CMD='bash --login'
    fi
fi

# Background update checker — runs hourly, posts HA notification when update is available
if [ "$AUTO_UPDATE" = "true" ]; then
    (while true; do
        IV=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        LV=$(npm show @anthropic-ai/claude-code version 2>/dev/null)
        if [ -n "$LV" ] && [ -n "$IV" ] && [ "$IV" != "$LV" ]; then
            echo "$LV" > "$PERSIST_DIR/.update_notice"
            echo "[INFO] Claude Code update available: $LV (installed: $IV)"
            printf '{"title":"Claude Code Update Available","message":"Version %s is available (installed: %s). Restart the add-on to update.","notification_id":"claude_code_update"}' "$LV" "$IV" \
                | curl -sf -X POST \
                  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
                  -H "Content-Type: application/json" \
                  -d @- http://supervisor/core/api/services/persistent_notification/create 2>/dev/null || true
        else
            rm -f "$PERSIST_DIR/.update_notice" 2>/dev/null
            printf '{"notification_id":"claude_code_update"}' \
                | curl -sf -X POST \
                  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
                  -H "Content-Type: application/json" \
                  -d @- http://supervisor/core/api/services/persistent_notification/dismiss 2>/dev/null || true
        fi
        sleep 3600
    done) &
else
    echo "[INFO] Auto-update disabled — update checker not started"
fi

# Start web terminal
cd /homeassistant
exec ttyd --port 7681 --writable --ping-interval 30 --max-clients 5 \
    -t fontSize="$FONT_SIZE" \
    -t fontFamily=Monaco,Consolas,monospace \
    -t scrollback=20000 \
    -t "theme=$COLORS" \
    $SHELL_CMD
