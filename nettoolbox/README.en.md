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
- **Operator / software detection** — operator from the MX names (Microsoft 365, Google, IONOS, STRATO …), MTA software from the SMTP banner (Postfix, Exim, Exchange …)
- **HTTP/3 (QUIC)** — a real handshake over UDP/443, not just the Alt-Svc advertisement
- **Ping / Traceroute** — via the container's own system tools
- **IP lookup** — location, provider and AS number of an IP (ip-api.com), including your own public IP
- **DNSSEC** — DS/DNSKEY status, whether the resolver validated the answer (AD flag)
- **Monitoring** — check domains/IPs automatically at a chosen interval (TLS expiry, blocklists,
  mail health), notification by email or Telegram on a state change; SMTP/Telegram set up via
  the gear icon in the header, not the add-on options
- **Root-server worker** *(optional)* — a home instance can hand its checks to a second instance
  on a root server, where port 25 is open and blocklists answer. Running NetToolbox on the root
  server in the first place makes this unnecessary — see
  [Do I need the root-server worker?](#do-i-need-the-root-server-worker)
- History, rate limiting, dark/light · DE/EN · HA Ingress

## Quick start

1. Install the add-on, change `password` in the options
2. That's it — every check works right away. The worker options are **optional** and only
   needed for the special case described in the next section.

## Ports

| Port | Purpose |
|------|---------|
| 17798 | NetToolbox web UI (direct, sign-in required) |

## Do I need the root-server worker?

Short answer: **usually not.** The worker solves exactly one problem, and it is a problem of an
ordinary home connection:

- **Outbound port 25 is blocked** — most consumer ISPs block it, which makes SMTP tests
  impossible.
- **Blocklists stay silent** — Spamhaus and other DNSBLs often refuse to answer queries coming
  from consumer IPs and large public resolvers.

If a root server with a fixed IPv4 and an open port 25 is available, a second NetToolbox
instance there can take over the checks — the home instance asks, the root server executes.

**The decision in one line:**

| Setup | What to configure |
|-------|-------------------|
| A single instance, wherever it runs (including directly on the root server) | **nothing.** Leave every `worker_*` option empty or `false` — the status pill reads "Local", which is the intended state |
| A home instance **and** a second one on the root server | configure both sides, see below |

Running NetToolbox on the root server in the first place means it already probes from exactly
the connection that matters. There is nothing to hand off.

### Setting it up when both instances run

The token is the only access control, so it has to exist on **both** sides. Without
`worker_enabled` the `/worker/info` and `/worker/probe` endpoints stay switched off and answer
with `worker_disabled` — the client then only ever gets an error back.

**1. On the root server** (the instance doing the work):

```json
"worker_enabled": true,
"worker_token": "<output of: openssl rand -hex 32>"
```

**2. At home in the Home Assistant add-on** (the instance asking) under *Settings → Add-ons →
NetToolbox → Configuration*:

| Option | Value |
|--------|-------|
| `worker_url` | base address of the root server **without a path**, e.g. `https://nettoolbox.example.com` |
| `worker_token` | the same random value as above |
| `worker_tls_verify` | leave at `true` as long as a real certificate is in place |
| `worker_enabled` | stays `false` here — the home instance is a client, not a worker |

The status pill in the header then reads "Worker connected" (at home) and "Worker mode" (on the
root server).

> **Security:** the token travels as an `X-Nettoolbox-Token` header on every request. Over plain
> `http://` it crosses the internet in the clear, and whoever holds it can use the root server as
> a scanner. Put the worker behind a reverse proxy with TLS instead of exposing port 17798
> directly.

## Standalone (without Home Assistant, e.g. with Dockge)

The same image also runs without the Supervisor — see [docker-compose.yml](docker-compose.yml):

```sh
docker compose up -d
```

On first start NetToolbox creates `data/options.json` itself, with a randomly generated password
for the `admin` user. **That password is only ever written to the file, never to the log** —
container logs are too easy to read and kept for too long:

```sh
cat ./data/options.json
```

Every option from the section above is set in that same file, under the same names. Changes take
effect immediately, no restart needed: the file is re-read whenever its timestamp changes.

Since the password and the token sit in there in the clear: `chmod 600 ./data/options.json`.

### With Dockge, step by step

Dockge keeps every stack under `/opt/stacks/<stackname>/`, so the `./data` volume from the
compose file ends up in `/opt/stacks/nettoolbox/data/`.

1. Create a new stack `nettoolbox` in Dockge, paste the contents of
   [docker-compose.yml](docker-compose.yml), then **Deploy**.
2. The first start creates `/opt/stacks/nettoolbox/data/options.json` with a random password for
   `admin`.
3. Open that file — through the **terminal** Dockge offers for each stack (it starts in the
   stack directory on the host), or over SSH:
   ```sh
   cat /opt/stacks/nettoolbox/data/options.json     # read the password
   vi  /opt/stacks/nettoolbox/data/options.json     # edit
   ```
4. Tighten the permissions, since the password and the token sit in there in the clear:
   ```sh
   chmod 600 /opt/stacks/nettoolbox/data/options.json
   ```
5. Sign in at `http://<server>:17798` with `admin` and the password you just read.

### Setting the worker options in options.json

Only needed when a home instance exists that should hand its checks over here — see
[Do I need the root-server worker?](#do-i-need-the-root-server-worker). This instance is then the
**executing** side:

First generate a token:

```sh
openssl rand -hex 32
```

Its output goes into `worker_token`:

```json
{
  "username": "admin",
  "password": "<your password>",
  "worker_enabled": true,
  "worker_token": "<the 64 characters from openssl>",
  "worker_url": ""
}
```

`worker_url` stays empty here — the address goes on the *asking* side, i.e. in the Home
Assistant add-on. Saving is enough, no restart of the stack required.

For the opposite direction, where this standalone instance hands its checks to a worker, put
`worker_url` and `worker_token` here instead and leave `worker_enabled` at `false`.
