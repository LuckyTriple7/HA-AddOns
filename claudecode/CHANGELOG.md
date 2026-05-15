# Changelog

All notable changes to this project will be documented in this file.

## [2.3.10] - 2026-05-14

### Changed
- Rebuild to bundle latest Claude Code release.

## [2.3.9] - 2026-05-08

### Fixed
- Startup crash: "Permission denied" when executing `/root/.local/bin/claude`. AppArmor allows read/write on `/root/**` but not execute — any `claude` binary left there from a previous `claude update` would be found in PATH before `/usr/local/bin/claude` and fail. Startup now removes the stale binary from the persisted local-bin so bash always falls through to the AppArmor-allowed path.
- In-container updates via `claude-update` now actually work: added AppArmor `ixmr` permission for `/homeassistant/.claudecode/npm-global/**` so the npm-prefix-installed binary can be executed.

## [2.3.8] - 2026-05-08

### Fixed
- Add-on failed to start with "Permission denied" when creating symlink at `/usr/local/bin/claude`. That path is in the read-only Docker image layer and cannot be overwritten at runtime. Removed all `ln -sf /usr/local/bin/claude` calls; instead, the writable npm prefix (`/homeassistant/.claudecode/npm-global/bin`) is now prepended to PATH in both `run.sh` and `.bashrc`, so any installed update automatically takes priority without touching the image layer.

## [2.3.7] - 2026-05-08

### Fixed
- `claude-update` (and auto-update on startup) failed with "read-only filesystem" error. `claude update` detects it was npm-installed and tries to overwrite files in `/usr/local` — a read-only Docker image layer. Now uses `npm install --prefix` to install into the writable persisted directory (`/homeassistant/.claudecode/npm-global/`) and symlinks `/usr/local/bin/claude` to the result. Users can now run `claude-update` from the terminal to get the latest Claude Code without needing a new add-on image.

## [2.3.6] - 2026-05-05

### Changed
- Updated bundled Claude Code to latest release.
- Added `claude-opus-4-7` to the model selector (replaces `claude-opus-4-6`).

### Fixed
- OAuth/auth URL wrapping across multiple lines when connecting to Claude. tmux resets the PTY width via SIGWINCH when a client attaches, overriding the `stty cols 220` set at shell startup. A `claude()` bash wrapper now re-applies the 220-column PTY width immediately before every `claude` invocation, so auth URLs always render as a single unbroken line.

## [2.3.5] - 2026-05-05

### Changed
- Rebuild to bundle latest Claude Code.
- Removed install progress ticker — HA's own popup handles the in-progress state; log output is now clean.

## [2.3.4] - 2026-04-24

### Fixed
- Add-on install/update appeared hung in HA with no output during the Claude Code npm download step (can take 30-60 seconds). Added a background ticker that prints progress every 20 seconds so HA shows the build is still running.

## [2.3.3] - 2026-04-24

### Fixed
- "Claude symlink points to missing or invalid binary" warning on startup. `claude update` stores the actual version binaries in `~/.local/share/claude/versions/` — only `~/.local/bin/` (the symlink) was being persisted, so after a container rebuild the symlink survived but its target was gone. Now `~/.local/share/claude/` is also persisted to persistent storage.

## [2.3.2] - 2026-04-24

### Changed
- Rebuild to bundle latest Claude Code.

## [2.3.1] - 2026-04-24

### Fixed
- After `claude update`, running `claude` still used the old version due to bash's command hash table caching the npm-installed path. On startup, `run.sh` now symlinks `/usr/local/bin/claude` → the persisted binary when one exists, so there is only ever one `claude` in PATH regardless of hash state.

## [2.3.0] - 2026-04-24

### Changed
- Disabled tmux mouse mode (`set -g mouse off`). tmux was intercepting all mouse and touch events, breaking native browser copy/paste and iPad touch scrolling. With mouse off, the browser's xterm.js terminal handles scrolling (20,000 line buffer via ttyd) and copy/paste natively. Session persistence is unchanged — tmux still maintains the session across reconnects.

## [2.2.9] - 2026-04-16

