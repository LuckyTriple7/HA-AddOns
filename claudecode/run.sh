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

## Safety Rules — these override everything else in this file

You are working inside a **live** Home Assistant installation. A wrong write here
does not fail a test — it stops the user's house from booting.

### Never write to Home Assistant's internal state

These are managed exclusively by HA Core. They have no stable schema, HA rewrites
them whenever it likes, and hand-editing them corrupts the installation — a broken
`.storage/` registry means Home Assistant does not start at all.

| Path | Contains | Use instead |
|------|----------|-------------|
| `/homeassistant/.storage/` | Entity, device, area and auth registries, UI-managed automations, helpers, dashboards | `homeassistant` MCP server, or `hab` for areas/floors/labels/helpers/dashboards |
| `/homeassistant/.cloud/` | Nabu Casa Cloud state | nothing — managed by HA Cloud |
| `/homeassistant/deps/` | Python dependency cache | nothing — managed by HA Core |
| `/homeassistant/tts/` | TTS cache | nothing — managed by the TTS integration |
| `/homeassistant/home-assistant_v2.db` | History/recorder SQLite database | `homeassistant` MCP server for history and logbook |

Reading `home-assistant.log` is fine. Writing to it is not.

**Anything configured through the HA user interface lives in `.storage/`.** If a
request touches a UI-created automation, script, scene, helper, dashboard, area or
label, the answer is never "edit the JSON" — it is the MCP server or `hab`. If
neither offers it, say so and let the user do it in the UI. Do not improvise.

### Never expose secrets

Never display, echo, copy or paste the contents of `secrets.yaml` or any token,
password or API key. Reference secrets as `!secret <name>` in YAML.

### Ask before you change anything

- Show the exact change and wait for explicit approval before writing any file.
- Do only what was asked. No unrequested cleanup, refactoring or "improvements".
- One change at a time; let the user verify before the next.
- Validate after YAML changes: `ha core check`
- Say clearly whether a change needs a reload or a full restart.
- Suggest a backup before anything large.

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

For dashboard CRUD, area/floor/label management, helper creation, backup/restore, and other
admin operations, prefer the `hab` CLI (Home Assistant Builder) over raw REST/WebSocket calls.
It authenticates automatically via the Supervisor token inside this add-on.

```bash
hab guide                     # discover available commands
hab schema <command> --json   # inspect a command's contract before using it
hab <command> --plan --json   # preview a mutation before applying it
```

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

# Append a Home Context briefing — snapshot of this HA installation so sessions start
# knowing the setup instead of rediscovering it. Best-effort: HA core may still be
# starting on a fresh boot, so cap the wait and degrade gracefully.
HOME_CONTEXT=$(timeout 10 hab overview --text 2>/dev/null || true)
if [ -z "$HOME_CONTEXT" ]; then
    HOME_CONTEXT="(unavailable — Home Assistant Core may still be starting. Run 'hab overview' manually once it's up.)"
fi
cat >> "$PERSIST_DIR/CLAUDE.md" << EOF

## Home Context

