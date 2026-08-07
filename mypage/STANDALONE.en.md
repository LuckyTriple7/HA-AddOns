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

## Configuration (`options.json`)

The file is mounted to `/data/options.json` in the container (read-only) and read at startup. All fields are optional except a **strong password**.

| Key | Meaning | Default |
|---|---|---|
| `username` | Admin username | `admin` |
| `password` | **Admin password — be sure to set it!** | _(empty)_ |
| `session_hours` | Admin session lifetime in hours | `24` |
| `smtp_host` / `smtp_port` | Mail server for notifications, newsletter, member mails | – / `587` |
| `smtp_user` / `smtp_password` | Mail server credentials | – |
| `smtp_from` / `smtp_to` | Sender / recipient for contact notifications | – |
| `smtp_tls` | Use STARTTLS | `true` |
| `telegram_bot_token` / `telegram_chat_id` | Optional Telegram notification on new messages | – |
| `github_token` | Optional token for the GitHub project import (higher rate limit) | – |
| `translate_email` | E-mail for the free MyMemory translation quota | – |
| `user_upload_max_mb` | Max upload size per file (member area) | `200` |
| `visit_log_max` | Length of the visitor log | `500` |
| `geoip_lookup` / `geoip_api_key` | Country lookup in the stats (optional) | `false` |
| `smb_server` / `smb_share` / `smb_user` / `smb_password` | Optional SMB storage for member files | – |
| `gemini_api_key` | Google Gemini key — enables “Generate image” in the library editor (billed) | – |
| `gemini_image_model` | Model used for image generation | `gemini-3.1-flash-image` |
| `gemini_image_ratio` | Aspect ratio of generated images | `16:9` |

After changing `options.json`, restart the container: `docker compose restart`.

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

1. **In the admin panel** under *System → Backup*, download a ZIP with all content (and restore it via *Restore backup*).
2. Back up the **`./data`** folder (additionally contains uploads and member files).

---

## Security notes

- Set a **strong admin password** in `options.json` — without ingress, only this login protects the admin panel.
- Make the admin panel reachable **over HTTPS only** (Caddy/Cloudflare Tunnel).
- Brute-force protection (rate limit + temporary lockout) is built in; still, don't expose the admin panel publicly without need — ideally put it on a subdomain or add an extra layer (firewall/basic auth).
