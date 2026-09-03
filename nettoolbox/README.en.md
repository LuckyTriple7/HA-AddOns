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
- **Blocklists** — an IP checked against 15 public DNSBL/RBL lists in parallel, with reason text
- **SSL/TLS** — certificate chain, expiry, hostname coverage, negotiated TLS version
- **Whois/RDAP** — registrar, registration/expiry dates, name servers; RDAP first, WHOIS fallback for TLDs without RDAP (e.g. .de)
- **HTTP headers** — redirect chain, security headers, HTTP/3 advertisement (Alt-Svc)
- **SMTP** — banner, EHLO capabilities, STARTTLS, open-relay test (never actually delivers mail)
- **HTTP/3 (QUIC)** — a real handshake over UDP/443, not just the Alt-Svc advertisement
- **Ping / Traceroute** — via the container's own system tools
- **DNSSEC** — DS/DNSKEY status, whether the resolver validated the answer (AD flag)
- **Monitoring** — check domains/IPs automatically at a chosen interval (TLS expiry, blocklists,
  mail health), notification by email or Telegram on a state change; SMTP/Telegram set up via
  the gear icon in the header, not the add-on options
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

## Standalone (without Home Assistant, e.g. with Dockge)

The same image also runs without the Supervisor — see [docker-compose.yml](docker-compose.yml):

```sh
docker compose up -d
docker compose logs nettoolbox   # shows the generated password for "admin"
```

On first start NetToolbox creates `data/options.json` itself, with a random password printed to
the log. That same instance can act as a root-server worker (set `worker_enabled` and
`worker_token` in the file) or as a client of one (`worker_url` and `worker_token`).