Snapshot of this Home Assistant installation, captured when the add-on last started.
Counts may be stale if the setup changed since then — rerun \`hab overview\` for current data.

\`\`\`
$HOME_CONTEXT
\`\`\`
EOF

# The user's own standing instructions. CLAUDE.md above is rewritten on every start,
# so anything the user adds there is lost — CLAUDE.local.md is the file the add-on
# never writes to. Ship the example (kept current), import the real file only if it
# exists so Claude doesn't chase a dangling @-reference.
cat > "$PERSIST_DIR/CLAUDE.local.md.example" << 'LOCALMD'
# Your own instructions for Claude Code

Rename this file to `CLAUDE.local.md` (drop the `.example`) and Claude reads it at
the start of every session, alongside the add-on's own `CLAUDE.md`.

- The add-on **never** writes to `CLAUDE.local.md`. Add-on updates cannot overwrite it.
- Delete the file to stop loading it. There is no option to toggle.
- `CLAUDE.md` wins if the two conflict — the safety rules stay in force regardless
  of what you put here.
- Everything in this file is sent with **every** request, so keep it short and
  specific. Standing preferences are useful; a diary is not.
- Never put passwords, tokens or API keys here. Reference them with `!secret`.

Delete the examples below and write your own.

---

## About my setup

- Zigbee runs through Zigbee2MQTT, not ZHA. Don't suggest ZHA workflows.
- Three floors: Keller, Erdgeschoss, Obergeschoss. Areas are named after rooms.

## How I want you to work

- Answer in German.
- New configuration goes into `packages/`, one file per feature. Don't grow
  `configuration.yaml`.
- Always show me the diff before writing, even for one-line changes.

## Leave these alone

- Everything under `custom_components/` — managed through HACS.
LOCALMD

if [ -f "$PERSIST_DIR/CLAUDE.local.md" ]; then
    cat >> "$PERSIST_DIR/CLAUDE.md" << 'EOF'

## Your Own Instructions

The user's standing instructions follow. Treat them as the user speaking. Where they
conflict with this file, this file wins — the safety rules above are never relaxed.

@CLAUDE.local.md
EOF
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] CLAUDE.local.md found — user instructions loaded"
else
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] No CLAUDE.local.md — rename CLAUDE.local.md.example in $PERSIST_DIR to add your own instructions"
fi

# Persistence symlinks — keep Claude auth and config across container rebuilds
[ ! -L /root/.claude ] && { rm -rf /root/.claude; ln -s "$PERSIST_DIR" /root/.claude; }
[ ! -L /root/.config/claude-code ] && { rm -rf /root/.config/claude-code; ln -s "$PERSIST_DIR/config" /root/.config/claude-code; }
[ ! -L /root/.claude.json ] && { touch "$PERSIST_DIR/.claude.json"; rm -f /root/.claude.json; ln -s "$PERSIST_DIR/.claude.json" /root/.claude.json; }

# One-time scrub: older versions persisted the live Supervisor token into settings.json
# (a dead HASS_TOKEN field hass-mcp never reads — it only reads the HA_TOKEN env var).
# That file lives under /homeassistant and is included in every HA backup, so remove it.
SETTINGS_FILE_SCRUB="$PERSIST_DIR/settings.json"
if [ -f "$SETTINGS_FILE_SCRUB" ] && jq -e '.mcpServers.homeassistant.env.HASS_TOKEN' "$SETTINGS_FILE_SCRUB" > /dev/null 2>&1; then
    jq 'del(.mcpServers.homeassistant.env.HASS_TOKEN)' "$SETTINGS_FILE_SCRUB" > /tmp/settings.tmp && mv /tmp/settings.tmp "$SETTINGS_FILE_SCRUB"
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Scrubbed persisted Supervisor token from settings.json (was unused, hass-mcp reads HA_TOKEN from env)"
fi

# Persist ~/.local/bin and ~/.local/share/claude across container rebuilds.
# claude update stores symlinks in local-bin and actual version binaries in local-share-claude.
# Without persisting both, the symlink survives but points to a missing binary after rebuild.
mkdir -p "$PERSIST_DIR/local-bin"
[ ! -L /root/.local/bin ] && { rm -rf /root/.local/bin; ln -s "$PERSIST_DIR/local-bin" /root/.local/bin; }
# Remove stale claude from local-bin — AppArmor blocks exec from /root/.local/bin/
rm -f "$PERSIST_DIR/local-bin/claude" 2>/dev/null || true

mkdir -p "$PERSIST_DIR/local-share-claude" /root/.local/share
[ ! -L /root/.local/share/claude ] && { rm -rf /root/.local/share/claude; ln -s "$PERSIST_DIR/local-share-claude" /root/.local/share/claude; }

# Persist git configuration and credentials. /root is part of the container image,
# so ~/.gitconfig and ~/.git-credentials are gone after every rebuild — identity and
# push credentials had to be set up again each time (issue #251).
touch "$PERSIST_DIR/gitconfig"
if [ ! -L /root/.gitconfig ]; then
    [ -f /root/.gitconfig ] && cat /root/.gitconfig >> "$PERSIST_DIR/gitconfig"
    rm -f /root/.gitconfig
    ln -s "$PERSIST_DIR/gitconfig" /root/.gitconfig
fi
# Default the credential store into the persisted directory. Only when nothing is
# configured yet — an own credential.helper stays untouched.
if ! git config --global --get credential.helper > /dev/null 2>&1; then
    git config --global credential.helper "store --file=$PERSIST_DIR/.git-credentials"
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] git credential store → $PERSIST_DIR/.git-credentials"
fi
[ -f "$PERSIST_DIR/.git-credentials" ] && chmod 600 "$PERSIST_DIR/.git-credentials" 2>/dev/null

# Environment variables for MCP servers and CLI tools. Claude Code substitutes
# ${VAR} in .mcp.json from its own process environment, and `export` inside a
# terminal session can never reach that already-running process — so the values
# have to be in place before ttyd starts (issue #251).
ENV_FILE="$PERSIST_DIR/.env"
cat > "$PERSIST_DIR/.env.example" << 'ENVEXAMPLE'
# Environment variables for Claude Code
#
# What to do:
#   1. Rename this file to `.env` (drop the `.example`).
#   2. Go to the last line, DELETE THE LEADING `#` and put your token in.
#      A line still starting with `#` is a comment and is ignored.
#   3. Restart the add-on. The log then says:
#        Loaded 1 variable(s) from .env: GITHUB_PERSONAL_ACCESS_TOKEN
#
# Everything here is exported before Claude Code starts, so MCP servers that
# authenticate through ${VAR} substitution see their token — across restarts.
#
# The token alone does not create a server. GitHub's MCP server has to be
# registered once, and it is what reads GITHUB_PERSONAL_ACCESS_TOKEN:
#
#   claude mcp add-json github '{"type":"http","url":"https://api.githubcopilot.com/mcp/","headers":{"Authorization":"Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}"}}' -s user
#
# Leave ${GITHUB_PERSONAL_ACCESS_TOKEN} in that command exactly as written — it
# is a placeholder Claude Code fills in from the environment, so your token
# never ends up in a config file.
#
# Format: one KEY=VALUE per line. `#` starts a comment. Quotes around the value
# are optional and get stripped. A leading `export ` is allowed and ignored.
#
# This file lives under /homeassistant and is therefore part of every Home
# Assistant backup. Treat those backups accordingly.
#
# PATH, HOME, IFS, LD_PRELOAD, LD_LIBRARY_PATH, SUPERVISOR_TOKEN, HA_TOKEN and
# HA_URL are ignored — overwriting them breaks the add-on.

# GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...
ENVEXAMPLE

if [ -f "$ENV_FILE" ]; then
    chmod 600 "$ENV_FILE" 2>/dev/null
    ENV_NAMES=""
    ENV_COUNT=0
    # Parsed line by line instead of sourced: a sourced file would execute whatever
    # is in it, and a stray \r from a Windows editor would end up inside the value,
    # which breaks an Authorization header in a way that is very hard to see.
    while IFS= read -r RAW || [ -n "$RAW" ]; do
        LINE=${RAW%$'\r'}
        LINE=${LINE#$'\xef\xbb\xbf'}   # UTF-8 BOM, written by some Windows editors
        LINE=${LINE#"${LINE%%[![:space:]]*}"}
        case "$LINE" in
            ''|'#'*) continue ;;
            *=*) ;;
            *) echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] .env: line without '=' ignored"; continue ;;
        esac
        LINE=${LINE#export }
        KEY=${LINE%%=*}
        VAL=${LINE#*=}
        KEY=${KEY%"${KEY##*[![:space:]]}"}
        case "$KEY" in
            ''|[0-9]*|*[!A-Za-z0-9_]*)
                echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] .env: invalid variable name ignored"
                continue ;;
            PATH|HOME|IFS|LD_PRELOAD|LD_LIBRARY_PATH|SUPERVISOR_TOKEN|HA_TOKEN|HA_URL)
                echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] .env: $KEY is reserved by the add-on — ignored"
                continue ;;
        esac
        # Strip one layer of matching quotes, then trailing whitespace on bare values
        case "$VAL" in
            \"*\") VAL=${VAL#\"}; VAL=${VAL%\"} ;;
            \'*\') VAL=${VAL#\'}; VAL=${VAL%\'} ;;
            *) VAL=${VAL%"${VAL##*[![:space:]]}"} ;;
        esac
        export "$KEY=$VAL"
        ENV_NAMES="$ENV_NAMES $KEY"
        ENV_COUNT=$((ENV_COUNT + 1))
    done < "$ENV_FILE"
    if [ "$ENV_COUNT" -eq 0 ]; then
        # A .env in which every line is commented out is nearly always the example
        # file with the `#` still in front of the token — say so instead of just
        # reporting zero.
        echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] .env contains no active variable — every line is a comment or empty. Remove the leading '#' from the line holding your token."
    else
        # Names only — the values are secrets and add-on logs are shown in the HA UI
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Loaded $ENV_COUNT variable(s) from .env:$ENV_NAMES"
    fi