### Fixed
- After `claude update`, running `claude` still used the old version. Login shells (bash --login / tmux) source `/etc/profile` on Alpine which resets PATH to system defaults, dropping `/root/.local/bin`. Added `export PATH="/root/.local/bin:$PATH"` to `.bashrc` so it's always restored for interactive sessions.

## [2.2.8] - 2026-04-16

### Changed
- Rebuild to bundle latest Claude Code at image build time.

## [2.2.7] - 2026-04-15

### Fixed
- AppArmor profile only grants execute permission (`ixr`) to `/bin/**`, `/usr/bin/**`, `/usr/local/**` etc. — not to `/run.sh` at the filesystem root. Moved startup script to `/usr/local/bin/start-addon.sh` which is in the AppArmor-allowed execution path.

## [2.2.6] - 2026-04-15

### Fixed
- `run.sh` was committed without the execute bit (mode 100644), causing tini to fail with "Permission denied". Fixed by setting mode 100755 in git and changing CMD to `["/bin/bash", "/run.sh"]` so bash executes the script directly regardless of the file's permission bits.

## [2.2.5] - 2026-04-15

### Fixed
- Moved all startup logic from an inline Dockerfile CMD bash -c string into a proper `run.sh` shell script. The inline approach caused `\"` quoting to be passed as literal backslashes to jq (breaking the `&&` chain before ttyd started) and shell keywords in the CLAUDE.md content to be misinterpreted as Dockerfile instructions by the linter. The shell script has none of these quoting constraints.

## [2.2.4] - 2026-04-14

### Fixed
- Startup crash: jq filters with string literals (`.terminal_theme // "dark"`, `.model // "claude-sonnet-4-6"`, etc.) were receiving literal backslash-quotes (`\"`) instead of double quotes when run inside the Docker CMD JSON array. Replaced all string literals in jq filters with `--arg` variables which require no quoting.

## [2.2.3] - 2026-04-14

### Fixed
- Add-on failed to start: `claude update` in the startup CMD (no TTY) was hanging waiting for interactive input. Now pipes `yes` and uses `timeout 120` to prevent blocking startup.
- Restored `DISABLE_AUTOUPDATER=1` to prevent Claude Code's background auto-updater from interfering with startup commands (`claude mcp remove/add-json`).

## [2.2.2] - 2026-04-12

### Fixed
- `claude-update` and auto-update now use `claude update` instead of `npm install -g`. Newer Claude Code versions block npm from overwriting the binary and require using the built-in update command.
- Removed `DISABLE_AUTOUPDATER=1` env var so the built-in updater can function correctly.
- `~/.local/bin/` is now symlinked to persistent storage so updates installed via `claude update` survive add-on restarts and rebuilds.

## [2.2.1] - 2026-04-14

### Fixed
- `claude-update` and auto-update failing because Claude Code's postinstall script calls `sudo`, which HA's security profile blocks. Added a passthrough `sudo` wrapper (container already runs as root so elevation is unnecessary).

## [2.2.0] - 2026-04-14

### Added
- `claude-update` terminal alias: run it from the terminal to update Claude Code instantly without restarting the add-on
- Update notification now mentions `claude-update` as an alternative to restarting

### Changed
- No add-on version bump needed to update Claude Code: just restart the add-on (triggers auto-update) or run `claude-update` in the terminal

## [2.1.99] - 2026-04-12

### Fixed
- Auto-update now shows progress in logs: compares installed vs latest version, logs the update action, and confirms completion — no longer silently hangs with no output

## [2.1.98] - 2026-04-12

### Fixed
- OAuth URL still wrapping: previous fix set the shell COLUMNS variable but Claude Code is Node.js and reads PTY width via ioctl. Now also runs `stty cols 220` at shell start and before each `claude`/`cc` invocation to set the actual PTY width that Node.js reads.

## [2.1.97] - 2026-04-12

### Fixed
- Docker cache no longer causes stale Claude Code version in builds: `BUILD_VERSION` (auto-passed by HA) is declared before the npm install, forcing a fresh `@latest` fetch on every version bump

## [2.1.96] - 2026-04-12

