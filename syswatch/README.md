# HA SysWatch

Docker container resource monitor for Home Assistant.

Real-time CPU, RAM, Network I/O, Disk I/O and PID counts for all Docker containers — including stopped HA add-ons — in a sortable, PWA-ready web interface with automatic refresh.

## Features

- **Sortable table**: CPU %, RAM %, NET I/O, DISK I/O, PIDs per container — sort state persists across reloads
- **CPU sparkline**: history of the last 30 measurements per container
- **System stats**: host CPU %, RAM %, CPU clock (cores × GHz) from `/proc`
- **HA Status card**: Supervisor / Support / Health status from Supervisor API — green / yellow / red indicator
- **Footer versions**: HA Core, Supervisor and OS version always visible at the bottom
- **Container actions**: Start, Stop, Restart, Kill (SIGKILL) — all with password confirmation
- **Log viewer**: last 200 lines with timestamps in a modal dialog
- **Port overview**: modal with all host-mapped ports, searchable and sortable — host ports are clickable links (`http://<host-ip>:<port>`)
- **Stopped containers**: shows stopped HA add-ons via Supervisor API (HA removes their Docker containers)
- **Telegram notifications**: alerts for unexpected container stops/starts and CPU/RAM threshold breaches with configurable trigger and all-clear delays
- **Auto-refresh**: browser interval calibrates automatically to the backend collection cycle
- **Performance mode**: idle mode (2 workers, 60s interval) when no browser is connected; pause button in header
- **Persistent preferences**: sort column/direction and show-stopped state saved in localStorage
- **Password-protected** with brute-force lockout (5 attempts / 15 min block)
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
| `telegram_bot_token` | `""` | Telegram bot token for notifications. Leave empty to disable. |
| `telegram_chat_id` | `""` | Telegram chat/user/group ID for notifications. |
| `notify_cpu_threshold` | `0` | CPU alert threshold in %. 0 = disabled. |
| `notify_ram_threshold` | `0` | RAM alert threshold in %. 0 = disabled. |
| `notify_over_duration` | `0` | Seconds CPU/RAM must stay above threshold before alert fires. |
| `notify_clear_duration` | `120` | Seconds CPU/RAM must stay below threshold before all-clear is sent. |

**Performance note:** With 49 containers and 49 workers, query time is ~2 s
(same floor as `docker stats --no-stream` in the terminal — Docker daemon measurement interval).
Total cycle: ~2 s + `collect_interval`.

## Telegram Notifications

To enable notifications, set `telegram_bot_token` and `telegram_chat_id` in the add-on configuration.

- **Create a bot**: message `@BotFather` on Telegram → `/newbot`
- **Find your chat ID**: message `@userinfobot` on Telegram

Notification events:

| Event | Message |
|---|---|
| Container stops unexpectedly (crash, HA action) | 💥 Container unerwartet gestoppt |
| Container starts (not triggered via SysWatch UI) | ▶️ Container gestartet |
| CPU exceeds threshold (after `notify_over_duration`) | ⚠️ Hohe CPU-Last |
| CPU back below threshold (after `notify_clear_duration`) | ✅ CPU-Last normal |
| RAM exceeds threshold | ⚠️ Hohe RAM-Auslastung |
| RAM back below threshold | ✅ RAM-Auslastung normal |

Stopping/killing containers via the SysWatch UI does **not** trigger a notification (marked as intentional).
CPU/RAM alerts have a 10-minute cooldown between repeated alerts for the same metric.

## Protection Mode / Gesicherter Modus

After installation HA shows a warning: **"Protection mode disabled"** / **"Gesicherter Modus deaktiviert"**.
This is expected and must be confirmed manually.

SysWatch requires `docker_api: true` to mount the Docker socket (`/var/run/docker.sock`) —
without it no container stats can be read. HA automatically disables protection mode for this,
since the Docker socket grants broad host-level access by design.

**In the HA add-on UI:** Info tab → set the "Protection Mode" toggle to **Off**.

---

## Installation

Add this repository to your Home Assistant Add-on Store:

```
https://github.com/LuckyTriple7/HA-AddOns
```
