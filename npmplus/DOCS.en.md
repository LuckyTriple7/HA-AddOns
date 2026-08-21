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

> **Prerequisite: CrowdSec is not part of this repository.** Everything described here requires a
> running CrowdSec engine (LAPI). Home Assistant has official add-ons for that:
> <https://github.com/crowdsecurity/home-assistant-addons> — `crowdsec` is the engine/LAPI,
> `crowdsec-firewall-bouncer` is optional and blocks at host firewall level.
>
> The bouncer for NPMplus itself is already built into NPMplus (OpenResty/Lua) — nothing extra to
> install. All it needs is an API key from the engine (`cscli bouncers add npmplus`, see step 4).
> Put it into the add-on options as `crowdsec_api_key` together with `crowdsec_enabled: true`. The
> add-on fills `/data/crowdsec/crowdsec.conf` from those options on every start — setting
> `ENABLED`, `API_URL`, `API_KEY`, `APPSEC_URL` or the captcha keys there by hand has no effect,
> while every other value in that file is left alone.
>
> Without an installed engine all CrowdSec options do nothing.

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

Through journald. One way, no second one.

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

The right address is the CrowdSec container's **hostname**:

```sh
docker inspect -f '{{.Config.Hostname}}' <crowdsec-container>
```

The result looks like `424ccef4-crowdsec`. The leading part is the add-on repository's id and differs between installations — read the real value instead of copying this one.

Then in the add-on options:

```yaml
crowdsec_enabled: true
crowdsec_api_key: "<key from cscli>"
crowdsec_lapi_url: "http://424ccef4-crowdsec:8080"
crowdsec_appsec_url: "http://424ccef4-crowdsec:7422"
```

> **Do not enter an IP address.** The container IP (`172.30.33.x`, found with `docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' <crowdsec-container>`) only holds until the next restart. Docker hands out a new one on every start, and restarting Home Assistant restarts every add-on container. After that `crowdsec_lapi_url` and `crowdsec_appsec_url` point nowhere and the bouncer stays off, without anyone having changed a thing. The hostname stays stable.

> NPMplus runs on the host network but still resolves other add-ons' hostnames — the Supervisor hands the HA DNS service to every add-on container. Should resolution ever fail, the long form `424ccef4-crowdsec.local.hass.io` works.

> If AppSec is not running (no `appsec` block in the acquisition), `crowdsec_appsec_url` must be left **empty**.

### Example CrowdSec add-on configuration

For comparison, a complete configuration of the official `crowdsec` add-on that works with
NPMplus. The syslog identifier is a placeholder — look up your own as shown in step 2.

```yaml
acquisition: |
  ---
  # Home Assistant Core - login attempts.
  # type: syslog is deliberate: syslog-logs derives the program from the
  # SYSLOG_IDENTIFIER, and home-assistant-logs filters on exactly that.
  source: journalctl
  journalctl_filter:
    - "--directory=/var/log/journal/"
    - "SYSLOG_IDENTIFIER=homeassistant"
  labels:
    type: syslog
  ---
  # NPMplus - reverse proxy access log.
  # type: npmplus is required: non-syslog derives the program from it, and
  # ZoeyVid/npmplus-logs filters on program startsWith 'npmplus'.
  source: journalctl
  journalctl_filter:
    - "--directory=/var/log/journal/"
    - "SYSLOG_IDENTIFIER=app_<repo-hash>_npmplus"
  labels:
    type: npmplus
  ---
  # AppSec/WAF - virtual patching and generic rules only.
  listen_addr: 0.0.0.0:7422
  appsec_config: crowdsecurity/appsec-default
  name: appsec
  source: appsec
  labels:
    type: appsec
disable_lapi: false
remote_lapi_url: ''
agent_username: ''
agent_password: ''
collections:
  - crowdsecurity/home-assistant
  - ZoeyVid/npmplus
  - crowdsecurity/http-cve
  - crowdsecurity/appsec-virtual-patching
  - crowdsecurity/appsec-generic-rules
  - crowdsecurity/http-dos
  - crowdsecurity/whitelist-good-actors
parsers: []
scenarios: []
postoverflows: []
parsers_to_disable:
  - crowdsecurity/whitelists
scenarios_to_disable: []
disable_online_api: false
```

