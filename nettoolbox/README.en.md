# NetToolbox

**Network and mail diagnostics for Home Assistant** · [Deutsch](README.md)

DNS lookups, propagation checks, reverse DNS, DNSSEC, and a full mail health
check (SPF/DKIM/DMARC/MTA-STS/TLS-RPT/BIMI) — no third-party API, and nothing
about your domains leaves your own infrastructure.

## Features

- **DNS** — every common record type, all standard types in one pass, TXT, SOA with a
  name-server sync check
- **Mail health** — SPF (including RFC 7208 lookup count and include-chain resolution), DKIM
  (key strength, common selectors are guessed), DMARC (policy, report addresses, foreign-domain
  authorisation), MTA-STS (policy file checked against the real MX records), TLS-RPT, BIMI — with
  its own 0-100 score
- **Propagation** — the same query against eight public resolvers at once
- **Reverse DNS / MX** — PTR with forward confirmation, MX servers with addresses and reverse
  names
- **DNSSEC** — DS/DNSKEY status, whether the resolver validated the answer (AD flag)
- **Root-server worker** — the same instance can act as a target for a second one: with a fixed
  IPv4 and an open port 25, lookups run where blocklists actually answer and SMTP tests are
  possible, instead of behind a typical home connection
- History, rate limiting, dark/light · DE/EN · HA Ingress

## Quick start

1. Install the add-on, change `password` in the options
2. Optional: run a second instance on a root server with a fixed IPv4, set `worker_enabled` and a
   random `worker_token` there, and enter both under `worker_url` / `worker_token` on the
   home instance

## Ports

| Port | Purpose |
|------|---------|
| 17798 | NetToolbox web UI (direct, sign-in required) |

## Standalone (without Home Assistant)

The same image also runs without the Supervisor — options then come from environment variables
instead of `/data/options.json`:

```sh
docker run -d --name nettoolbox -p 17798:17798 \
  -e NETTOOLBOX_OPTIONS=/config \
  -v /path/to/config:/config \
  ghcr.io/luckytriple7/nettoolbox
```

`/config/options.json` must exist (see `dev_run.py` for an example).
