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

The bouncer needs a key from **your** CrowdSec instance. Without a valid key AppSec answers with HTTP 403 — and 403 means "block" in the AppSec protocol. A wrong key would therefore block every single request. The add-on verifies the key at startup and starts without the bouncer if anything is off.

Find the container names (in a terminal add-on with Docker access):

```sh
docker ps --format '{{.Names}}' | grep -iE 'crowdsec|npmplus'
```

> **The biggest pitfall:** by default `cscli` uses `/etc/crowdsec/config.yaml` — but the CrowdSec **add-on** starts the engine with its own configuration, typically under `/config/.storage/crowdsec/config/config.yaml`. Without `-c` you register the bouncer in a database the running instance never reads. `cscli bouncers list` happily shows it, yet the LAPI still answers **403**.
>
> The running process reveals the real configuration:
> ```sh
> docker exec <crowdsec-container> ps aux | grep crowdsec
> ```
> The path after `-c` is the right one. Pass it to **every** `cscli` call.

Create the key — use `-k` to supply your own hex-only key so no `+`, `/` or `=` can get lost while copying:

```sh
KEY=$(openssl rand -hex 22)
echo "$KEY"

docker exec <crowdsec-container> cscli -c /config/.storage/crowdsec/config/config.yaml \
  bouncers add npmplus -k "$KEY"
```

Verify — `npmplus` must show up here:

```sh
docker exec <crowdsec-container> cscli -c /config/.storage/crowdsec/config/config.yaml bouncers list
```

Without `-k`, `cscli` generates the key itself; it is shown **once** and cannot be retrieved later. If the name already exists, run `cscli … bouncers delete npmplus` first.

### 5. Determine the CrowdSec address

`http://127.0.0.1:8080` is only correct if CrowdSec publishes its ports on the host. If it runs as a regular add-on inside the Docker network, `127.0.0.1` is the host from NPMplus' point of view — and nothing listens there. Result: `connection refused`.

Find the container IP:

```sh
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' <crowdsec-container>
```

Then in the add-on options:

```yaml
crowdsec_enabled: true
crowdsec_api_key: "<key from cscli>"
crowdsec_lapi_url: "http://172.30.33.22:8080"
crowdsec_appsec_url: "http://172.30.33.22:7422"
```

> Container IPs can change when the CrowdSec add-on is updated. If its configuration offers a port mapping to the host, that is the more stable choice — then `127.0.0.1` is correct.

> If AppSec is not running (no `appsec` block in the acquisition), `crowdsec_appsec_url` must be left **empty**.

### 6. Verify

Restart NPMplus. The log contains exactly one of these lines:

```
[INFO] CrowdSec bouncer active against http://…
[WARN] CrowdSec rejected the bouncer key (HTTP 403) — bouncer stays OFF.
```

On the CrowdSec side, check that the bouncer is registered and pulling decisions:

```sh
docker exec <crowdsec-container> cscli -c /config/.storage/crowdsec/config/config.yaml bouncers list
```

`npmplus` must be listed with a recent "Last API pull" timestamp. An empty list means the key was never created — repeat step 4.

To check that log lines arrive:

```sh
docker exec <crowdsec-container> cscli -c /config/.storage/crowdsec/config/config.yaml metrics
```

Under **Acquisition Metrics** the npmplus source must appear with a rising `lines read`.

### 7. Captcha instead of a hard block (optional)

The bouncer can make suspicious visitors solve a challenge instead of locking them out — useful for borderline cases that may also hit real users.

Supported providers are **Turnstile** (Cloudflare, free, no user profiling — recommended), **hCaptcha** and **reCAPTCHA**. Create a key pair at the provider and fill in:

```yaml
crowdsec_captcha_provider: turnstile
crowdsec_captcha_site_key: "0x4AAA…"
crowdsec_captcha_secret_key: "0x4AAA…"
```

> **Important:** a captcha only appears if CrowdSec issues decisions of type `captcha`. By default it issues `ban`. That is controlled by `profiles.yaml` in the CrowdSec configuration, for example:
> ```yaml
> name: captcha_remediation
> filters:
>   - Alert.Remediation == true && Alert.GetScenario() contains "http-crawl"
> decisions:
>   - type: captcha
>     duration: 4h
> ```
> Without that change every decision stays a hard block, no matter which keys are configured.

To test, issue a captcha decision for your own IP:

```sh
docker exec $CS cscli -c $CFG decisions add --ip <your-ip> --duration 5m --type captcha
```

The page itself can be customised in `/data/crowdsec/captcha.html`; the untouched template sits next to it as `captcha.html.example`.

### Diagnostics at a glance