Notes on it:

- **The `type:` of each source** decides which parser runs. `syslog` for Home Assistant (that
  parser takes the program from `SYSLOG_IDENTIFIER`), `npmplus` for NPMplus —
  `ZoeyVid/npmplus-logs` filters on a program whose name starts with `npmplus`.
- **`crowdsecurity/appsec-crs`** (OWASP Core Rule Set) is deliberately absent. On a typical Home
  Assistant install it fires false positives in bulk because it matches substrings — `elif`
  inside Jinja templates posted to `/api/template`, `sched` inside `schedule` in GitHub webhooks.
  Virtual patching plus the generic rules are enough to start with; CRS can be added later if you
  are willing to maintain exclusion lists.
- **`parsers_to_disable: crowdsecurity/whitelists`** turns off the whitelist for private address
  ranges. Useful if traffic from your own LAN should be judged too — remove the line again if it
  locks you out.
- **`disable_online_api: false`** reports attacks to the CrowdSec community and pulls the
  community blocklist in return. Set it to `true` to report nothing, at the cost of that blocklist.

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
| What is the CrowdSec container's hostname? | `docker inspect -f '{{.Config.Hostname}}' $CS` |
| Are LAPI and AppSec reachable? | `nc -z -v <crowdsec-hostname> 8080 && nc -z -v <crowdsec-hostname> 7422` |
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

## Country filter

Blocks whole countries inside nginx — no MaxMind account, no extra module, no CrowdSec. The decision is made on the very first packet, whereas CrowdSec only reacts after the first request has been parsed.

