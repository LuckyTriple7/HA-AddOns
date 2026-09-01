# Running MyPage without Home Assistant (standalone)

At its core, MyPage is a plain Flask app in a standard Docker image — Home Assistant is just the convenient wrapper, not a requirement. You can run MyPage on any server with **Docker**.

> The prebuilt image is at `ghcr.io/luckytriple7/mypage:latest` (amd64 + aarch64). You don't need the source code — just Docker and a `docker-compose.yml`.

---

## Quick start

```bash
# 1. Start — nothing to prepare
docker compose up -d

# 2. Read the generated admin password from the log
docker compose logs mypage | grep -A 3 "Neue Installation"

# 3. Open
#   Public site:  http://<server>:17760
#   Admin panel:  http://<server>:17761   (user "admin", password from step 2)
```

On first start MyPage creates its data in the `./data` folder (`site.json`, `uploads/`, members, game states …) and generates a random admin password (16 characters, upper and lower case plus digits). It appears **only in the log** — the disk holds nothing but a hash in `./data/admin_login.json`. Write it down and set your own in the admin panel right away.

---

## Several instances on one server (Dockge)

MyPage has no instance limit: any number of containers can run side by side on one server, as long as each gets its **own host ports** and its **own data folder**. In [Dockge](https://github.com/louislam/dockge) that means **one stack per instance**. Each stack has its own folder under `/opt/docker/stacks/`, and `./data` resolves there automatically — nothing to name or separate by hand.

```
/opt/docker/stacks/
├── mypagea/       compose.yaml  data
└── mypageb/       compose.yaml  data
```

`/opt/docker/stacks/mypagea/compose.yaml`:

```yaml
services:
  mypage:
    image: ghcr.io/luckytriple7/mypage:latest
    container_name: mypagea
    ports:
      - "17760:17760"        # public site
      - "17761:17761"        # admin panel
    volumes:
      - ./data:/config
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:17760/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

`/opt/docker/stacks/mypageb/compose.yaml` — the same file, three lines different:

```yaml
    container_name: mypageb
    ports:
      - "17770:17760"
      - "17771:17761"
```

Ports **17760** and **17761** on the right of the colon are hard-wired inside the container and stay the same in every instance; only the left, server-wide unique side has to differ.

After *Deploy*, pick up the generated password from the stack's log tab (user `admin`), sign in and set your own under **System → Access** — a different one per instance. There is no shared login across containers.

Then set the matching address in each instance under **Design → Public URL**. Without it MyPage guesses `http://<host>:17760`, which is wrong for every instance but the first, affecting preview, sitemap, RSS, PWA and mail links.

**Things to watch:**

- **Never point two containers at the same data folder.** `site.json`, the visitor counter, game states and sessions would overwrite each other.
- **SMB storage** needs `cap_add: [SYS_ADMIN, DAC_READ_SEARCH]` and `security_opt: [apparmor:unconfined]` per container. Two instances must not use the same subfolder of the share — give each its own *subdirectory* in the settings.
- **Brute-force protection counts per container**, not server-wide. Behind a reverse proxy, set `trusted_proxies` in every instance (see below), otherwise MyPage only ever sees the proxy address and one attack locks out all visitors at once.
- **Memory**: roughly 200–400 MB per instance. Worth counting on a small VPS.

---

## Configuration

### Admin access — changing the password

In the admin panel under **System → Access**: enter the current password (plus the code if 2FA is on), then set user name and new password. At least **12 characters with an upper-case letter, a lower-case letter and a digit**. Changing it ends every other admin session; your own stays.

Stored in `./data/admin_login.json` as a hash only. The file is **not** part of the backup ZIP — restoring last week's backup would otherwise silently bring the old password back.

### Forgotten password

```bash
cd /opt/docker/stacks/mypagea      # folder of the stack / compose file
rm ./data/admin_login.json
docker compose restart
docker compose logs | grep -A 3 "Neue Installation"
```

The password also shows up in the stack's log tab in Dockge. With several instances this only affects the one whose folder you deleted in; the others stay as they are.

MyPage then generates a new password and writes it to the log. Content, members and settings are untouched. **2FA stays on** — deleting the file is deliberately not a full bypass for anyone with file access. If the second factor is lost too, also delete `./data/admin_2fa.json`.

> If the "Neue Installation" message shows up unexpectedly, the volume path is usually wrong and MyPage started on an empty folder. Check the mount before adding content.

### Storage limit (compose.yaml only)

By default MyPage may use as much space as the disk offers. Set an overall limit in the compose.yaml:

```yaml
    environment:
      MYPAGE_STORAGE_MAX_MB: 2048     # 0 or omitted = unlimited
```

Everything in the data folder counts: images, library PDFs, logos, member files, attachments, game states and the automatic backups. Member files on an SMB share sit outside the folder and do not count.

Once the limit is reached, **new uploads are rejected** — browsing, deleting and cleaning up keep working so you can make room again. Instead of writing a new automatic backup, the existing ones are thinned out. Members see the smaller of their personal quota and the remaining overall space.

The limit is deliberately **not in the admin panel**: a limit the content admin can raise is no limit. The panel only shows usage under **System → Storage usage** — a bar, the total and a breakdown by area (images, PDFs, member files, backups …) so you can see what is eating the space. With several instances, set a value per stack.

### `options.json` — optional

No longer needed for the login. If you do mount it (read-only to `/data/options.json`), it can still carry two things:

| Key | Meaning | Default |
|---|---|---|
| `session_hours` | Admin session lifetime in hours | `24` |
| `trusted_proxies` | Addresses whose forwarding headers are trusted | all private networks |

Upgrading from an older version that had `username`/`password` there: on the first start after the update MyPage imports them into `admin_login.json` as a hash, so your login keeps working. Afterwards both entries have no effect and the file can go.

### Everything else: admin panel → **Settings**

Mail delivery, Telegram, GitHub token, AI keys, SMB storage, visitor counter and backup retention live on the **Settings** tab of the admin panel — no editor, no restart.

They are stored in `./data/settings.json`. Tokens and passwords are **encrypted** with `./data/settings.key`, never shown in the browser (only “set”/“not set”), and logged by field name only.

* An empty secret field means **“leave unchanged”** — use the **Delete** button to remove one.
* **Download key** (on the *Settings* tab) exports `settings.key` wrapped with a passphrase — the only way to bring credentials back on a fresh installation. MyPage asks for the admin password again first.
* Almost everything applies immediately. Only the **SMB fields** need a `docker compose restart` if no share was configured at start (the UI tells you).
* Upgrading from an older version: on first start MyPage imports the existing values from `options.json` into `settings.json`, encrypting them on the way. The old entries in `options.json` then have no effect and can be removed.

---

## HTTPS (recommended for production)

Without HA ingress, the **admin login is the only protection layer** — so it must **never run over unencrypted HTTP**. Put a reverse proxy with automatic Let's Encrypt certificates in front, e.g. **Caddy**.

`docker-compose.yml` (with Caddy, ports no longer exposed directly):

```yaml
services:
  mypage:
    image: ghcr.io/luckytriple7/mypage:latest
    container_name: mypage
    expose:
      - "17760"
      - "17761"
    volumes:
      - ./data:/config
    restart: unless-stopped

  caddy:
    image: caddy:2
    container_name: caddy
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
    restart: unless-stopped

volumes:
  caddy_data:
```

Matching `Caddyfile` (public site on the main domain, admin on a subdomain):

```caddyfile
your-domain.com {
    reverse_proxy mypage:17760
}

admin.your-domain.com {
    reverse_proxy mypage:17761
}
```

Caddy fetches the certificates automatically. Point both DNS records to your server's IP. Afterwards set **Design → Public URL** in the admin panel to `https://your-domain.com` so sitemap, RSS and share links produce correct addresses.

> A **Cloudflare Tunnel** works too (see README) — then you don't need any open ports.

---

## What's missing without Home Assistant

These three things are HA-specific and go away — **everything else works unchanged**:

- **HA sensors** (`sensor.mypage_*` with visitor count, pending requests …)
- **HA notifications** in the HA dashboard
- **Ingress** (single sign-on via the HA menu) → the built-in username/password login is used instead

Still fully usable: public site with all content blocks, blog, custom pages, forms, member area, games, **e-mail and Telegram notifications**, SMB storage, backup/restore, SEO/sitemap/redirects, share buttons.

---

## Updates

```bash
docker compose pull
docker compose up -d
```

Your data in `./data` is preserved.

---

## Backup

Two ways, ideally combined:

1. **In the admin panel** under *System → Backup*, download a ZIP with all content (and restore it via *Restore backup*). The ZIP contains `settings.json` but **not** the key `settings.key`, so credentials cannot be read from it. Restoring onto a fresh installation means entering them once again.
2. Back up the **`./data`** folder (additionally contains uploads, member files, `settings.key` and `admin_login.json`) — keep that folder somewhere safe.

---

## Security notes

- **Replace the initial password**: it sits in the container log, and logs get forwarded, collected and archived. Set your own under *System → Access* — without ingress, only this login protects the admin panel.
- **`data/admin_login.json` lives in the data folder** so you can lock yourself out over SSH *and* back in. Anyone with file access to the server can therefore reset the login — on a rented server that means trusting the provider or using an encrypted filesystem.
- `./data/settings.key` decrypts every stored credential: never share it or commit it to a public repository.
- Make the admin panel reachable **over HTTPS only** (Caddy/Cloudflare Tunnel).
- Brute-force protection (rate limit + temporary lockout) is built in; still, don't expose the admin panel publicly without need — ideally put it on a subdomain or add an extra layer (firewall/basic auth).