### Changed
- Rebuild to pick up latest @anthropic-ai/claude-code release

## [2.1.95] - 2026-04-11

### Fixed
- "sessionstart: startup hook error": HASS_TOKEN is now injected into the hass-mcp server env config at startup, not only when using the `c` alias

## [2.1.94] - 2026-04-11

### Fixed
- Build-time Claude Code install now uses `@latest` so the image always ships with the newest version, not whatever npm cached at build time

## [2.1.93] - 2026-04-11

### Changed
- Version bump above upstream 2.1.92 so HA detects this fork as an upgrade

## [1.2.71] - 2026-04-11

### Fixed
- "ttyd: missing start command" on startup: the `&` operator for the background update checker was splitting the entire preceding `&&` chain into a background subshell, so `$SHELL_CMD` was never set in the foreground process. Fixed by using `;` to terminate the main chain before launching the background loop.

## [1.2.70] - 2026-04-11

### Changed
- Version bump to verify update flow

## [1.2.69] - 2026-04-11

### Added
- HA persistent notification when Claude Code update is available: appears in the HA UI bell/notification area and is automatically dismissed once up-to-date

## [1.2.68] - 2026-04-11

### Added
- Update available notification: background process checks npm hourly and writes a notice file; terminal displays a yellow banner on open when a newer Claude Code version is available

## [1.2.67] - 2026-04-07

### Changed
- Version bump for update flow testing

## [1.2.66] - 2026-04-07

### Fixed
- Claude Code updates now install to the correct location: replaced `npm update -g` with `npm install -g @anthropic-ai/claude-code@latest` to match build-time install behavior
- Set `DISABLE_AUTOUPDATER=1` to prevent Claude Code's built-in self-updater from installing to `~/.local/bin/` (a different path that doesn't persist across container restarts)

## [1.2.65] - 2026-04-07

### Fixed
- OAuth URL displayed as malformed/multi-line in terminal by setting COLUMNS=220 in bash environment, preventing Claude Code from wrapping the auth URL

## [1.2.64] - 2026-04-07

### Added
- Model selection config option: choose between claude-opus-4-6, claude-sonnet-4-6 (default), and claude-haiku-4-5-20251001
- Selected model is applied via ANTHROPIC_MODEL env var at startup
- Auto-update Claude Code (existing feature) keeps new models accessible without add-on updates

## [1.2.63] - 2026-02-23

### Fixed
- Build failure due to `/usr/local/bin/mcp` conflict between hass-mcp (pip) and @playwright/mcp (npm)
- Switched from `npm install -g @playwright/mcp` to npx cache approach (pre-cache during build, `npx --no-install` at runtime)

### Changed
- Playwright Browser add-on: added aarch64 (ARM64) architecture support

## [1.2.62] - 2026-01-26

### Fixed
- MCP token now auto-updates when starting Claude via `c` or `cc` aliases
- Fixes "HTTP error: 500" when SUPERVISOR_TOKEN changes after addon restart

## [1.2.61] - 2026-01-16

### Added
- Full hardware access (`full_access: true`) for Docker socket mounting

## [1.2.60] - 2026-01-16

### Added
- Docker CLI (`docker` command) to use the Docker API

## [1.2.59] - 2026-01-16

### Added
- Docker API access (`docker_api: true`)

## [1.2.58] - 2026-01-16

### Added
- UART/serial port access (`uart: true`)

## [1.2.57] - 2026-01-16

### Added
- `socat` for bidirectional data transfer between channels

## [1.2.56] - 2026-01-16

### Added
- `pyserial` Python library for serial port communication

## [1.2.55] - 2026-01-16

### Fixed
- Removed `unrar` package (not available in Alpine 3.21)
- Use `7z x file.rar` instead for RAR extraction

## [1.2.54] - 2026-01-16

### Added
- Archive tools: `p7zip` for 7-Zip and RAR archives (use `7z` command)
- Modbus tools: `mbpoll` command line Modbus master, `pymodbus` Python library
- Useful for industrial automation and device communication tasks

## [1.2.53] - 2026-01-15

