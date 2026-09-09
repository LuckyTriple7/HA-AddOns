# Anubis

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=anubis&style=flat-square)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

🇩🇪 [Deutsche Version](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/README.md)

Proof-of-work bot challenge based on [Anubis](https://github.com/TecharoHQ/anubis) — placed in front of a reverse proxy to slow down automated traffic (scrapers, scanners, simple bots).

## How it works

```text
Internet → reverse proxy (e.g. NPMplus) → Anubis challenge → application
```

- A bare engine with no UI of its own, no Ingress, no published port — only other add-on containers reach it, via its hostname on port 8923
- Ships a self-contained policy with no external imports: challenges any client without a valid auth cookie, no implicit ALLOW branch
- Google, Bing, DuckDuckGo, Qwant, Internet Archive, Kagi, Marginalia, Mojeek, Common Crawl, Wikimedia and Arquivo.pt exempted by default (verified via IP+user agent), can be turned off via `allow_search_engines`
- UptimeRobot and updown.io exempted by default (`allow_monitoring_services`), so external monitoring doesn't permanently report "down"
- AI bot tier `ai_bot_policy` (off/aggressive/moderate/permissive) — finer control than the generic challenge, identical to Anubis' own presets
- Your own trusted IP ranges via `trusted_ip_ranges`, no user-agent check
- Pre-wired for this repo's [NPMplus add-on](../npmplus/) via its `AUTH_REQUEST_ANUBIS_UPSTREAM`
- Policy freely editable at `/data/policy.yaml`

## Configuration

| Option | Default | Description |
|--------|---------|--------------|
| `TZ` | `Europe/Berlin` | Container timezone |
| `log_level` | `info` | Log level: `debug`, `info`, `warn`, `error` |
| `allow_search_engines` | `true` | Exempt real search engine/archive crawlers from the challenge (verified via IP+user agent). Off = truly everyone gets challenged |
| `allow_monitoring_services` | `true` | Exempt UptimeRobot & updown.io from the challenge (verified via IP+user agent). Self-hosted Uptime Kuma unaffected (no fixed IP) |
| `ai_bot_policy` | `off` | `off`/`aggressive`/`moderate`/`permissive` — how known AI/LLM clients are treated, see the docs |
| `trusted_ip_ranges` | `[]` | Your own IPs/CIDR ranges that never see the challenge — a plain IP exemption, no user-agent check |

Setup with NPMplus, testing the auth request, customizing the policy and troubleshooting: **[Documentation](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/DOCS.en.md)**

## Notes

- Architecture: amd64 and aarch64.
- Doesn't replace a login — Anubis is an extra protection layer, not access control.
- Monitoring tools like Uptime Kuma usually can't solve the challenge — see the docs.

## Changelog

See [CHANGELOG.md](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/CHANGELOG.md)

## License

Anubis is licensed under the [MIT License](https://github.com/TecharoHQ/anubis/blob/main/LICENSE). This add-on only copies the static binary from the official image; details in [LICENSE.md](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/LICENSE.md).