Run everything in a terminal add-on with Docker access. `CS` is the CrowdSec container, `NP` the NPMplus one.

```sh
CS=$(docker ps --format '{{.Names}}' | grep -i crowdsec | head -1)
NP=$(docker ps --format '{{.Names}}' | grep -i npmplus | head -1)
CFG=/config/.storage/crowdsec/config/config.yaml
```

| Question | Command |
|---|---|
| Which configuration does the running engine use? | `docker exec $CS ps aux \| grep crowdsec` |
| Is the bouncer registered and pulling? | `docker exec $CS cscli -c $CFG bouncers list` |
| Do log lines arrive? | `docker exec $CS cscli -c $CFG metrics` |
| Who is currently banned? | `docker exec $CS cscli -c $CFG decisions list` |
| Which collections are installed? | `docker exec $CS cscli -c $CFG collections list` |
| What is the CrowdSec container's IP? | `docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' $CS` |
| Are LAPI and AppSec reachable? | `nc -z -v <crowdsec-ip> 8080 && nc -z -v <crowdsec-ip> 7422` |
| What is in the NPMplus bouncer configuration? | `docker exec $NP grep -E '^(ENABLED\|API_URL\|APPSEC_URL)=' /data/crowdsec/crowdsec.conf` |
| Does the LAPI accept this exact key? | see below |

Test the key directly — takes the value from the file and queries the LAPI, bypassing the add-on:

```sh
KEY=$(docker exec $NP sh -c "grep '^API_KEY=' /data/crowdsec/crowdsec.conf | cut -d= -f2-")
echo "length: ${#KEY}"   # cscli generates 44 characters
docker exec $CS curl -s -o /dev/null -w '%{http_code}\n' \
  -H "X-Api-Key: $KEY" "http://127.0.0.1:8080/v1/decisions?ip=1.2.3.4"
```

`200` means the key is valid. `403` means the running instance does not know it — almost always because it was created with `cscli` without `-c` and landed in the wrong database.

The fastest way to prove the bouncer really blocks is a temporary ban on your own IP:

```sh
docker exec $CS cscli -c $CFG decisions add --ip <your-ip> --duration 2m --type ban
```

Then open one of your domains: the block page must appear. Undo it with:

```sh
docker exec $CS cscli -c $CFG decisions delete --ip <your-ip>
```

## Home Assistant behind NPMplus

Home Assistant answers requests from an unknown proxy with **400 Bad Request**. NPMplus runs on the host network and therefore has no container address of its own — requests arrive with the machine's LAN IP, not from the `172.30.x.x` network. An entry that worked for a bridged add-on does not apply here.

In **Settings → System → Network** under "Trust X-Forwarded-For", or in `configuration.yaml`:

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 127.0.0.1
    - ::1
    - 192.168.178.200   # LAN IP of the Home Assistant machine
    - 172.30.32.0/23
```

Then **restart** Home Assistant — `http:` is only evaluated at startup.

Alternatively point the proxy host at the internal address `http://172.30.32.1:8123`; the source IP then stays inside the Docker network and the existing list already covers it.

> The same applies to **every other service behind NPMplus** that validates trusted proxies — Nextcloud, Vaultwarden, Uptime Kuma and the like. They all need the Home Assistant machine's LAN IP in their proxy list instead of a `172.30.x.x` address. Left out, the service either rejects the request outright or logs every access with the proxy IP — at which point its brute-force protection may lock you out of your own instance.


## GoAccess statistics

GoAccess parses the access log and shows visitors, top hosts, requested URLs, status codes, traffic, browsers and referrers — live, updated over a WebSocket.

Turn it on with `goaccess: true`. `logrotate` is enabled along with it, without an access log GoAccess would have nothing to read. The service only starts once the log actually has lines in it, so right after a start the page stays empty for a moment.

> **Not under `/goaccess`.** In the NPMplus version used here GoAccess runs as its own HTTPS server on **port 91**, not as a sub-path of the interface. `https://<HA-IP>:81/goaccess` therefore returns the NPMplus error page. The move to a sub-path with an admin check does exist in the NPMplus development branch, but is not part of any release yet.

### Securing access

The server on port 91 has **no authentication**. Whoever reaches it sees every visitor IP and every URL requested from your services. The add-on therefore binds it to `127.0.0.1` by default (`goaccess_listen_localhost: true`).

Recommended route to the dashboard — a proxy host with an access list in front:

1. Create an **access list** in NPMplus (username and password, optionally restricted to your subnet as well).
2. Create a **proxy host**, e.g. `stats.your-domain.tld`, target `https://127.0.0.1:91`.
3. Pick that access list on the "Options" tab, issue a certificate on the "TLS" tab and force HTTPS.
4. Enable **Websockets support** — without it the live refresh stalls.