### Added
- Auto-detect Playwright Browser hostname using Supervisor API
- No need to manually configure `playwright_cdp_host` anymore
- Finds any add-on with slug ending in `playwright-browser`

## [1.2.52] - 2026-01-15

### Fixed
- Changed Playwright CDP endpoint from `ws://` to `http://` protocol
- Playwright auto-discovers the WebSocket path via `/json/version`
- Fixes 404 Not Found error when connecting to Chrome CDP

## [1.2.51] - 2026-01-15

### Added
- Configurable `playwright_cdp_host` option for custom Playwright Browser hostname
- Useful when default hostname doesn't resolve (e.g., use `1016f397-playwright-browser`)

## [1.2.50] - 2026-01-15

### Fixed
- Playwright MCP CDP endpoint hostname corrected to `playwright-browser` (was `local-playwright-browser`)
- Fixes "ENOTFOUND local-playwright-browser" connection error

## [1.2.49] - 2026-01-15

### Added
- GitHub CLI (`gh`) for GitHub operations (PRs, issues, repos, etc.)

## [1.2.48] - 2026-01-15

### Changed
- Playwright MCP now connects to external "Playwright Browser" add-on via CDP
- Removed Chromium from this add-on (keeps image small ~100MB vs ~2GB)
- Alpine + Chromium sandbox issues resolved by using separate Ubuntu-based add-on

### Note
- Requires "Playwright Browser" add-on to be installed and running for browser automation

## [1.2.47] - 2026-01-15

### Fixed
- Created `/usr/local/bin/chromium-wrapper` script that always passes `--no-sandbox`
- Playwright MCP config now points to wrapper script
- Should resolve EACCES and sandbox errors when running as root

## [1.2.46] - 2026-01-15

### Fixed
- Playwright MCP now uses config file with system Chromium
- Added `--no-sandbox` and `--disable-dev-shm-usage` flags for container compatibility
- Uses `/usr/bin/chromium-browser` instead of downloaded Chromium

## [1.2.45] - 2026-01-15

### Fixed
- MCP servers now configured at user scope (`-s user`) instead of project scope
- MCPs are now globally available regardless of working directory

## [1.2.44] - 2026-01-14

### Added
- Playwright MCP server for browser automation (opt-in via `enable_playwright_mcp`)
- Headless Chromium browser pre-installed
- Allows Claude to navigate web pages, fill forms, click elements, and take screenshots

## [1.2.43] - 2026-01-14

### Changed
- Upgraded `hassio_role` from `homeassistant` to `manager`
- Enables access to other add-ons' logs via `ha addons logs <slug>`

## [1.2.42] - 2026-01-14

### Added
- `hassio_role: homeassistant` permission for reading core logs
- Fixes 403 error when using `ha core logs`

## [1.2.41] - 2026-01-14

### Added
- Installed Home Assistant CLI (`ha` command) in the container
- `ha core logs`, `ha core restart`, etc. now available

## [1.2.40] - 2026-01-14

### Fixed
- Updated log commands in CLAUDE.md (`ha` CLI not available in add-on containers)
- Now uses `/homeassistant/home-assistant.log` and Supervisor API

## [1.2.39] - 2026-01-14

### Added
- CLAUDE.md now includes Home Assistant logging instructions
  - Log levels explanation (debug, info, warning, error)
  - Commands to read and filter logs
  - How to enable debug logging for integrations

## [1.2.38] - 2026-01-14

### Added
- Pre-authorized read-only hass-mcp tools (no confirmation needed):
  - `get_version`, `get_entity`, `list_entities`, `search_entities_tool`
  - `domain_summary_tool`, `list_automations`, `get_history`, `get_error_log`
- Pre-authorized file read operations:
  - `Read`, `Glob`, `Grep` for `/homeassistant/**`, `/config/**`, `/share/**`, `/media/**`
- Write operations still require confirmation: `entity_action`, `call_service_tool`, `restart_ha`

## [1.2.37] - 2026-01-14

### Added
- Auto-generated `~/.claude/CLAUDE.md` with path mapping instructions
- Claude Code now knows `/config` → `/homeassistant` translation