else
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] No .env — rename .env.example in $PERSIST_DIR to pass tokens to MCP servers"
fi

# Report active version (npm-global/bin is first in PATH, so updated version is used automatically)
if [ -f "$NPM_GLOBAL_DIR/bin/claude" ]; then
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Using npm-updated Claude Code: $(claude --version 2>/dev/null)"
fi

# Read all options from HA config
FONT_SIZE=$(jq -r '.terminal_font_size // 14' /data/options.json)
THEME=$(jq -r --arg d dark '.terminal_theme // $d' /data/options.json)
SESSION_PERSIST=$(jq -r 'if .session_persistence == false then "false" else "true" end' /data/options.json)
TMUX_SCROLL=$(jq -r --arg d browser '.tmux_scroll_mode // $d' /data/options.json)
MOBILE_SCROLL=$(jq -r 'if .mobile_scroll_ui == false then "false" else "true" end' /data/options.json)
CLAUDE_AUTOSTART=$(jq -r '.claude_autostart // false' /data/options.json)
ENABLE_MCP=$(jq -r 'if .enable_mcp == false then "false" else "true" end' /data/options.json)
ENABLE_PLAYWRIGHT=$(jq -r '.enable_playwright_mcp // false' /data/options.json)
PLAYWRIGHT_HOST=$(jq -r --arg d '' '.playwright_cdp_host // $d' /data/options.json)
AUTO_UPDATE=$(jq -r 'if .auto_update_claude == false then "false" else "true" end' /data/options.json)
NOTIFY_ON_UPDATE=$(jq -r 'if .notify_on_update == false then "false" else "true" end' /data/options.json)
MODEL=$(jq -r --arg d claude-sonnet-5 '.model // $d' /data/options.json)
EXPORT_MEMORY=$(jq -r '.export_memory // false' /data/options.json)
EXPORT_MEMORY_INTERVAL=$(jq -r '.export_memory_interval // 60' /data/options.json)
ENABLE_CAVEMAN=$(jq -r '.enable_caveman_skill // false' /data/options.json)
PROTECT_INTERNAL=$(jq -r 'if .protect_internal_config == false then "false" else "true" end' /data/options.json)
DIRECT_ACCESS=$(jq -r '.enable_direct_access // false' /data/options.json)
DIRECT_USER=$(jq -r --arg d admin '.direct_username // $d' /data/options.json)
DIRECT_PASS=$(jq -r --arg d '' '.direct_password // $d' /data/options.json)

