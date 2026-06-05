# HA SysWatch

Docker container resource monitor for Home Assistant.

Real-time CPU, RAM, Network I/O, Disk I/O and PID counts for all Docker containers — including stopped HA add-ons — in a sortable, PWA-ready web interface with automatic refresh.

## Features

### Dashboard & Charts
- **Sortable table**: CPU %, RAM %, NET I/O, DISK I/O, PIDs per container — sort persists across reloads
- **CPU sparkline**: 30-measurement history per container in the table
- **24h history charts**: click SYS CPU or SYS RAM card to open a canvas chart with the last 24 hours — stored in SQLite, survives restarts
- **CPU temperature chart**: click any temperature reading to open a 24h temperature history with threshold reference lines (60 / 75 / 90°C)
- **HA Status card**: Supervisor / Support / Health from Supervisor API — green / yellow / red

### System Info
- **SYS CPU / SYS RAM cards**: color-coded progress bars (green ≤70 %, yellow ≤80 %, orange ≤90 %, red >90%) — clickable for 24h chart
- **CPU temperature**: from `coretemp` / `k10temp` hwmon — Package + per-core temps displayed below the CPU chart
- **Footer versions**: HA Core, Supervisor and OS version always visible

### Container Management
- **Container actions**: Start, Stop, Restart, Kill (SIGKILL) — all with password confirmation
- **Log viewer**: last 200 lines with timestamps
- **Port overview**: all host-mapped ports, searchable and sortable — host ports are clickable links (`http://<host-ip>:<port>`)
- **Stopped containers**: shows stopped HA add-ons via Supervisor API

### Telegram Notifications
- Unexpected container stop → 💥 alert with **▶ Starten** inline button — start directly from Telegram
- Container restart detected → message updated to ✅, button removed
- CPU/RAM threshold alerts with **Top 5 consumers** (RAM: size + %)
- Configurable trigger and all-clear delays
- Startup notification with HA version, container count, host IP
- **📨 Test** button in header (desktop) to verify bot setup
- Chat ID auto-detected on first `/start` message — no manual lookup needed

### General
- **Auto-refresh**: browser calibrates automatically to backend collection cycle
- **Idle mode**: 2 workers / 60s interval when no browser connected — pause button in header
- **Persistent preferences**: sort column/direction, show-stopped state in localStorage
- **Password-protected** with brute-force lockout (5 attempts / 15 min)
- **DE / EN** language support (auto-detected from browser)
- **Light / Dark mode** — persisted in localStorage
- **PWA** — installable on desktop and mobile
- **Mobile-responsive** layout

## Port

`17790`

## Key Configuration

| Option | Default | Description |
|---|---|---|
| `collect_interval` | `3` | Sleep between queries in seconds. Total cycle ≈ query time + this value. |
| `collect_workers` | `16` | Parallel Docker stats calls (4–64). More = faster but higher CPU load. |
| `viewer_timeout` | `180` | Seconds without heartbeat before switching to idle mode (30–1800). |
| `show_stopped` | `true` | Show stopped containers by default. |
| `telegram_bot_token` | `""` | Telegram bot token. Leave empty to disable all Telegram features. |
| `telegram_chat_id` | `""` | Recipient chat ID. **Optional** — auto-detected when you message the bot. |
| `notify_cpu_threshold` | `0` | CPU alert threshold in %. 0 = disabled. |
| `notify_ram_threshold` | `0` | RAM alert threshold in %. 0 = disabled. |
| `notify_over_duration` | `0` | Seconds CPU/RAM must stay above threshold before alert fires. |
| `notify_clear_duration` | `120` | Seconds CPU/RAM must stay below threshold before all-clear is sent. |

**Performance note:** With 49 containers and 49 workers, query time is ~2 s (same floor as `docker stats --no-stream`). Total cycle: ~2 s + `collect_interval`.

## Telegram Setup

1. Create a bot via `@BotFather` → `/newbot` — copy the token
2. Set `telegram_bot_token` in the add-on configuration
3. Open your bot in Telegram and send `/start`
4. SysWatch auto-detects your chat ID and confirms with a message — done

`telegram_chat_id` is optional. SysWatch learns it automatically from the first message.
If set explicitly, only that chat ID is accepted (recommended for shared bots).
Token empty → all Telegram features disabled, no polling, no log output.

### Notification events

| Event | Message |
|---|---|
| Add-on started | 🟢 Startup info with HA/Supervisor/OS version, container count, host IP |
| Container stops unexpectedly | 💥 Alert + **▶ Starten** button |
| Container starts (not via SysWatch UI) | ▶️ Container gestartet |
| CPU above threshold | ⚠️ CPU alert + Top 5 CPU consumers |
| CPU back to normal | ✅ All-clear |
| RAM above threshold | ⚠️ RAM alert + Top 5 consumers (GiB + %) |
| RAM back to normal | ✅ All-clear |

## Protection Mode / Gesicherter Modus

After installation HA shows a warning: **"Protection mode disabled"** / **"Gesicherter Modus deaktiviert"**.
This is expected and must be confirmed manually.

SysWatch requires `docker_api: true` to mount the Docker socket (`/var/run/docker.sock`) —
without it no container stats can be read. HA automatically disables protection mode for this.

**In the HA add-on UI:** Info tab → set the "Protection Mode" toggle to **Off**.

---

## Installation

Add this repository to your Home Assistant Add-on Store:

```
https://github.com/LuckyTriple7/HA-AddOns
```
