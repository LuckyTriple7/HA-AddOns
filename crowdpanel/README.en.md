# CrowdPanel

**CrowdSec control panel for Home Assistant** · [Deutsch](README.md)

View, create and lift decisions — without `cscli` on the command line.
CrowdPanel talks to the Local API of an existing CrowdSec installation and turns
it into a web interface.

## Features

- **Overview** — active decisions, alerts from the last 24 hours, top countries and scenarios
- **Decisions** — filter by scope, type and origin; lift them one by one or all at once
- **New ban** — single IP, CIDR range, whole country or whole network (AS), with a free duration and reason
- **Alerts** — what CrowdSec detected, with its events and the triggering log line
- **Check IP** — active decisions, alert history and allowlist hits for an address
- **Allowlists** — see which addresses are exempt from decisions
- **Two-factor sign-in** — TOTP for the direct port, QR code generated locally, backup codes
- Dark / light · DE / EN · HA Ingress · PWA

## Quick start

1. Create a machine account in CrowdSec:
   ```sh
   CS=$(docker ps --format '{{.Names}}' | grep -i crowdsec)
   CFG=/config/.storage/crowdsec/config/config.yaml
   PW=$(openssl rand -hex 22)
   docker exec $CS cscli -c $CFG machines add crowdpanel --password "$PW"
   echo "$PW"
   ```
   The `-c $CFG` is mandatory → [DOCS.en.md](DOCS.en.md#step-1--create-a-machine-account-in-crowdsec)
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

Not included: `cscli bouncers list`, `machines list`, `metrics` and `hub list` —
those commands read the local CrowdSec database instead of the API.

## Documentation

Full setup, all options, troubleshooting: **[DOCS.en.md](DOCS.en.md)**