For a quick look without a proxy host: set `goaccess_listen_localhost: false` and open `https://<HA-IP>:91`. Every device on the LAN can then read along. **Never put port 91 into a router port forward.**

The report contains personal data (IP addresses). If the services behind it are public, mention it in your privacy policy.

### Country breakdown

Not included out of the box. Put the MaxMind databases (free account) into `/data/goaccess/geoip` — `GeoLite2-City.mmdb`, `GeoLite2-Country.mmdb` or `GeoLite2-ASN.mmdb`. NPMplus picks up whatever it finds at startup.

## Per-host settings

### "Options" tab

| Option | Meaning | Recommendation |
|---|---|---|
| Send noindex header and block some user agents | Sends `X-Robots-Tag: noindex` and blocks known crawlers | On for private services, off for public websites — otherwise the site disappears from search engines |
| Disable Crowdsec Appsec | Turns the WAF check off for this host only | Off. Enable only on false positives (e.g. large uploads, WebDAV) |
| Disable Request Buffering | nginx normally buffers the request body before forwarding it | Off. Useful for very large uploads — with CrowdSec enabled everything is buffered anyway |
| Disable Response Buffering | The response is passed through immediately instead of collected | Off. Only needed for live streams (server-sent events, running log output) |
| Enable compression by upstream | Lets the backend compress | Off. NPMplus compresses better with brotli/zstd |
| Disable URI Sanitisation | nginx no longer normalises the URL | Off. Only if an app needs encoded special characters in the path |
| Spoof Host Header | Sends the target IP as `Host` instead of the requested domain | Off. Breaks redirects and absolute links in most applications |
| Enable fancyindex | Directory listing — only relevant when NPMplus serves files itself | No effect on a proxied target |
| X-Frame-Options | Controls whether the page may be framed | Keep `SAMEORIGIN`; use `none` only if you want to embed the service elsewhere |
| Auth Request | Login enforced by Authelia, Authentik, tinyauth, oauth2-proxy or Anubis | `none` unless one of those runs. Otherwise also set the matching `AUTH_REQUEST_*_UPSTREAM` variable via `extra_env` |

### "TLS certificates" tab

| Switch | Meaning |
|---|---|
| Force HTTPS | Redirects HTTP to HTTPS. The ACME challenge on port 80 is unaffected |
| HTTP/3 support | Enables QUIC. Only effective if the router forwards 443/UDP — otherwise browsers silently fall back to HTTP/2 |
| HSTS enabled | Browsers remember: this domain over HTTPS only |
| HSTS subdomains+preload | **Enable with care.** `includeSubDomains` forces *every* subdomain onto valid HTTPS — a device that only speaks HTTP becomes unreachable in browsers. `preload` aims at inclusion in the browsers' built-in list; removal takes months |
| Keep key | Reuses the same private key on renewal. Required for DANE/TLSA records, otherwise a matter of taste |
| Use DNS challenge | Validation via a TXT record instead of port 80. Required behind CGNAT/DS-Lite and for wildcard certificates |

## Options

| Option | Default | Meaning |
|---|---|---|
| `TZ` | `Europe/Berlin` | Container timezone |
| `acme_email` | – | Email for Let's Encrypt |
| `acme_profile` | `shortlived` | Certificate lifetime: `shortlived` ≈ 6 days, `classic` = 90 days |
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
| `goaccess` | `false` | GoAccess dashboard on port 91 |
| `goaccess_listen_localhost` | `true` | Bind the dashboard to `127.0.0.1` only |
| `trust_ip` | – | Trusted proxy IPs for X-Forwarded-For |
| `trust_cloudflare` | `false` | Fetch and trust Cloudflare IP ranges |
| `crowdsec_enabled` | `false` | Enable the nginx bouncer |
| `crowdsec_lapi_url` | `http://127.0.0.1:8080` | CrowdSec Local API |
| `crowdsec_api_key` | – | Bouncer key from `cscli bouncers add` |
| `crowdsec_appsec_url` | `http://127.0.0.1:7422` | AppSec/WAF endpoint |
| `crowdsec_captcha_provider` | – | `turnstile`, `hcaptcha` or `recaptcha`; empty = off |
| `crowdsec_captcha_site_key` | – | Public key of the provider |
| `crowdsec_captcha_secret_key` | – | Secret key of the provider |
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

## Certificate lifetime

By default NPMplus requests the `shortlived` profile from Let's Encrypt — certificates last about **6 days**. Certbot renews every few hours, so in normal operation you never notice.