# Log configuration
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Configuration:"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] model                  : $MODEL"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] enable_mcp             : $ENABLE_MCP"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] enable_playwright_mcp  : $ENABLE_PLAYWRIGHT"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] playwright_cdp_host    : ${PLAYWRIGHT_HOST:-auto-detect}"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] terminal_font_size     : $FONT_SIZE"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] terminal_theme         : $THEME"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] session_persistence    : $SESSION_PERSIST"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] tmux_scroll_mode       : $TMUX_SCROLL"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] mobile_scroll_ui       : $MOBILE_SCROLL"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] claude_autostart       : $CLAUDE_AUTOSTART"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] auto_update_claude     : $AUTO_UPDATE"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] notify_on_update       : $NOTIFY_ON_UPDATE"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] export_memory          : $EXPORT_MEMORY"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] export_memory_interval : ${EXPORT_MEMORY_INTERVAL} min"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] enable_caveman_skill   : $ENABLE_CAVEMAN"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] protect_internal_config: $PROTECT_INTERNAL"
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] enable_direct_access   : $DIRECT_ACCESS"

# Write protection for Home Assistant's internal state. The CLAUDE.md rules ask
# Claude not to touch these paths; these deny rules make Claude Code refuse the
# write itself, which also holds when the guidance gets ignored or compressed out
# of context. Rewritten on every start so toggling the option takes effect at once.
# Only the add-on's own entries are added or removed — user entries stay.
SETTINGS_FILE="$PERSIST_DIR/settings.json"
# Edit(...) is the rule form file permission checks actually match, and it covers
# every file-editing tool including Write. Write(...) rules are ignored for paths
# and only produce a startup warning.
# The two Read rules cover the files holding the user's tokens — they are already
# in Claude's environment where it needs them, there is no reason to read them off
# disk and every reason not to paste them into a session.
PROTECT_RULES='[
  "Edit(/homeassistant/.storage/**)",
  "Edit(/homeassistant/.cloud/**)",
  "Edit(/homeassistant/deps/**)",
  "Edit(/homeassistant/tts/**)",
  "Edit(/homeassistant/home-assistant_v2.db)",
  "Read(/homeassistant/.claudecode/.env)",
  "Read(/homeassistant/.claudecode/.git-credentials)"
]'
# Written by 1.3.12, which used the wrong rule form. Removed on every start
# regardless of the option, otherwise they keep warning on installs that had it.
OBSOLETE_RULES='[
  "Write(/homeassistant/.storage/**)",
  "Write(/homeassistant/.cloud/**)",
  "Write(/homeassistant/deps/**)",
  "Write(/homeassistant/tts/**)",
  "Write(/homeassistant/home-assistant_v2.db)"
]'
[ -f "$SETTINGS_FILE" ] || echo '{}' > "$SETTINGS_FILE"
if ! jq -e . "$SETTINGS_FILE" > /dev/null 2>&1; then
    # Hand-edited into invalid JSON — rewriting it would destroy whatever is in there
    echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] $SETTINGS_FILE is not valid JSON — leaving it alone, write protection not applied"
