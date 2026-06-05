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
- **Telegram notifications**: alerts for unexpected stops/starts and CPU/RAM threshold breaches — with inline keyboard to restart a stopped container directly from Telegram
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
| `telegram_bot_token` | `""` | Telegram bot token. Leave empty to disable all Telegram features. |
| `telegram_chat_id` | `""` | Recipient chat ID. **Optional** — auto-detected when you message the bot. |
| `notify_cpu_threshold` | `0` | CPU alert threshold in %. 0 = disabled. |
| `notify_ram_threshold` | `0` | RAM alert threshold in %. 0 = disabled. |
| `notify_over_duration` | `0` | Seconds CPU/RAM must stay above threshold before alert fires. |
| `notify_clear_duration` | `120` | Seconds CPU/RAM must stay below threshold before all-clear is sent. |

**Performance note:** With 49 containers and 49 workers, query time is ~2 s
(same floor as `docker stats --no-stream` in the terminal — Docker daemon measurement interval).
Total cycle: ~2 s + `collect_interval`.

## Telegram Notifications

### Setup

1. Create a bot via `@BotFather` → `/newbot` — copy the token
2. Set `telegram_bot_token` in the add-on configuration
3. Open your bot in Telegram and send `/start`
4. SysWatch auto-detects your chat ID and confirms with a message — done

`telegram_chat_id` is optional. If left empty, SysWatch learns it from the first message received.
If set explicitly, only that chat ID is accepted (recommended for shared bots).

### Notification events

| Event | Message |
|---|---|
| Add-on started | 🟢 HA SysWatch gestartet (with HA version, container count, host IP) |
| Container stops unexpectedly (crash, HA action) | 💥 Container unerwartet gestoppt + **▶ Starten** button |
| Container starts (not triggered via SysWatch UI) | ▶️ Container gestartet |
| CPU exceeds threshold (after `notify_over_duration` s) | ⚠️ Hohe CPU-Last + Top 5 CPU consumers |
| CPU back below threshold (after `notify_clear_duration` s) | ✅ CPU-Last normal |
| RAM exceeds threshold | ⚠️ Hohe RAM-Auslastung + Top 5 RAM consumers (size + %) |
| RAM back below threshold | ✅ RAM-Auslastung normal |

### Inline keyboard — start from Telegram

When a container stops unexpectedly, the notification includes a **▶ Starten** button.
Pressing it starts the container directly from Telegram (via Docker or Supervisor API fallback).
The message is then updated to ✅ once the container is running again.

### Top 5 consumers in alerts

CPU alerts list the top 5 containers by CPU %. RAM alerts list the top 5 by RAM with size and percentage:
```
Top 5 RAM:
  1. addon_nextcloud: 1.8 GiB (18.4%)
  2. homeassistant: 1.2 GiB (12.1%)
  ...
```

### Logging

Every outgoing Telegram message is logged in the HA add-on log:
```
[Telegram] → 🟢 HA SysWatch gestartet …
[Telegram] Gesendet.
```

### Test button

A **📨 Test** button next to the logo (desktop only) sends a test notification immediately,
showing the current top 5 CPU and RAM consumers — useful for verifying bot setup.

### Rules

- Stop/Kill/Start triggered via the SysWatch UI do **not** trigger notifications (marked as intentional)
- CPU/RAM alerts have a 10-minute cooldown between repeated alerts for the same metric
- Token empty → all Telegram features disabled, no polling, no log output

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
