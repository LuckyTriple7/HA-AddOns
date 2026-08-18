# NPMplus

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=npmplus&style=flat-square)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

🇩🇪 [Deutsche Version](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/README.md)

Reverse proxy with a web interface, based on [NPMplus](https://github.com/ZoeyVid/NPMplus) — the actively maintained fork of NGINX Proxy Manager.

## Access

| Service | URL |
|--------|-----|
| Web interface | `https://<HA-IP>:81` |
| GoAccess statistics (optional) | `https://<HA-IP>:91` — separate port, bound to `127.0.0.1` by default |

The interface certificate is self-signed — the browser warning on first access is expected.

## Features

- **HTTP/3 (QUIC)** on UDP 443, custom nginx build with aws-lc
- **Let's Encrypt** including automatic renewal; other ACME servers (ZeroSSL, Google Public CA) via `extra_env`
- **Hardened TLS**: ML-KEM, Encrypted Client Hello, modern cipher selection out of the box
- **CrowdSec bouncer and AppSec/WAF** configurable straight from the add-on options
- **Country filter** inside nginx, no MaxMind account — block or allow list, a ready-made preset, per-hostname exceptions and your own IP block list
- **mTLS**: client certificates and custom CAs can be uploaded
- **Access lists** per host and per location, multiple lists combinable
- **GoAccess dashboard** on port 91, without its own login — bound to `127.0.0.1` by default, reached through a proxy host with an access list
- **zstd and brotli compression**, file and PHP server with fancyindex
- Logs to `/share/npmplus/logs` and/or the add-on log — matching both CrowdSec acquisition styles

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `TZ` | `Europe/Berlin` | Container timezone |
| `acme_email` | – | Email address for Let's Encrypt |
| `initial_admin_email` | – | First user, only on the very first start |
| `initial_admin_password` | – | Its password; empty = random password in the log |
| `admin_port` | `81` | Web interface port |
| `logrotate` | `true` | Write and rotate access logs |
| `goaccess` | `false` | GoAccess dashboard on port 91 |
| `goaccess_listen_localhost` | `true` | Bind the dashboard to `127.0.0.1` only |
| `share_logs` | `true` | Mirror logs to `/share/npmplus/logs` |
| `log_to_stdout` | `true` | Also send the access log to the add-on log (journald) |
| `crowdsec_enabled` | `false` | Enable the nginx bouncer |
| `crowdsec_api_key` | – | Key from `cscli bouncers add npmplus` |
| `geo_mode` | `off` | Country filter: `block`, `allow` or `off` |
| `geo_preset` | `none` | Ready-made selection: `high_risk` (21 countries) |
| `geo_countries` | `[]` | Two-letter country codes, e.g. `cn` |
| `geo_deny_ips` | `[]` | Always-blocked addresses or CIDR ranges |
| `extra_env` | `[]` | Additional NPMplus variables as `KEY=VALUE` |

Full option list, CrowdSec setup and migration from the old NGINX Proxy Manager add-on: **[documentation](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/DOCS.en.md)**

## Notes

- Requires ports **80, 443/TCP, 443/UDP and 81** — any other reverse proxy has to be stopped first.
- Forward **443/UDP** on the router as well, otherwise HTTP/3 stays unused.
- **No Ingress**: the interface runs directly on port 81, bypassing the Home Assistant login. Set a strong admin password.
- Architecture: amd64 (x86-64-v2 or newer) and aarch64.

## Changelog

See [CHANGELOG.md](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/CHANGELOG.md)

## License

NPMplus is licensed under [AGPL-3.0-or-later](https://github.com/ZoeyVid/NPMplus/blob/develop/COPYING) and is based on the MIT-licensed nginx-proxy-manager. This add-on builds on the official `zoeyvid/npmplus` image and replaces its entrypoint; the application itself is unchanged. Details in [LICENSE.md](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/LICENSE.md).