elif [ "$PROTECT_INTERNAL" = "true" ]; then
    jq --argjson rules "$PROTECT_RULES" --argjson obsolete "$OBSOLETE_RULES" \
       '(((.permissions.deny // []) - $obsolete)) as $kept
        | .permissions.deny = ($kept + ($rules - $kept))' \
       "$SETTINGS_FILE" > /tmp/settings.tmp && mv /tmp/settings.tmp "$SETTINGS_FILE"
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Write protection active — .storage/, .cloud/, deps/, tts/ and the recorder database are read-only for Claude, .env and .git-credentials unreadable"
else
    jq --argjson rules "$PROTECT_RULES" --argjson obsolete "$OBSOLETE_RULES" \
       '.permissions.deny = ((.permissions.deny // []) - $rules - $obsolete)
        | if (.permissions.deny | length) == 0 then del(.permissions.deny) else . end
        | if (.permissions | length) == 0 then del(.permissions) else . end' \
       "$SETTINGS_FILE" > /tmp/settings.tmp && mv /tmp/settings.tmp "$SETTINGS_FILE"
    echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] Write protection disabled — Claude may write to Home Assistant's internal directories, including .storage/, and may read .env and .git-credentials"
fi

# Caveman skills: opt-in, copied/removed on every start so toggling the option takes
# effect immediately. Only the bundled names are touched — own skills/agents stay put.
CAVEMAN_SRC=/opt/default-skills
if [ "$ENABLE_CAVEMAN" = "true" ]; then
    mkdir -p "$PERSIST_DIR/skills" "$PERSIST_DIR/agents"
    for SKILL_DIR in "$CAVEMAN_SRC"/skills/*/; do
        rm -rf "$PERSIST_DIR/skills/$(basename "$SKILL_DIR")"
        cp -a "${SKILL_DIR%/}" "$PERSIST_DIR/skills/"
    done
    cp -a "$CAVEMAN_SRC"/agents/. "$PERSIST_DIR/agents/"
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Caveman skills installed → /root/.claude/skills/ ($(find "$CAVEMAN_SRC/skills" -mindepth 1 -maxdepth 1 -type d | wc -l) skills, $(find "$CAVEMAN_SRC/agents" -name '*.md' | wc -l) agents)"
else
    for SKILL_DIR in "$CAVEMAN_SRC"/skills/*/; do
        rm -rf "$PERSIST_DIR/skills/$(basename "$SKILL_DIR")"
    done
    for AGENT_FILE in "$CAVEMAN_SRC"/agents/*.md; do
        rm -f "$PERSIST_DIR/agents/$(basename "$AGENT_FILE")"
    done
fi

# Auto-detect Playwright Browser hostname if not explicitly set
if [ -z "$PLAYWRIGHT_HOST" ] && [ "$ENABLE_PLAYWRIGHT" = "true" ]; then
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Auto-detecting Playwright Browser hostname..."
    PLAYWRIGHT_HOST=$(curl -s -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/addons \
        | jq -r --arg s1 playwright-browser --arg s2 _playwright-browser \
          '.data.addons[] | select(.slug | (endswith($s1) or endswith($s2))) | .hostname' | head -1)
    if [ -n "$PLAYWRIGHT_HOST" ] && [ "$PLAYWRIGHT_HOST" != "null" ]; then
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Found Playwright Browser: $PLAYWRIGHT_HOST"
    else
        echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] Playwright Browser add-on not found, using default hostname"
        PLAYWRIGHT_HOST="playwright-browser"
    fi
fi

# Auto-update Claude Code on startup if enabled
if [ "$AUTO_UPDATE" = "true" ]; then
    CURRENT_VER=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    LATEST_VER=$(npm show @anthropic-ai/claude-code dist-tags.stable 2>/dev/null)
    if [ -n "$LATEST_VER" ] && [ -n "$CURRENT_VER" ] && [ "$CURRENT_VER" != "$LATEST_VER" ]; then
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Updating Claude Code from $CURRENT_VER to $LATEST_VER..."
        # Install into the writable persisted prefix — avoids read-only Docker layer restriction
        # that blocks `claude update` (which tries to update the npm global in /usr/local)
        npm install -g "@anthropic-ai/claude-code@$LATEST_VER" \
            --prefix "$NPM_GLOBAL_DIR" --no-fund --no-audit 2>&1 || true
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Claude Code update complete: $(claude --version 2>/dev/null)"
    else
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Claude Code $CURRENT_VER is up to date"
    fi
fi

# Set Claude model
export ANTHROPIC_MODEL="$MODEL"

# Export memory + custom commands to addon config folder

do_memory_export() {
    MEMORY_SRC="$PERSIST_DIR/projects/-homeassistant/memory"
    if [ -d "$MEMORY_SRC" ]; then
        mkdir -p /config/memory
        cp -a "$MEMORY_SRC/." /config/memory/
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Memory exported: $(ls /config/memory/*.md 2>/dev/null | wc -l) file(s) → /config/memory/"
    else
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] No memory directory found at $MEMORY_SRC — skipping"
    fi
    COMMANDS_SRC="$PERSIST_DIR/commands"
    if [ -d "$COMMANDS_SRC" ] && [ -n "$(ls -A "$COMMANDS_SRC" 2>/dev/null)" ]; then
        mkdir -p /config/commands
        cp -a "$COMMANDS_SRC/." /config/commands/
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Commands exported: $(ls /config/commands/ 2>/dev/null | wc -l) file(s) → /config/commands/"
    else
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] No custom commands found — skipping"
    fi
}

if [ "$EXPORT_MEMORY" = "true" ]; then
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Exporting Claude memory and commands to /config/..."
    do_memory_export
    if [ "$EXPORT_MEMORY_INTERVAL" -gt 0 ] 2>/dev/null; then
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Memory backup started (interval: ${EXPORT_MEMORY_INTERVAL} min)"
        (while true; do
            sleep $(( EXPORT_MEMORY_INTERVAL * 60 ))
            echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Running scheduled memory backup..."
            do_memory_export
        done) &
    fi
else
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Memory export disabled"
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
      "Read(/media/**)"
    ]'
    jq --argjson tools "$ALLOWED_TOOLS" \
        '.permissions.allow = (($tools + ((.permissions.allow // []) | map(select(test("^(Glob|Grep)\\(") | not)))) | unique)' \
        "$SETTINGS_FILE" > /tmp/settings.tmp && mv /tmp/settings.tmp "$SETTINGS_FILE"
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] MCP configured with Home Assistant integration"
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Pre-authorized read-only MCP tools"
else
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] MCP disabled"
fi

if [ "$ENABLE_PLAYWRIGHT" = "true" ]; then
    # Auto-detect Playwright browser add-on and forward port 80 → 9222 via socat.
    # Playwright MCP requires the CDP endpoint on port 80; socat bridges to the add-on's port 9222.
    if getent hosts "$PLAYWRIGHT_HOST" > /dev/null 2>&1; then
        socat TCP-LISTEN:80,fork TCP:"$PLAYWRIGHT_HOST":9222 &
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] socat forwarding localhost:80 → $PLAYWRIGHT_HOST:9222"
    fi
    claude mcp add-json playwright \
        '{"command":"npx","args":["--no-install","@playwright/mcp","--cdp-endpoint","http://localhost:80"]}' \
        -s user
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Playwright MCP enabled (CDP: http://localhost:80 → ${PLAYWRIGHT_HOST}:9222)"
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Make sure the Playwright Browser add-on is installed and running"
else
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Playwright MCP disabled"
fi

# Write tmux runtime config based on scroll mode (sourced by /root/.tmux.conf)
if [ "$TMUX_SCROLL" = "tmux" ]; then
    # Mouse on: wheel scrolls tmux copy-mode through the full 20000-line history,
    # survives browser reloads; native touch scroll and copy/paste are unavailable
    printf 'set -g mouse on\nset -g status on\n' > /root/.tmux-runtime.conf
else
    # Status off: with a status line tmux scrolls inside a DECSTBM region,
    # which never reaches the xterm.js scrollback buffer (issue #162)
    printf 'set -g mouse off\nset -g status off\n' > /root/.tmux-runtime.conf
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
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Update checker started (interval: 1h)"
    (while true; do
        sleep 3600
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Checking for Claude Code updates..."
        IV=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        LV=$(npm show @anthropic-ai/claude-code dist-tags.stable 2>/dev/null)
        if [ -n "$LV" ] && [ -n "$IV" ] && [ "$IV" != "$LV" ]; then
            echo "$LV" > "$PERSIST_DIR/.update_notice"
            echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Update available: $LV (installed: $IV)"
            if [ "$NOTIFY_ON_UPDATE" = "true" ]; then
                printf '{"title":"Claude Code Update Available","message":"Version %s is available (installed: %s). Restart the add-on to update.","notification_id":"claude_code_update"}' "$LV" "$IV" \
                    | curl -sf -X POST \
                      -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
                      -H "Content-Type: application/json" \
                      -d @- http://supervisor/core/api/services/persistent_notification/create 2>/dev/null || true
            fi
        else
            rm -f "$PERSIST_DIR/.update_notice" 2>/dev/null
            echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Claude Code $IV is up to date"
            if [ "$NOTIFY_ON_UPDATE" = "true" ]; then
                printf '{"notification_id":"claude_code_update"}' \
                    | curl -sf -X POST \
                      -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
                      -H "Content-Type: application/json" \
                      -d @- http://supervisor/core/api/services/persistent_notification/dismiss 2>/dev/null || true
            fi
        fi
    done) &
else
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Auto-update disabled — update checker not started"
fi

# Serve the patched index.html (swipe scrolling + on-screen scroll buttons on
# touch devices, see mobile-scroll.js). Falls back to ttyd's built-in page if the
# build-time patch is missing.
TTYD_INDEX=""
if [ "$MOBILE_SCROLL" = "true" ] && [ -s /opt/ttyd-index.html ]; then
    TTYD_INDEX="--index /opt/ttyd-index.html"
else
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Mobile scroll UI off — serving ttyd's built-in page"
fi

cd /homeassistant

# Optional second ttyd on 7682 for direct browser access, bypassing the Supervisor
# ingress proxy and its Home Assistant login. Both instances run `tmux new-session -A`
# against the same session name, so the direct port shows the very same terminal.
#
# The ingress port is protected by HA's own auth; this one is not, and the terminal is
# a root shell on a container with full_access. So the port stays shut unless a password
# is set — a warning in the log would be too easy to miss for what it opens up.
if [ "$DIRECT_ACCESS" = "true" ]; then
    if [ -z "$DIRECT_PASS" ]; then
        echo "[ERROR] [$(date '+%Y-%m-%d %H:%M:%S')] enable_direct_access is on but direct_password is empty — port 7682 NOT started"
        echo "[ERROR] [$(date '+%Y-%m-%d %H:%M:%S')] Set a password in the add-on configuration, or turn enable_direct_access off"
    elif [ -z "$DIRECT_USER" ]; then
        echo "[ERROR] [$(date '+%Y-%m-%d %H:%M:%S')] enable_direct_access is on but direct_username is empty — port 7682 NOT started"
    else
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Direct access on port 7682, user '$DIRECT_USER' (HTTP Basic Auth — LAN only, never forward this port)"
        ttyd --port 7682 --writable --ping-interval 30 --max-clients 5 \
            --credential "$DIRECT_USER:$DIRECT_PASS" \
            -t fontSize="$FONT_SIZE" \
            -t fontFamily=Monaco,Consolas,monospace \
            -t scrollback=20000 \
            -t "theme=$COLORS" \
            $TTYD_INDEX \
            $SHELL_CMD &
    fi
fi

# Start web terminal
exec ttyd --port 7681 --writable --ping-interval 30 --max-clients 5 \
    -t fontSize="$FONT_SIZE" \
    -t fontFamily=Monaco,Consolas,monospace \
    -t scrollback=20000 \
    -t "theme=$COLORS" \
    $TTYD_INDEX \
    $SHELL_CMD
