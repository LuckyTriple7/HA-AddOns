# HA SysWatch

Docker container resource monitor for Home Assistant.

Displays CPU, RAM, Network I/O, Disk I/O and PID counts for all Docker
containers in a sortable, PWA-ready web interface with automatic refresh.

## Features

- Sortable table: CPU %, RAM %, NET I/O, DISK I/O, PIDs per container
- CPU sparkline history per container (last 30 measurements)
- System-level CPU % and RAM % from host `/proc` filesystem
- CPU clock speed (cores × GHz) from `/proc/cpuinfo`
- Log viewer (last 200 lines) and container actions (restart, kill) with password confirmation
- Auto-refresh: browser interval calibrates automatically to the backend collection cycle
- Performance mode: idle mode with minimal load when no browser is connected
- Password-protected with brute-force lockout
- DE / EN language support
- Light/Dark mode — persisted in localStorage
- PWA — installable on desktop and mobile
- Mobile-responsive dark/light theme

## Port

`17790`

## Key Configuration

| Option | Default | Description |
|---|---|---|
| `collect_interval` | `3` | Sleep between queries (seconds). Cycle = query time + this value. |
| `collect_workers` | `16` | Parallel Docker stats calls (4–64). More = faster but more CPU. |
| `viewer_timeout` | `180` | Seconds before switching to idle mode when no browser is connected. |

**Performance note:** With 49 containers and 49 workers, query time is ~2s
(same as `docker stats --no-stream` in the terminal — that's the Docker
daemon's measurement interval floor). Total cycle: ~2s + `collect_interval`.

## Installation

Add this repository to your Home Assistant Add-on Store:

```
https://github.com/LuckyTriple7/HA-AddOns
```
