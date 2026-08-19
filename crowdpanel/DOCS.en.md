# CrowdPanel

A web interface for a running CrowdSec installation: see who is banned, ban an
address by hand, lift a ban that was set by mistake, browse alerts and look up a
single IP address — everything that would otherwise need `cscli` on the command
line.

CrowdPanel does not ship CrowdSec itself. It expects an existing installation,
for example the CrowdSec add-on, and talks to its Local API.

---

## What CrowdPanel does — and what it does not

Everything runs through the CrowdSec Local API (LAPI). That covers:

- list, filter and lift active decisions
- create new decisions: a single IP, a CIDR range, a whole country or a whole
  network (AS)
- browse alerts from the last hours to weeks, with their events and source
- look up an IP address: active decisions, alert history, allowlist hits
- view allowlists

Deliberately **not** included, because the LAPI does not offer it:
`cscli bouncers list`, `cscli machines list`, `cscli metrics` and
`cscli hub list`. Those commands read the local CrowdSec database, not the API.
Reaching it would mean mapping the Home Assistant configuration directory into
this add-on — too much access for too little gain. Home Assistant's own ban list
`ip_bans.yaml` is left out for the same reason; it is only read when Home
Assistant starts and has nothing to do with CrowdSec.

---

## Setup

### Step 1 — create a machine account in CrowdSec

CrowdPanel signs in to the LAPI the same way `cscli` does: as a **machine**. A
bouncer key is not enough — bouncers may only read decisions, not create or
delete them.

First find the name of the CrowdSec container:

```sh
docker ps --format '{{.Names}}' | grep -i crowdsec
```

Then create the account. `CFG` points at the CrowdSec add-on's config file:

```sh
CS=app_xxxxxxxx_crowdsec
CFG=/config/.storage/crowdsec/config/config.yaml
PW=$(openssl rand -hex 22)
docker exec $CS cscli -c $CFG machines add crowdpanel --password "$PW" -f -
echo "$PW"
```

> **The `-c $CFG` is mandatory.** Without it `cscli` writes to `/etc/crowdsec`,
> which is a different, empty database. The account would be created there, the
> running LAPI would never know about it, and CrowdPanel would get an
> "auth_failed" despite a correct password.

> **The `-f -` is mandatory too, and `--force` is the wrong answer.** Without
> `-f`, `cscli` wants to write the new credentials to
> `local_api_credentials.yaml` and stops because that file already exists. That
> file is how CrowdSec itself signs in to its own LAPI — overwriting it with
> `--force` points the local agent at the new account and breaks log processing.
> `-f -` prints the credentials to standard output instead and leaves the file
> alone.

`openssl rand -hex 22` produces 44 characters without `+`, `/` or `=`, so nothing
gets lost when copying.

Check that the account arrived:

```sh
docker exec $CS cscli -c $CFG machines list
```

`crowdpanel` must show up with a tick under "Validated".

### Step 2 — find the LAPI address

`http://127.0.0.1:8080` only works if CrowdSec publishes its ports on the host.
When CrowdSec runs as an add-on in its own container, the container address is
needed:

```sh
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' $CS
```

The result is typically something like `172.30.33.22`, making the LAPI
`http://172.30.33.22:8080`.

### Step 3 — set the options

| Option | Value |
|---|---|
| `lapi_url` | `http://172.30.33.22:8080` |
| `machine_id` | `crowdpanel` |
| `machine_password` | the password from step 1 |
| `password` | your own password instead of `changeme123` |

Start the add-on. The log then says:

```
[INFO] CrowdSec LAPI reachable at http://172.30.33.22:8080 (7 ms)
```