The address ranges come from [ipverse/country-ip-blocks](https://github.com/ipverse/country-ip-blocks), which turns the delegation files of the Regional Internet Registries (RIPE, ARIN, APNIC …) into ready-made CIDR lists every day. The add-on downloads them at startup and feeds them into nginx's built-in `geo` module.

### Two modes

```yaml
geo_mode: block
geo_countries:
  - cn
  - ru
  - kp
```

`block` lets everyone in and denies the listed countries. Recommended to start with.

### A preset instead of typing

```yaml
geo_mode: block
geo_preset: high_risk
```

Adds 16 countries in one go:

`CN` `RU` `KP` `IR` `PK` `BD` `VN` `MY` `TH` `PH` `NG` `GH` `ZA` `AR` `CO` `EG`

Around **38,000 address ranges** in total. The download takes a few seconds at startup, after that everything sits inside the container.

`geo_countries` still works alongside it — both lists are merged and duplicates are dropped:

```yaml
geo_preset: high_risk
geo_countries:
  - ua
  - by
```

**`geo_mode` is the master switch.** With it set to `off` nothing happens, no matter what the preset and the country list contain — the log warns about it. Combined with `allow` the preset is skipped with a warning, since a block list would suddenly have become an allow list.

You can tell the filter is really running by the log lines `Downloading country lists for … countries` and `Country filter active`. If they are missing, it is off.

**What is missing and why:** `IN`, `BR`, `MX`, `ID` and `TR` are deliberately left out. They are large internet countries with many real users — blocking them costs more in shut-out visitors than it saves in attacks. If you want them anyway, add them in `geo_countries`:

```yaml
geo_preset: high_risk
geo_countries:
  - in
  - br
```

The other way round: the selection stays coarse. Real people live in those 16 countries too. If you have friends there or expect someone on holiday, leave the country out and type the codes you want into `geo_countries` individually instead of using `high_risk`. Single addresses can be exempted through `geo_allow_ips`.

**Limits of the approach:** most automated attacks today come from data centres, not from residential lines — rented servers in the Netherlands, Germany or the US. Those are exactly the ones you cannot block, because that is where you are yourself. A country filter noticeably lowers the background noise in the log, but it does not replace CrowdSec.

```yaml
geo_mode: allow
geo_countries:
  - de
  - at
  - ch
```

`allow` turns it around: only the listed countries get through, everything else receives **403**.

### Exceptions

```yaml
geo_exempt_hosts:
  - home.example.com
```

The filter does not apply to these hostnames. That entry saves you when you are on holiday in a blocked country and need to reach Home Assistant.

Two exceptions are always applied by the add-on itself:

- **`/.well-known/acme-challenge/`** is never blocked. Let's Encrypt validates from the US — without this exception, issuance and renewal would be dead in `allow` mode.
- The **web interface on port 81** is unaffected, it runs in its own server block.

### Blocking or allowing single addresses

Independent of any country:

```yaml
geo_deny_ips:
  - 203.0.113.7
  - 198.51.100.0/24
  - 2001:db8::/32
```

These addresses always get **403** — even with `geo_mode: off` and even on the hostnames listed in `geo_exempt_hosts`. This is the hard block list for individual offenders.

The other way round:

```yaml
geo_allow_ips:
  - 203.0.113.7
```

The country filter never applies to these addresses, even if they sit in a blocked country. Meant for your own address while abroad or a monitoring service in another country. It has no effect on `geo_deny_ips` — whatever is listed there stays blocked.

Both lists take single addresses and CIDR ranges, IPv4 as well as IPv6. In the `geo` module the more specific entry always wins, so a single address beats the country block it sits in. Entries that are not an address are dropped with a warning in the log instead of being written into the configuration.

For lasting blocks against attackers CrowdSec is still the better tool — it finds them by itself and forgets them again. `geo_deny_ips` is for cases you decided on by hand.

### Refreshing

```yaml
geo_refresh_hours: 24
```

The registries move address blocks around all the time. After a few months without refreshing, the lists start blocking the wrong people. The add-on therefore downloads them again at the configured interval and reloads nginx only when something actually changed. `0` disables refreshing.

If the network is down at startup, the previously downloaded lists stay in effect. If there are none yet, the filter stays **off** — a failed download must never lock anyone out.

### Accuracy

Registry data says who an address block is *allocated to*, not where it is used. MaxMind measures on top of that and is closer to the truth in individual cases.

For `block` the difference is irrelevant. With `allow` and only `de`, however, real visitors get dropped as soon as their provider hands out addresses from a block registered abroad — common with mobile networks and large hosters. When in doubt, a block list is the healthier choice.

### Checking what is active

```sh
CT=$(docker ps --format '{{.Names}}' | grep npmplus)
docker exec $CT sh -c 'wc -l /data/geoip/ranges.conf; cat /data/geoip/http.conf'
```

### What blocked visitors get

```yaml
geo_deny_action: 403
```

The default. nginx serves a short block page in German and English. It lives at `/data/geoip/blocked.html` and can be edited freely — the add-on only creates it when it is missing and never overwrites it. Useful for adding a contact route for false positives.

```yaml
geo_deny_action: 444
```

nginx closes the connection without a single line of response. A scanner does not even learn that a server is listening on that address. The downside: a real visitor blocked by mistake only sees a dropped connection and reports "the site is down" instead of a clear error.

The block page does not replace CrowdSec's page. Both stay separate: internally the add-on answers with its own code 460 and only then converts it to 403. An `error_page 403` would also have swallowed the pages from CrowdSec and from access lists.

### Who was blocked, and from where

```yaml
geo_log_country: true
```

Writes every blocked request to `/data/nginx/logs/blocked.log`, with the country code:

```
2026-08-18T11:04:12+02:00 www.example.com 1.2.3.4 cn "GET /wp-login.php HTTP/1.1" 403 "python-requests/2.31"
```

The columns:

| Column | Content | Example |
|---|---|---|
| 1 | Timestamp | `2026-08-18T11:04:12+02:00` |
| 2 | Requested host | `www.example.com` |
| 3 | Source IP | `49.232.104.223` |
| 4 | Country | `cn` |
| 5–7 | Request, in quotes | `"GET /wp-login.php HTTP/1.1"` |
| 8 | Status code | `403` |
| 9+ | User agent, in quotes | `"python-requests/2.31"` |

Three evaluations worth running:

```sh
L=/share/npmplus/logs/blocked.log

# Which countries actually contribute?
awk '{print $4}' $L | sort | uniq -c | sort -rn

# Most persistent individual addresses
awk '{print $3, $4}' $L | sort | uniq -c | sort -rn | head -20

# What were they after?
awk -F'"' '{print $2}' $L | sort | uniq -c | sort -rn | head -20
```

The third one is the most revealing. If it is full of `/wp-login.php`, `/.env` or `/phpmyadmin`, those are plain scanners and the filter is doing its job. If ordinary page requests show up instead, you may have caught real visitors — then it is worth looking at which country they came from.

Countries that show up with a handful of hits can be dropped from the list again — every blocked country costs you real visitors.

> Lines written before 0.1.24 have one field more, because the timestamp contained a space back then. For those, `$5` is the country column. The next log rotation sorts it out.

Cost: a second lookup table in memory, around 4 MB for 38,000 ranges. In allow mode the column shows `-`, because only the permitted countries were downloaded and the origin of the rest stays unknown.

The regular NPMplus access log is untouched alongside it.

### Startup time

At startup the add-on checks whether the lists on disk still match the configuration and are younger than `geo_refresh_hours`. If so the download is skipped and the proxy comes up immediately:

```
[INFO] Country lists on disk are still current (38034 ranges) — skipping download
```

As soon as you change countries, switch mode or toggle `geo_log_country`, the fingerprint no longer matches and the lists are fetched again.

The add-on log covers the whole process:

```
[INFO] Country preset 'high_risk' adds 21 countries
[INFO] Downloading country lists for 21 countries from ipverse...
[INFO]   cn: 7551 ranges
[INFO]   ru: 10830 ranges
...
[INFO] Country lists ready: 72820 ranges in 9s
[INFO] Country filter active (block): cn,ru,kp,..., 72820 ranges
[INFO] IP deny list active: 3 entries
[INFO] Country lists are refreshed every 24 h
```

If a country is missing you get `Country list xx/ipv4-aggregated could not be downloaded` plus a closing warning about how many lists are missing. The filter still works, it is just incomplete.

### Applying changes

The nginx configuration for the filter is built when the add-on starts. After every change to `geo_mode`, `geo_preset`, `geo_countries`, `geo_exempt_hosts`, `geo_deny_ips`, `geo_allow_ips`, `geo_deny_action` or `geo_log_country`, **restart the add-on** — saving alone is not enough, and neither is `nginx -s reload`, because the files still hold the old state at that point.

The only exception is the list refresh driven by `geo_refresh_hours`: it runs while the add-on is up and reloads nginx by itself when something changed.

### Relation to CrowdSec

Running both makes sense and causes no conflict. The country filter is coarse and immediate, CrowdSec is fine-grained and keeps learning. If you have been doing country blocking through CrowdSec scenarios, you can switch that off there.

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
| `geo_mode` | `off` | Country filter: `block`, `allow` or `off` |
| `geo_preset` | `none` | Ready-made selection: `high_risk` or `none` |
| `geo_countries` | `[]` | Two-letter country codes, e.g. `cn` |
| `geo_exempt_hosts` | `[]` | Hostnames the filter does not apply to |
| `geo_deny_ips` | `[]` | Always-blocked addresses or CIDR ranges |
| `geo_allow_ips` | `[]` | Addresses the country filter never applies to |
| `geo_refresh_hours` | `24` | Interval for reloading the lists; `0` = off |
| `geo_deny_action` | `403` | Response when blocked: `403` with page or `444` silent |
| `geo_log_country` | `true` | Log blocked requests with country to `blocked.log` |
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

**CrowdSec used to work, after a restart the bouncer reaches nothing** — `crowdsec_lapi_url` holds a container IP (`172.30.33.x`) that Docker reassigned on start. Switch both URLs to the container hostname, e.g. `http://424ccef4-crowdsec:8080`.

**The log says "error loading captcha plugin: no recaptcha site key provided"** — cosmetic. With `crowdsec_captcha_provider` empty the bouncer falls back to `recaptcha` internally, finds no site key and turns captcha off. The bouncer itself keeps working. The line only disappears once captcha is set up with a provider and both keys (see step 7).

**The log says "Permission Denied" with HTTP 403 on `/api/nginx/...`** — these requests do not come from the add-on. The user agent (`HomeAssistant/…`) and the IP give it away: a Home Assistant integration is querying the NPMplus API, typically "Nginx Proxy Manager" from HACS. Signing in works (otherwise it would be 401), but the user configured there is not allowed to read those lists. In NPMplus open *Users*, set *Edit Permissions* to at least "View" or make the user an administrator — otherwise remove the integration. Proxying is unaffected; only that integration's sensors stay empty.

**Wrong client IPs in the logs** — if another proxy or Cloudflare sits in front, add its IPs to `trust_ip` or enable `trust_cloudflare`.

**CrowdSec sees no attacks** — check in order: `logrotate` on, logs arriving through journald (`log_to_stdout` on, identifier correct), collection `ZoeyVid/npmplus` installed, `cscli metrics` shows the acquisition.

**400 Bad Request from Home Assistant** — see the section "Home Assistant behind NPMplus".

**The log says "CrowdSec rejected the bouncer key (HTTP 403)" although the key is correct** — the bouncer sits in the wrong database. Without `-c`, `cscli` writes to `/etc/crowdsec/` while the add-on instance reads its own configuration. Re-create the bouncer with `-c <path from ps aux>`.

**Logged out after every restart** — set `cookie_secret` to a fixed random value.

**`https://<HA-IP>:81/goaccess` shows "Oops… you found an error page"** — that path does not exist. GoAccess runs on port 91, see the "GoAccess statistics" section.

**GoAccess dashboard stays empty** — the service only starts once `/data/nginx/logs/access.log` has lines in it, and it re-checks every 10 seconds. Load a page through the proxy and wait a moment.

**Port 91 does not answer** — the default is `goaccess_listen_localhost: true`, so the service listens on `127.0.0.1` only and is deliberately unreachable from the LAN.

## License

NPMplus is licensed under [AGPL-3.0-or-later](https://github.com/ZoeyVid/NPMplus/blob/develop/COPYING) and is based on the MIT-licensed nginx-proxy-manager.

This add-on builds on the official `zoeyvid/npmplus` image (pinned in the [Dockerfile](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/Dockerfile)) and **replaces its entrypoint** with `run.sh` so the add-on options arrive as environment variables. The application itself is not modified, no RUN layer is added.

The published image `ghcr.io/luckytriple7/npmplus` therefore contains a modified AGPL work and is, as a whole, covered by the **AGPL-3.0-or-later**. The add-on's own files are MIT licensed. Details and source references: [LICENSE.md](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/LICENSE.md).

Bug reports: anything about `run.sh`, the options or the docs belongs in [this repository](https://github.com/LuckyTriple7/HA-AddOns/issues); for bugs in NPMplus itself the project asks you to report [there](https://github.com/ZoeyVid/NPMplus/issues) first, not to the original nginx-proxy-manager.
