# NPMplus

🇩🇪 [Deutsche Version](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/DOCS.md)

Reverse proxy with a web interface, based on [NPMplus](https://github.com/ZoeyVid/NPMplus) — an actively maintained fork of NGINX Proxy Manager with HTTP/3, hardened TLS, a CrowdSec bouncer and AppSec/WAF.

## Requirements

- **Architecture**: amd64 (x86-64-v2 or newer) or aarch64. Plain first-generation x86-64 is not supported.
- **Ports 80, 443/TCP, 443/UDP and 81** must be free. If another reverse proxy add-on (e.g. NGINX Proxy Manager) is running, stop it first.
- On the router: **forward 443/UDP as well**, otherwise HTTP/3 stays unused.

## First setup

1. Configure the add-on: set at least `TZ` and `acme_email`.
2. Optionally set `initial_admin_email` and `initial_admin_password`. Without them NPMplus creates `admin@example.org` with a random password and prints it to the add-on log.
3. Start the add-on and check the log.
4. Open the interface: `https://<HA-IP>:81`

The interface certificate is self-signed — the browser warning on first access is expected.

> **No Ingress**: The NPMplus interface serves HTTPS only and uses absolute paths. The HA ingress proxy expects plain HTTP under a sub-path; the two are incompatible. Access therefore goes directly to port 81, bypassing the Home Assistant login — a strong admin password is mandatory.

## Migrating from NGINX Proxy Manager

Existing hosts cannot be imported automatically, the databases are incompatible. Shortest-downtime path:

1. Note every proxy host in the old add-on: domain, target IP, target port, scheme (http/https), enabled switches.
2. **Stop** the old add-on — otherwise it holds ports 80 and 443.
3. Start NPMplus, log in, recreate the hosts.
4. Issue a fresh Let's Encrypt certificate per host.

Let's Encrypt allows 50 certificates per week and domain, so reissuing a dozen domains is harmless. Only repeated failed attempts with an identical domain set hit the limit of 5 duplicate certificates per week.

**Important:** These DNS challenge providers are gone and need replacing: `certbot-dns-he`, `certbot-dns-dnspod`, `certbot-dns-online`, `certbot-dns-powerdns`, `certbot-dns-do`. Route53 is not supported either.

## CrowdSec

NPMplus ships the **bouncer** (nginx/Lua, blocks individual requests) and can talk to the **AppSec/WAF** endpoint. The CrowdSec engine itself keeps running in your CrowdSec add-on. An existing firewall bouncer stays useful and does not conflict — it blocks at IP level, the nginx bouncer at HTTP level.

### 1. Add the collection to CrowdSec

NPMplus writes a different log format than NGINX Proxy Manager. The `crowdsecurity/nginx-proxy-manager` collection does **not** parse it. Add to your CrowdSec configuration:

```yaml
collections:
  - crowdsecurity/home-assistant
  - crowdsecurity/http-cve
  - ZoeyVid/npmplus
```

`crowdsecurity/nginx-proxy-manager` can stay while the old add-on is still running, and be removed afterwards.

### 2. Get the logs to CrowdSec

Two ways, depending on how your CrowdSec reads. Both are switchable in the add-on.

**Option A — journald** (fits an existing journald acquisition):

Set the add-on option `log_to_stdout: true`. Then find the syslog identifier, for example in the terminal add-on:

```sh
journalctl --directory=/var/log/journal/ -o json -n 200 \
  | jq -r .SYSLOG_IDENTIFIER | sort -u | grep -i npmplus
```

The value looks like `app_<8-char-repo-hash>_npmplus`. Use it in the CrowdSec acquisition:

```yaml
---
source: journalctl
journalctl_filter:
  - "--directory=/var/log/journal/"
  - "SYSLOG_IDENTIFIER=app_xxxxxxxx_npmplus"
labels:
  type: npmplus
```

**Option B — files** (the way documented by the NPMplus project):

Set the add-on option `share_logs: true`, then the logs live in `/share/npmplus/logs`. The CrowdSec add-on needs access to `/share` for this.

```yaml
---
filenames:
  - /share/npmplus/logs/*.log
labels:
  type: npmplus
```

### 3. Enable AppSec/WAF (optional)

Add to the CrowdSec acquisition:

```yaml
---
listen_addr: 0.0.0.0:7422
appsec_config: crowdsecurity/appsec-default
name: appsec
source: appsec
labels:
  type: appsec
```

### 4. Register the bouncer

In the CrowdSec add-on:

```sh
cscli bouncers add npmplus
```

Put the returned key into the add-on options:

```yaml
crowdsec_enabled: true
crowdsec_api_key: "<key from cscli>"
crowdsec_lapi_url: "http://127.0.0.1:8080"
crowdsec_appsec_url: "http://127.0.0.1:7422"
```

Restart NPMplus. The log then shows `CrowdSec-Bouncer aktiv gegen …`.

> If CrowdSec runs in its own container without host networking, `127.0.0.1` is wrong — use the host or container IP and expose ports 8080 and 7422 there.

> With CrowdSec enabled nginx always buffers requests. `proxy_request_buffering off` no longer takes effect.

## Options

| Option | Default | Meaning |
|---|---|---|
| `TZ` | `Europe/Berlin` | Container timezone |
| `acme_email` | – | Email for Let's Encrypt |
| `initial_admin_email` | – | First user, only on the very first start |
| `initial_admin_password` | – | Its password; empty = random password in the log |
| `http_port` | `80` | HTTP port; changing it breaks the HTTP challenge |
| `https_port` | `443` | HTTPS port, TCP and UDP |
| `admin_port` | `81` | Web interface port |
| `disable_ipv6` | `false` | Disable IPv6 |
| `disable_h3_quic` | `false` | Disable HTTP/3 |
| `enable_mptcp` | `false` | Multipath TCP |
| `logrotate` | `true` | Write and rotate access logs |
| `logrotations` | `3` | How many rotated logs are kept |
| `error_log_level` | `warn` | From which level nginx writes to the error log |
| `share_logs` | `true` | Mirror logs to `/share/npmplus/logs` |
| `log_to_stdout` | `true` | Also send the access log to the add-on log (journald) |
| `goaccess` | `false` | GoAccess dashboard under `/goaccess` |
| `trust_ip` | – | Trusted proxy IPs for X-Forwarded-For |
| `trust_cloudflare` | `false` | Fetch and trust Cloudflare IP ranges |
| `crowdsec_enabled` | `false` | Enable the nginx bouncer |
| `crowdsec_lapi_url` | `http://127.0.0.1:8080` | CrowdSec Local API |
| `crowdsec_api_key` | – | Bouncer key from `cscli bouncers add` |
| `crowdsec_appsec_url` | `http://127.0.0.1:7422` | AppSec/WAF endpoint |
| `nginx_worker_processes` | `auto` | Number of nginx workers |
| `nginx_worker_connections` | `512` | Connections per worker |
| `cookie_secret` | – | Static key for login cookies |
| `extra_env` | `[]` | Additional NPMplus variables as `KEY=VALUE` |

Anything not listed here can be set through `extra_env`. The full list lives in the [NPMplus compose.yaml](https://github.com/ZoeyVid/NPMplus/blob/develop/compose.yaml):

```yaml
extra_env:
  - "ACME_SERVER=https://acme.zerossl.com/v2/DV90"
  - "NGINX_LOG_NOT_FOUND=true"
```

## Data and backup

Everything lives in the add-on's `/data`: SQLite database, certificates under `/data/tls`, nginx configuration, and the CrowdSec bouncer configuration at `/data/crowdsec/crowdsec.conf`.

A Home Assistant backup of this add-on therefore also contains **the private keys of your certificates**. Treat those backups accordingly.

## Troubleshooting

**Add-on will not start, port in use** — another proxy is still running (old NGINX add-on, Caddy, Traefik). Stop it first.

**Certificate cannot be issued** — port 80 must be reachable from the internet and the domain must resolve to your public IP. Behind CGNAT or with port 80 blocked, only the DNS challenge works.

**Wrong client IPs in the logs** — if another proxy or Cloudflare sits in front, add its IPs to `trust_ip` or enable `trust_cloudflare`.

**CrowdSec sees no attacks** — check in order: `logrotate` on, logs arriving (option A or B), collection `ZoeyVid/npmplus` installed, `cscli metrics` shows the acquisition.

**Logged out after every restart** — set `cookie_secret` to a fixed random value.

## License

NPMplus is licensed under [AGPL-3.0-or-later](https://github.com/ZoeyVid/NPMplus/blob/develop/LICENSE) and is based on the MIT-licensed nginx-proxy-manager. This add-on only packages the official `zoeyvid/npmplus` image — it does not modify the application.
