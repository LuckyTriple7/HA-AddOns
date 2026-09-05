# Anubis

🇩🇪 [Deutsche Version](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/DOCS.md)

[Anubis](https://github.com/TecharoHQ/anubis) hands visitors a proof-of-work computation before a request reaches the actual service. A normal browser solves it unnoticed via JavaScript in the background; simple bots, scanners and CLI clients without JavaScript don't get through. Meant as an extra protection layer **in front of** a reverse proxy — it doesn't replace a login, it just raises the cost of automated access.

```text
Internet
   ↓
Reverse proxy (e.g. NPMplus)
   ↓
Anubis challenge (proof of work)
   ↓
actual application
```

This add-on is a bare engine with no UI of its own and no Ingress — it's meant to be addressed only internally by a reverse proxy that supports `auth_request`/forward-auth. Simplest in combination with this repo's [NPMplus add-on](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/DOCS.en.md), which already knows Anubis as a built-in auth-request provider.

## Why a custom policy instead of Anubis' default one

Anubis' bundled default policy pulls in additional snippets (`(data)/common/domain-fronting.yaml`, `(data)/bots/...` etc.) that only exist embedded in the original image. A single mounted policy file without those imports fails with:

```text
invalid source file: (data)/common/domain-fronting.yaml
```

This add-on therefore ships a **self-contained, import-free policy** (`policy.default.yaml`), copied to `/data/policy.yaml` on first start. It deliberately has **no implicit ALLOW branch**: any client not matched by an earlier rule falls into a catch-all rule and gets challenged too — including curl, wget, scanners and unknown clients that would otherwise slip through a default allow with `weight <= 0`.

## Search engines (Google, Bing & co.)

The catch-all rule challenges real search engine crawlers too — they don't solve JavaScript proof-of-work. Without an exemption, an activated domain slowly vanishes from search results, because Google & co. can no longer get through on re-crawl.

The `allow_search_engines` option (default **on**) therefore exempts real search engine, web archive and citation crawlers via an `ALLOW` rule — always checking user agent **and** the respective official IP address together (`remote_addresses`); a bare user-agent string alone could be spoofed by anyone. Turn it off (`false`) if truly every client should be challenged, search engines included — for example for a purely private service that shouldn't show up in any search at all.

Included: **Google** (including Search Console's "Live Test" / Google-InspectionTool), **Bing**, **DuckDuckGo**, **Qwant**, **Internet Archive**, **Kagi**, **Marginalia**, **Mojeek**, **Common Crawl**, **Wikimedia** (Citoid/Zotero Translation Server) and **Arquivo.pt**. Deliberately **not** included: **Yandex**.

The rules live between two markers in `/data/policy.yaml`:

```yaml
bots:
  # >>> anubis-addon search-engines >>>
  # <<< anubis-addon search-engines <<<
```

The add-on rewrites **only this block** on every start, matching the current `allow_search_engines` setting — any rules you add there get lost on the next restart. Everything outside the markers (e.g. your own rules below the `catch-all` rule) stays untouched, same as the rest of the file.

Deliberately **no** `(data)/crawlers/_allow-good.yaml` import for this exemption: exactly this kind of import once failed in practice with `invalid source file: (data)/common/domain-fronting.yaml`. The Google/Bing rules therefore live literally in `policy.search-engines.yaml` inside the image, copied from Anubis' own official sources.

Other crawlers (e.g. Yandex) can be added the same way **below** the markers in `/data/policy.yaml` (outside the managed block, otherwise they'd be lost on the next start) — the matching rule is ready-made at `https://github.com/TecharoHQ/anubis/blob/main/data/crawlers/<name>.yaml`.

**Limits:** Providers occasionally republish their crawler IP ranges. If a range changes before the list here is refreshed, that part would briefly get challenged again — no data loss, just a temporarily uncrawled slice.

## Setting it up with NPMplus

1. Install and start the Anubis add-on.
2. Find the Anubis container's hostname (in a Terminal add-on with Docker access):

   ```sh
   docker inspect -f '{{.Config.Hostname}}' $(docker ps --format '{{.Names}}' | grep -i anubis)
   ```

   The result looks like `424ccef4-anubis`. The prefix identifies the add-on repository and differs per installation — read your own value, don't copy this one. Entering a container IP (`172.30.33.x`) here would be a mistake: Docker reassigns it on every restart, the hostname stays the same.

3. In the NPMplus add-on options, add under `extra_env`:

   ```yaml
   extra_env:
     - "AUTH_REQUEST_ANUBIS_UPSTREAM=http://424ccef4-anubis:8923"
   ```

4. Restart NPMplus.
5. On the desired Proxy Host: "Details" tab → **Auth Request** field → select `anubis` → Save.

   No extra Advanced nginx rules or custom locations needed — the integration is already built into NPMplus. Test with a less critical domain first.

The same principle works with other reverse proxies, as long as they support `auth_request` (nginx) or a comparable forward-auth feature — Anubis then needs to be wired up by hand as the auth backend at `http://<anubis-hostname>:8923/.within.website/x/cmd/anubis/api/check`.

## Testing the auth request by hand

```sh
curl -s -o /dev/null -w '%{http_code}\n' \
  -A 'Mozilla/5.0' \
  -H 'Host: test.example' \
  -H 'X-Real-IP: 127.0.0.1' \
  -H 'X-Forwarded-For: 127.0.0.1' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: test.example' \
  -H 'X-Original-URI: /' \
  -H 'X-Http-Version: HTTP/1.1' \
  http://424ccef4-anubis:8923/.within.website/x/cmd/anubis/api/check
```

Expected output: `401` — meaning "challenge required", which is correct with the bundled catch-all policy, even for this bare test call.

## Forcing the challenge again

Once a challenge is solved, Anubis sets a cookie (its name starts roughly with `techaro.lol-anubis-auth-`). The check then doesn't show up on every page load.

- **Easiest test**: open the protected domain in a private/incognito window.
- **Alternative**: delete the cookie in the browser (F12 → Application/Storage → Cookies → the domain in question) and reload.

## Customizing the policy

`/data/policy.yaml` is freely editable after the first start — the add-on never overwrites it again. Restart the add-on after every change.

Temporarily raise the difficulty to make the proof-of-work computation visible:

```yaml
challenge:
  algorithm: fast
  difficulty: 5
```

Don't leave it high permanently — legitimate visitors then need noticeably more compute time too. For everyday use, go back to `difficulty: 2` (the bundled default) or lower.

Valid values for `algorithm`: `fast` (quick JavaScript computation), `slow` (deliberately more expensive) and `metarefresh` (a page refresh instead of proof of work, no real compute cost).

## What a bot experiences

```text
Visitor
   ↓
Anubis generates a computation task
   ↓
Browser runs JavaScript
   ↓
Proof of work gets computed
   ↓
Solution gets verified
   ↓
correct → auth cookie → access
```

A simple bot without JavaScript usually can't solve the challenge. A modern bot automating a full browser like Chromium can, in principle, compute proof of work too — Anubis is therefore not a classic "prove you're human" check, it mainly raises the cost and effort of automated access.

## Monitoring tools like Uptime Kuma

Uptime Kuma, Healthchecks and similar monitors usually can't solve a JavaScript/proof-of-work challenge and get challenged too under the bundled catch-all policy. An HTTP monitor pointed at a domain protected by Anubis then shows, at best, that the **reverse proxy + Anubis** are answering — not that the application behind it works.

For full monitoring, add a separate internal monitor pointed directly at the service, bypassing Anubis:

```text
External: https://service.domain.tld       → reverse proxy + Anubis
Internal: http://<internal-address>:port   → the service itself
```

There's deliberately no built-in bypass for monitoring tools — that would weaken the catch-all rule. To exempt specific clients, add your own rule with `action: ALLOW` and a matching `user_agent_regex` above the catch-all rule in `/data/policy.yaml`.

## Data and backup

| What | Path |
|---|---|
| Policy (editable) | `/data/policy.yaml` |

A Home Assistant backup of the add-on includes `/data` in full. Since the policy holds no secrets, a copy under `/share` is harmless too.

## Troubleshooting

**`invalid source file: (data)/...` in the log** — a policy with external imports was entered (e.g. copied from Anubis' own docs). Go back to the self-contained policy from `policy.default.yaml` or remove your own imports.

**Auth request returns 500 instead of 401/403** — usually missing headers. A bare `curl http://<anubis-hostname>:8923` without the headers listed under "Testing the auth request by hand" is not a complete auth request and therefore returns no meaningful code.

**Anubis page never appears, the proxy host serves straight through** — check `AUTH_REQUEST_ANUBIS_UPSTREAM` under `extra_env` (correct hostname? was NPMplus restarted afterwards?) and whether the Proxy Host's "Auth Request" field is actually set to `anubis`.

**Monitoring tool shows red** — see "Monitoring tools like Uptime Kuma": expected for a domain protected by auth request, not a bug in the add-on.

## License

Anubis is licensed under the [MIT License](https://github.com/TecharoHQ/anubis/blob/main/LICENSE). This add-on only copies the static binary from the official image; details in [LICENSE.md](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/LICENSE.md).
