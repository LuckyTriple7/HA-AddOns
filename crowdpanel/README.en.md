# CrowdPanel

**CrowdSec control panel for Home Assistant** · [Deutsch](README.md)

View, create and lift decisions — without `cscli` on the command line.
CrowdPanel talks to the Local API of an existing CrowdSec installation and turns
it into a web interface.

## Features

- **Overview** — active decisions, alerts from the last 24 hours, top countries and scenarios
- **Decisions** — filter by scope, type and origin; lift them one by one or all at once
- **New ban** — single IP, CIDR range, whole country or whole network (AS), with a free duration and reason
- **Alerts** — groupable by address or scenario with hit counts, with events and the triggering log line; ban straight from the row
- **Check IP** — active decisions, alert history and allowlist hits for an address
- **Exemptions** — allowlists from the CrowdSec database and whitelist parsers in full, with the difference explained
- **Attack map** — one dot per source address from the GeoIP coordinates in the alerts, zoomable, your own location as the reference point, click leads to the alert list
- **Alert archive** — its own SQLite under `/data`, so history, map and alert list reach further back than CrowdSec's own retention
- **Metrics** — CrowdSec's own counters for data sources, parsers, scenarios, whitelists, LAPI, bouncers and AppSec
- **Two-factor sign-in** — TOTP for the direct port, QR code generated locally, backup codes
- **Home Assistant sensors** — active decisions, the locally detected ones, and detections of the last 24 hours
- Dark / light · DE / EN · HA Ingress · PWA

## Quick start

1. Create a machine account in CrowdSec:
   ```sh
   CS=$(docker ps --format '{{.Names}}' | grep -i crowdsec)
   CFG=/config/.storage/crowdsec/config/config.yaml
   PW=$(openssl rand -hex 22)
   docker exec $CS cscli -c $CFG machines add crowdpanel --password "$PW" -f -
   echo "$PW"
   ```
   Both `-c $CFG` and `-f -` are mandatory, `--force` would be wrong → [DOCS.en.md](DOCS.en.md#step-1--create-a-machine-account-in-crowdsec)
2. Put `lapi_url`, `machine_id` and `machine_password` into the add-on options
3. Change `password` and start the add-on

## Ports

| Port | Purpose |
|------|---------|
| `17797` | Web UI (direct, with sign-in — none through Ingress) |

## Scope

CrowdPanel replaces no bouncer and reads no logs. It only manages the decisions
held by the CrowdSec engine; enforcing them stays with the bouncers, for example
the one inside [NPMplus](../npmplus/).

What `cscli bouncers list`, `machines list`, `hub list` and `metrics` show does
not come from the API — there are no endpoints for it. Bouncers, machines and hub
are read from the CrowdSec database and configuration directory, the metrics from
CrowdSec's Prometheus endpoint.

## Documentation

Full setup, all options, troubleshooting: **[DOCS.en.md](DOCS.en.md)**