Upside: a leaked key becomes worthless within a week, and revocation lists stop mattering.

Downside: if renewal fails for longer — machine down, port 80 closed, DNS wrong — the certificates expire quickly. `classic` gives you the familiar 90 days and more headroom:

```yaml
acme_profile: classic
```

The change applies to the next issuance; it does not alter existing certificates.

## Data and backup

Everything lives in the add-on's private `/data` directory:

| What | Path |
|---|---|
| Database | `/data/npmplus/database.sqlite` |
| Encryption keys | `/data/npmplus/keys.json` |
| Let's Encrypt certificates | `/data/tls/certbot/live/npm-<id>/` |
| Custom certificates | `/data/tls/custom/` |
| CrowdSec bouncer configuration | `/data/crowdsec/crowdsec.conf` |
| nginx configurations | `/data/nginx/` |
| Logs | `/data/nginx/logs/` or `/share/npmplus/logs` |

### Reachable over Samba?

No. The Samba share exposes `config`, `share`, `media`, `backup`, `ssl` and `addons` — add-on data directories are not among them. The only exception is the logs: with `share_logs` enabled they live in `/share/npmplus/logs` and are visible there.

Everything else is reachable through a terminal add-on with Docker access. To look:

```sh
docker exec <npmplus-container> ls -la /data/tls/certbot/live/
```

To copy out:

```sh
docker cp <npmplus-container>:/data/npmplus/database.sqlite /share/npmplus-db.sqlite
docker cp <npmplus-container>:/data/tls /share/npmplus-tls
```

The copies then sit in `/share` and are visible over Samba.

> `/data/tls` holds the **private keys of your certificates**. A copy in `/share` can be read by anyone with access to the share — delete it once you are done.

### Regular backups

A Home Assistant backup of the add-on contains all of `/data`, database and certificates included, so there is nothing to copy by hand. The same warning applies though: that backup contains private keys.

## Troubleshooting

**Add-on will not start, port in use** — another proxy is still running (old NGINX add-on, Caddy, Traefik). Stop it first.

**Certificate cannot be issued, the error names an IPv6 address** — if the domain has an AAAA record, Let's Encrypt tries IPv6 first. If that record points at a device that does not answer, validation fails no matter how well IPv4 is set up. Check with `dig +short AAAA <domain>`; if you do not run IPv6, delete the record at your DNS provider. Note that subdomains have their own records — only CNAMEs inherit. And the DynDNS updater must stop reporting IPv6, otherwise the record reappears on its next run.

> Disabling IPv6 in the router or in the add-on does **not** help — only the DNS record matters.

**Certificate cannot be issued** — port 80 must be reachable from the internet and the domain must resolve to your public IP. Behind CGNAT or with port 80 blocked, only the DNS challenge works.

**Every site serves the CrowdSec block page** — the bouncer cannot reach CrowdSec or the key is rejected. Version 0.1.4 and later prevent this at startup; on older versions turn `crowdsec_enabled` off and restart.

**Wrong client IPs in the logs** — if another proxy or Cloudflare sits in front, add its IPs to `trust_ip` or enable `trust_cloudflare`.

**CrowdSec sees no attacks** — check in order: `logrotate` on, logs arriving (option A or B), collection `ZoeyVid/npmplus` installed, `cscli metrics` shows the acquisition.

**400 Bad Request from Home Assistant** — see the section "Home Assistant behind NPMplus".

**The log says "CrowdSec rejected the bouncer key (HTTP 403)" although the key is correct** — the bouncer sits in the wrong database. Without `-c`, `cscli` writes to `/etc/crowdsec/` while the add-on instance reads its own configuration. Re-create the bouncer with `-c <path from ps aux>`.

**Logged out after every restart** — set `cookie_secret` to a fixed random value.

**`https://<HA-IP>:81/goaccess` shows "Oops… you found an error page"** — that path does not exist. GoAccess runs on port 91, see the "GoAccess statistics" section.

**GoAccess dashboard stays empty** — the service only starts once `/data/nginx/logs/access.log` has lines in it, and it re-checks every 10 seconds. Load a page through the proxy and wait a moment.

**Port 91 does not answer** — the default is `goaccess_listen_localhost: true`, so the service listens on `127.0.0.1` only and is deliberately unreachable from the LAN.

## License

NPMplus is licensed under [AGPL-3.0-or-later](https://github.com/ZoeyVid/NPMplus/blob/develop/LICENSE) and is based on the MIT-licensed nginx-proxy-manager. This add-on only packages the official `zoeyvid/npmplus` image — it does not modify the application.