## [1.2.36] - 2026-01-14

### Fixed
- Reverted `/config` symlink that caused 502 startup errors

## [1.2.35] - 2026-01-14

### Added
- Symlink `/config` → `/homeassistant` for HA path compatibility (reverted in 1.2.36)

## [1.2.34] - 2026-01-14

### Added
- Auto-update Claude Code option (`auto_update_claude`) - checks for updates on startup
- Keeps Claude Code current without requiring add-on version bumps

## [1.2.33] - 2026-01-14

### Added
- Brazilian Portuguese translation (pt-BR)
- Spanish translation (es)

## [1.2.32] - 2026-01-14

### Fixed
- Added .profile to source .bashrc (tmux login shells need this for aliases)

## [1.2.31] - 2026-01-14

### Fixed
- Version bump to force rebuild (1.2.30 may have been cached before alias fix)

## [1.2.30] - 2026-01-14

### Changed
- Reorganized documentation: DOCS.md renamed to README.md
- Simplified root README.md
- Added Quick Start and Requirements sections

### Fixed
- Added .bashrc with aliases (`c`, `cc`, `ha-config`, `ha-logs`) - they were documented but not working

### Removed
- Deleted unused run.sh (Dockerfile CMD has everything inline)

## [1.2.29] - 2026-01-14

### Fixed
- hass-mcp expects `HA_URL` not `HA_HOST`

## [1.2.28] - 2026-01-14

### Changed
- Export HA_TOKEN/HA_HOST as environment variables instead of baking into MCP config
- hass-mcp now reads token from inherited environment (cleaner approach)

## [1.2.27] - 2026-01-14

### Fixed
- hass-mcp expects `HA_TOKEN` and `HA_HOST` (not `HASS_TOKEN`/`HASS_HOST`)

## [1.2.26] - 2026-01-14

### Fixed
- MCP now configured using `claude mcp add-json` command (proper Claude Code API)
- Previous settings.json approach was not recognized by Claude Code

### Documentation
- Added detailed copy/paste instructions for tmux mode (Ctrl+Shift to select, Shift+Insert to paste)

## [1.2.25] - 2026-01-14

### Fixed
- MCP configuration was never created - hass-mcp integration now works
- Added MCP setup to Dockerfile CMD (run.sh was not being executed)
- `/mcp` command now shows Home Assistant MCP server when `enable_mcp: true`

## [1.2.24] - 2026-01-14

### Added
- Improved tmux mouse wheel scrolling support
- Disable alternate screen buffer for better scrollback (`smcup@:rmcup@`)
- Mouse wheel bindings for scrolling in tmux copy mode

### Note
- Mouse scrolling now enabled; use middle-click or Shift+Insert to paste

## [1.2.23] - 2026-01-14

### Added
- Configure tmux with 20,000 line scrollback buffer (`history-limit`)
- Use `Ctrl+b [` then arrow keys/Page Up/Down to scroll in tmux

## [1.2.22] - 2026-01-14

### Added
- Increased terminal scrollback buffer to 20,000 lines (xterm.js)

## [1.2.21] - 2026-01-14

### Reverted
- Removed tmux mouse mode (breaks paste functionality)

### Documentation
- Added section explaining scrolling and session persistence trade-offs

## [1.2.20] - 2026-01-14

### Fixed
- Persist /root/.claude.json file (stores theme/onboarding state)
- Enable tmux mouse support for scroll wheel (`set -g mouse on`)

## [1.2.19] - 2026-01-14

### Fixed
- Store Claude Code data in /homeassistant/.claudecode (truly persistent)
- Survives addon uninstall/reinstall/rebuild
- Symlink ~/.claude and ~/.config/claude-code to HA config directory

## [1.2.18] - 2026-01-14

### Changed
- Sidebar icon changed to mdi:brain

### Fixed
- Persist both ~/.claude and ~/.config/claude-code directories
- Ensures all Claude Code auth and config survives restarts

## [1.2.17] - 2026-01-14

### Fixed
- Persist Claude Code authentication across restarts
- Symlink /root/.claude to /data/claude for persistent storage
- Restored config reading for font size, theme, and session persistence

