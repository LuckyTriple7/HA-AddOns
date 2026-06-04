# HA SysWatch

Docker container resource monitor for Home Assistant.

Real-time CPU, RAM, Network I/O, Disk I/O and PID counts for all Docker containers — including stopped HA add-ons — in a sortable, PWA-ready web interface with automatic refresh.

## Features

- **Sortable table**: CPU %, RAM %, NET I/O, DISK I/O, PIDs per container — sort state persists across reloads
- **CPU sparkline**: history of the last 30 measurements per container
- **System stats**: host CPU %, RAM % and CPU clock (cores × GHz) from `/proc`
- **Container actions**: Start, Stop, Restart, Kill (SIGKILL) — all with password confirmation
- **Log viewer**: last 200 lines with timestamps in a modal dialog
- **Port overview**: modal with all host-mapped ports, searchable and sortable
- **Stopped containers**: shows stopped HA add-ons via Supervisor API (HA removes their Docker containers)
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

**Performance note:** With 49 containers and 49 workers, query time is ~2 s
(same floor as `docker stats --no-stream` in the terminal — Docker daemon measurement interval).
Total cycle: ~2 s + `collect_interval`.

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
