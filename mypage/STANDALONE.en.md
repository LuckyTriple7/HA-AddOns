# Running MyPage without Home Assistant (standalone)

At its core, MyPage is a plain Flask app in a standard Docker image — Home Assistant is just the convenient wrapper, not a requirement. You can run MyPage on any server with **Docker**.

> The prebuilt image is at `ghcr.io/luckytriple7/mypage:latest` (amd64 + aarch64). You don't need the source code — just Docker, a `docker-compose.yml` and an `options.json`.

---

## Quick start

```bash
# 1. Copy the example config and change the password
cp options.example.json options.json
nano options.json          # set at least "password"!

# 2. Start
docker compose up -d

# 3. Open
#   Public site:  http://<server>:17760
#   Admin panel:  http://<server>:17761   (log in with username/password from options.json)
```

On first start MyPage creates its data in the `./data` folder (`site.json`, `uploads/`, members, game states …).

---

## Configuration

### `options.json` — login credentials only

The file is mounted read-only to `/data/options.json` in the container and read at start.

| Key | Meaning | Default |
|---|---|---|
| `username` | Admin user name | `admin` |
| `password` | **Admin password — set this!** | _(empty)_ |
| `session_hours` | Admin session lifetime in hours | `24` |

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
      - ./options.json:/data/options.json:ro
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
2. Back up the **`./data`** folder (additionally contains uploads, member files and `settings.key`) — keep that folder somewhere safe.

---

## Security notes

- Set a **strong admin password** in `options.json` — without ingress, only this login protects the admin panel.
- `./data/settings.key` decrypts every stored credential: never share it or commit it to a public repository.
- Make the admin panel reachable **over HTTPS only** (Caddy/Cloudflare Tunnel).
- Brute-force protection (rate limit + temporary lockout) is built in; still, don't expose the admin panel publicly without need — ideally put it on a subdomain or add an extra layer (firewall/basic auth).