## [1.2.16] - 2026-01-14

### Fixed
- Restored config reading for font size, theme, and session persistence
- ttyd now applies terminal_font_size, terminal_theme, and session_persistence settings

## [1.2.15] - 2026-01-14

### Fixed
- Refined AppArmor profile with focused permissions for HA config access
- Added dac_read_search capability for directory listing
- Full access to /homeassistant, /share, /media, /config directories
- Read-only access to system files, SSL, backups

## [1.2.14] - 2026-01-14

### Fixed
- Add /etc/** read permissions to AppArmor profile
- Fixes "bash: /etc/profile: Permission denied" error

## [1.2.13] - 2026-01-14

### Fixed
- Add PTY permissions to AppArmor profile (sys_tty_config, /dev/ptmx, /dev/pts/*)
- Fixes "pty_spawn: Permission denied" error when spawning terminal

## [1.2.12] - 2026-01-14

### Fixed
- Use static ttyd binary from GitHub releases instead of Alpine package
- Fixes "failed to load evlib_uv" libwebsockets error

## [1.2.11] - 2026-01-14

### Changed
- Simplified startup: run ttyd directly in CMD without script file
- Minimal configuration for debugging startup issues

## [1.2.10] - 2026-01-14

### Fixed
- Create run.sh inline via heredoc to avoid file permission issues

## [1.2.9] - 2026-01-14

### Fixed
- Add .gitattributes to enforce LF line endings for shell scripts
- Force Docker cache bust for permission fixes

## [1.2.8] - 2026-01-14

### Changed
- Use Docker's tini init system (`init: true`) instead of s6-overlay
- Simplified entrypoint configuration

## [1.2.7] - 2026-01-14

### Fixed
- Use bash instead of bashio in s6-overlay run script
- Add chmod +x /init to fix permission issues

## [1.2.6] - 2026-01-14

### Changed
- Properly configure s6-overlay v3 service structure
- Add service files in /etc/s6-overlay/s6-rc.d/ttyd

## [1.2.5] - 2026-01-14

### Changed
- Attempted switch to pure Alpine base image (reverted due to HA format requirements)

## [1.2.4] - 2026-01-14

### Fixed
- Set `init: false` for s6-overlay v3 compatibility

## [1.2.3] - 2026-01-14

### Fixed
- Force bash entrypoint to bypass s6-overlay init issues

## [1.2.2] - 2026-01-14

### Fixed
- Remove s6-overlay dependency, use plain bash with jq
- Fixes "/init: Permission denied" startup error

## [1.2.1] - 2026-01-14

### Fixed
- Corrected hass-mcp package name (was homeassistant-mcp)
- Upgraded to Python 3.13 base image for hass-mcp compatibility

## [1.2.0] - 2026-01-14

### Changed
- **Security improvement**: Removed API key from add-on config - Claude Code now handles authentication itself
- Simplified Dockerfile - use Alpine's ttyd package instead of architecture-specific downloads
- Removed model selection from config (Claude Code manages this)

### Fixed
- Docker build failure due to BUILD_ARCH variable not being passed correctly

## [1.1.0] - 2026-01-14

### Added
- Model selection option (sonnet, opus, haiku)
- Terminal font size configuration (10-24px)
- Terminal theme selection (dark/light)
- Session persistence using tmux
- s6-overlay service definitions for better process management
- Shell aliases and shortcuts (c, cc, ha-config, ha-logs)
- Welcome banner with configuration info
- Health check for container monitoring

### Changed
- Upgraded to Python 3.12 Alpine base image
- Improved architecture-specific ttyd binary installation
- Enhanced run.sh with better configuration handling
- Better error messages and validation

### Fixed
- Proper ingress base path handling

## [1.0.0] - 2026-01-14

### Added
- Initial release
- Web terminal interface using ttyd
- Claude Code integration via npm package
- Home Assistant MCP server integration for entity/service access
- Read-write access to Home Assistant configuration
- Multi-architecture support (amd64, aarch64, armv7, armhf, i386)
- Ingress support for seamless sidebar integration