If a warning shows up instead, the [troubleshooting](#troubleshooting) table helps.

---

## Access and sign-in

CrowdPanel is reachable two ways, with different protection:

**Through the Home Assistant sidebar (Ingress).** Home Assistant has already
signed the user in before the request even reaches the add-on, so CrowdPanel does
not ask for a username and password again.

**Through the direct port 17797.** Here CrowdPanel signs you in itself, using
`username` and `password` from the options. After five failed attempts within ten
minutes, signing in is blocked for 15 minutes.

### Two-factor sign-in

Under *Settings* a second factor can be switched on for the direct port (TOTP,
like any authenticator app).

1. press *Enable* — a QR code appears
2. scan it with your authenticator app, or type the secret in by hand
3. enter the code it shows and confirm
4. write down the ten backup codes — they are shown **this one time only**

The QR code is generated inside the add-on. The secret never leaves the server and
is never sent to a third-party service.

Each backup code works exactly once. At sign-in a backup code can be entered
instead of the time-based code. "Trust this device for 30 days" skips the second
step on that browser; the cookie set for it is signed.

Through Ingress the second factor has no effect — there Home Assistant signs you in.

---

## The tabs

### Overview

Number of active decisions, alerts from the last 24 hours, the split by type and
origin, the most frequent countries and scenarios.

### Decisions

The table shows every active decision with value, scope, type, scenario, origin,
country, network and remaining time.

- **Search** filters the listed rows by value, scenario, country and network.
- **Scope**, **type** and **origin** are passed straight to the LAPI.
- **Unban** lifts exactly that one decision.
- **Lift all filtered** lifts exactly the listed rows, one after another. It never
  deletes more than what is on screen — on purpose, so a filter cannot
  accidentally take half the ban list with it. Above 200 entries CrowdPanel
  declines and asks for a narrower filter.

The table shows at most as many rows as `page_size` allows, with the full count
next to it. That is not pedantry: subscribe to the community blocklists and you
quickly reach 30,000 active decisions, which do not all belong in one table.
**Origin** sorts that out at once — `crowdsec` are the attacks this instance
detected itself, `cscli` the ones created by hand, `CAPI` and `lists` come from
outside.

> Unbanning has two routes with different reach. The button in the row uses the
> decision id and hits exactly that one entry. Unbanning by IP instead also lifts
> a covering range — that is CrowdSec's own behaviour, identical to
> `cscli decisions delete --ip`.
>
> For **country** and **network (AS)** there is no bulk filter; the LAPI offers
> none. Those decisions can only be lifted from the row.

### New ban

| Scope | Value | Example |
|---|---|---|
| `Ip` | a single address | `198.51.100.7` |
| `Range` | a CIDR range | `198.51.100.0/24` |
| `Country` | two-letter country code | `CN` |
| `AS` | network number without prefix | `64500` |

**Type** is `ban` (block) or `captcha` (show a captcha first). `captcha` only does
something if the bouncer has a captcha configured — in NPMplus for example through
`crowdsec_captcha_provider`. Without that setup, `captcha` does nothing at all.

**Duration** comes from the list or is typed in freely, in Go format: `30m`, `4h`,
`1h30m`, `168h`. CrowdSec has no unlimited ban; the longest preset is one year
(`8760h`).

**Reason** becomes the alert message and shows up in the alert list later.

> Decisions are created with origin `cscli`, not with an origin of their own.
> Bouncers and the CrowdSec console filter on known origins, and an unknown one
> could be silently ignored. That the decision came from CrowdPanel is recorded in
> the scenario text instead: `manual 'ban' from 'crowdpanel'`.

### Alerts

What CrowdSec detected, whether or not it turned into a decision. *Details*
fetches the full alert with its first 20 events and their fields — that is where
you see which log line triggered the alert.

### Check IP

One field for an address or a range. The result: every active decision for it, the
alert history, and whether the address is on an allowlist.

That includes decisions which merely cover the address — a banned range it falls
inside. The LAPI only matches literally, so CrowdPanel runs the containment test
itself; the result matches what `cscli decisions list --ip` shows.

The allowlist part matters: if an address is on an allowlist, **no** decision
applies to it — not even one just created by hand.

### Allowlists

Read-only. Allowlists are created and maintained with `cscli allowlists`.

---

## How this fits with the other pieces

CrowdSec has three parts, and CrowdPanel sits exactly in the middle:

| Part | Job | Who does it |
|---|---|---|
| Input | read logs and detect attacks | CrowdSec add-on (acquisition) |
| Decision | manage and serve decisions | CrowdSec engine with LAPI |
| Output | enforce decisions | bouncers, for example inside NPMplus |

CrowdPanel talks to the middle only. It replaces no bouncer and reads no logs — it
only changes which decisions the middle holds. The bouncer picks the change up at
its next pull, usually within seconds.

**About country blocking in NPMplus:** the `geo_mode` filter there works inside
nginx and acts one layer earlier, before CrowdSec sees anything. Banning a country
through CrowdPanel is a different thing: that decision applies to **every** bouncer
attached to the same LAPI. Both at once is possible but usually unnecessary — for a
permanently blocked country the nginx route is cheaper, for a quick ban that takes
effect everywhere the CrowdPanel route is better.

---

## Options

| Option | Default | Meaning |
|---|---|---|
| `username` | `admin` | username for the direct port |
| `password` | `changeme123` | password for the direct port — change it |
| `session_hours` | `24` | how long a sign-in stays valid, in hours |
| `lapi_url` | `http://127.0.0.1:8080` | address of the CrowdSec LAPI |
| `machine_id` | empty | name of the machine account |
| `machine_password` | empty | password of the machine account |
| `lapi_tls_verify` | `true` | verify the TLS certificate; only turn off for self-signed `https` |
| `default_ban_duration` | `4h` | preselected duration in the form |
| `refresh_interval` | `30` | seconds between automatic refreshes, `0` turns it off |
| `page_size` | `100` | how many rows the tables show at most |
| `verbose_log` | `false` | extra lines in the log |

---

## Paths

| Path | Content |
|---|---|
| `/data/options.json` | the options, written by Home Assistant |
| `/data/sessions.json` | open sign-ins |
| `/data/twofa.json` | 2FA secret, backup codes, trusted devices (mode 600) |
| `/data/secret.key` | signing key for cookies (mode 600) |

Everything lives in `/data` and therefore not in a browsable share folder. To reset
two-factor sign-in, delete `twofa.json` and restart the add-on.

---

## Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| Machine credentials are missing | `machine_id` or `machine_password` empty | do step 1 of the setup |
| LAPI cannot be reached | wrong address or port | check the container address with `docker inspect`, do not guess `127.0.0.1` |
| The machine credentials were rejected | machine created in the wrong database | run `cscli` again with `-c $CFG`; verify with `machines list` |
| The LAPI address is not an http(s) address | typo, missing `http://` | fix `lapi_url` |
| Decision created but the bouncer lets it through | bouncer has not pulled yet, or the address is on an allowlist | open *Check IP* and read the allowlist line |
| Request rejected, reload the page | session or form expired | reload the page |

More detail is in the add-on log. With `verbose_log: true` lines about setting up
and tearing down the LAPI connection are added.

### About speed

On an instance with community blocklists, the LAPI's answer to "all active
decisions" is several megabytes. CrowdPanel therefore holds it for 15 seconds and
shares it between Overview and Decisions; every change drops the cache at once, so
a lifted ban disappears without delay. On a tab switch the browser first paints the
data it already has and reloads afterwards — which is why switching feels instant
even though the fresh numbers arrive a moment later.

---

## Security

- Through Ingress, Home Assistant signs you in; on the direct port CrowdPanel does
  it itself. Both routes grant the same rights — whoever reaches the interface may
  ban and unban.
- State-changing requests need a signed CSRF marker and a matching sender. No
  foreign page in the browser can lift a ban.
- Passwords and the machine password appear in no log line and in no answer from
  the interface.
- Every input is validated before it reaches the LAPI: addresses and ranges through
  `ipaddress`, country codes and network numbers through fixed patterns, durations
  through the Go time format. Anything invalid is rejected with an error and never
  passed on.
- The add-on calls no external service and runs no programs.
