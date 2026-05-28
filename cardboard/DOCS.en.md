# CardBoard – Documentation

## Overview

CardBoard renders Jinja2 templates directly via the HA Template API and displays the results as Markdown cards in the browser. Multiple users can use their own views simultaneously. Users and templates are managed via the built-in Admin Panel.

---

## Add-on Options

| Option | Description | Default |
|---|---|---|
| `ha_token` | HA Long-Lived Access Token | – |
| `ha_url` | URL of the HA instance | `http://homeassistant.local:8123` |
| `refresh_interval` | Auto-refresh interval in seconds | `30` |
| `login_message` | Personal greeting on the login page (optional) | – |
| `uptime_sensor` | Entity ID of the HA uptime sensor (optional) | `sensor.uptime` |
| `session_lifetime` | Login cookie lifetime in days (optional) | `7` |
| `notify_failed_login` | Send a persistent HA notification on failed login (optional) | `true` |
| `pw_min_length` | Minimum length for new passwords (optional) | `8` |
| `pw_require_special` | Password must contain at least one number or special character (optional) | `true` |
| `admin_password` | Password for the Admin Panel (optional). If empty, the Admin Panel is accessible without login from the LAN | – |
| `max_cards` | Maximum number of cards shown per user (optional) | `3` |

Create a Long-Lived Access Token in HA under:  
**Profile → Security → Long-lived access tokens → Create token**

The uptime sensor is used for the "online since" indicator. It requires the **Uptime integration**: <https://www.home-assistant.io/integrations/uptime/>

---

## Admin Panel

The Admin Panel is the central management interface for users and templates — no manual file editing required.

### Access

| Method | URL |
|---|---|
| HA Sidebar (Ingress) | Via the CardBoard entry in the HA sidebar |
| Direct (LAN) | `http://<HA-IP>:17773/admin/` |

If `admin_password` is set, a login page appears on first access. The admin session is valid for 4 hours.  
If no password is set, the Admin Panel is accessible without login from the local network.

> **nginx**: Do **not** include port 17773 or port 17774 (Ingress) in nginx — only proxy port 17772.

### User Management

| Function | Description |
|---|---|
| **Create user** | Username, display name, language, initial password. The user directory is created automatically. `force_pw_change` is set — the user must change their password on first login. |
| **Edit user** | Change display name, language and the `force_pw_change` flag. |
| **Reset password** | Set a new password; `force_pw_change` is automatically enabled. |
| **Delete user** | Removes the entry from `users.yaml`. The template directory is preserved. |
| **Login history** | The 📊 button per user shows the last 50 login events (timestamp, result, IP). |

### Template Editor

The template editor is accessible via the 📝 button in the user table.

| Function | Description |
|---|---|
| **Create templates** | Enter filename (`.j2`), optional title and content directly in the browser. |
| **Edit templates** | Click a template in the list to open it in the editor. |
| **Reorder** | ↑/↓ buttons control the display order of the cards. |
| **Live preview** | The 👁 button renders the template via the HA API and shows the card in real time. |
| **Save** | Button or **Ctrl+S** (Cmd+S on Mac). |
| **Delete template** | 🗑 button per template, with confirmation dialog. |

> If more than `max_cards` templates exist, a warning appears — only the first `max_cards` templates are shown in the view.

### Blocked IPs (Rate Limiting)

The lower section of the Admin Panel shows a list of currently blocked IPs. An IP is blocked for 15 minutes after 5 failed login attempts within 10 minutes.

- Local/private IPs (LAN) are **exempt** from blocking
- Blocked IPs can be manually unblocked with the **Unblock** button

---

## Configuration Structure

All user configurations are stored under `/config/addons_config/cardboard/`:

```
/config/addons_config/cardboard/
├── users.yaml
├── user1/
│   ├── solar.j2
│   ├── temps.j2
│   └── grid.j2
└── user2/
    └── overview.j2
```

---

## users.yaml

`users.yaml` is normally managed via the Admin Panel. For manual editing:

```yaml
users:
  - username: user1
    password: secret123
    display_name: John Doe
    lang: en
    templates:
      - file: solar.j2
        title: Solar
      - file: temps.j2
        title: Temperatures
      - file: grid.j2
        title: Grid Usage
  - username: user2
    password: another_password
    display_name: Jane Doe
    lang: en
    templates:
      - overview.j2        # Short form without title is also valid
```

- `username` is compared case-insensitively
- `display_name` (optional) – shown as greeting. If omitted, `username` is used
- `lang` (optional) – display language: `de` (default) or `en`
- `password` – plaintext or SHA-256 hash (64 hex characters)
- `templates` – order = display order; max. `max_cards` cards are shown
- `force_pw_change: true` – user is forced to change password on next login

---

## Hashing Passwords

Instead of a plaintext password, a SHA-256 hash can be stored in `users.yaml`.

**Linux / macOS:**
```sh
echo -n "MyPassword" | sha256sum
```

**Windows (PowerShell):**
```powershell
[System.BitConverter]::ToString(
  [System.Security.Cryptography.SHA256]::Create().ComputeHash(
    [System.Text.Encoding]::UTF8.GetBytes("MyPassword")
  )
).Replace("-","").ToLower()
```

> **Important:** Use `echo -n` — without `-n` a newline is included in the hash and the result will be incorrect.

---

## Template Files (.j2)

Templates use the full HA Jinja2 syntax:

```jinja2
{%- set temp = states('sensor.living_room_temperature') | float(0) -%}
{%- set rain = states('binary_sensor.rain_detected') -%}

## Living Room

Temperature: **{{ temp | round(1) }}°C**
Rain: {% if rain == 'on' %}🌧️ Yes{% else %}☀️ No{% endif %}
```

Content is displayed in a monospace font with whitespace alignment preserved. Standard Markdown syntax like `**bold**`, `## Heading`, or tables is fully rendered.

---

## PWA – Install as App

CardBoard supports installation as a Progressive Web App (PWA).

| Device | Requirement | How to install |
|---|---|---|
| **iPhone / iPad** | any browser | Safari: Share (📤) → "Add to Home Screen" |
| **Android** | HTTPS | Chrome: Menu → "Add to Home Screen" or automatic banner |
| **Desktop** | HTTPS | Chrome/Edge: Install icon in the address bar |

After installation, CardBoard opens as a standalone app without browser chrome. The status bar follows the selected Dark/Light theme.

> HTTPS is required for Android/Desktop (e.g. via nginx with Let's Encrypt).

---

## Admin API

The Admin API runs on port **17773** and is accessible from the local network only.

### Endpoints

#### `GET /api/admin/stats`
Overall statistics of all login events.

```json
{
  "total_logins": 42,
  "successful_logins": 38,
  "failed_logins": 4,
  "last_24h": { "successful": 5, "failed": 1 }
}
```

#### `GET /api/admin/logins`
Login events, newest first.

| Parameter | Values | Default |
|---|---|---|
| `status` | `all` / `success` / `failed` | `all` |
| `username` | Username (optional) | – |
| `limit` | 1–500 | `100` |
| `offset` | Number | `0` |

```sh
curl http://<HA-IP>:17773/api/admin/logins?status=failed
curl http://<HA-IP>:17773/api/admin/logins?username=user1&limit=20
```

#### `GET /api/admin/health`
Checks the connection to the HA API.

```json
{ "status": "ok", "ha_api": { "reachable": true, "message": "ok" } }
```

---

## Integrating the Admin API in Home Assistant

Since HA and CardBoard run on the same physical host but in separate Docker containers, `localhost` does not work — use the HA hostname with port 17773:

```
http://homeassistant.local:17773
```

### REST Sensors (`configuration.yaml`)

```yaml
sensor:
  - platform: rest
    name: "CardBoard Total Logins"
    unique_id: cardboard_total_logins
    resource: http://homeassistant.local:17773/api/admin/stats
    value_template: "{{ value_json.total_logins }}"
    scan_interval: 300
    icon: mdi:account-key

  - platform: rest
    name: "CardBoard Failed Logins 24h"
    unique_id: cardboard_failed_logins_24h
    resource: http://homeassistant.local:17773/api/admin/stats
    value_template: "{{ value_json.last_24h.failed }}"
    scan_interval: 300
    icon: mdi:account-alert-outline

  - platform: rest
    name: "CardBoard Last Successful Login"
    unique_id: cardboard_last_successful_login
    resource: "http://homeassistant.local:17773/api/admin/logins?status=success&limit=1"
    value_template: >
      {% if value_json.events | length > 0 %}
        {{ value_json.events[0].username }} — {{ value_json.events[0].timestamp[:16].replace('T',' ') }} ({{ value_json.events[0].ip }})
      {% else %}-{% endif %}
    scan_interval: 300
    icon: mdi:account-check

  - platform: rest
    name: "CardBoard Last Failed Login"
    unique_id: cardboard_last_failed_login
    resource: "http://homeassistant.local:17773/api/admin/logins?status=failed&limit=1"
    value_template: >
      {% if value_json.events | length > 0 %}
        {{ value_json.events[0].username }} — {{ value_json.events[0].timestamp[:16].replace('T',' ') }} ({{ value_json.events[0].ip }})
      {% else %}-{% endif %}
    scan_interval: 300
    icon: mdi:shield-alert

  - platform: rest
    name: "CardBoard HA API Status"
    unique_id: cardboard_ha_api_status
    resource: http://homeassistant.local:17773/api/admin/health
    value_template: "{{ value_json.status }}"
    scan_interval: 60
    icon: mdi:api
```

### Automation: Notification on Failed Login

```yaml
automation:
  - alias: "CardBoard Login Failed Attempt"
    triggers:
      - trigger: state
        entity_id: sensor.cardboard_failed_logins_24h
    conditions:
      - condition: template
        value_template: >
          {{ trigger.to_state.state | int(0) > trigger.from_state.state | int(0) }}
    actions:
      - action: notify.notify
        data:
          title: "⚠️ CardBoard Login Failed"
          message: >
            Failed login attempt on CardBoard.
            Failed attempts last 24h: {{ states('sensor.cardboard_failed_logins_24h') }}
```

### Automation: Alert on HA API Outage

```yaml
automation:
  - alias: "CardBoard HA API Unreachable"
    triggers:
      - trigger: state
        entity_id: sensor.cardboard_ha_api_status
        to: "degraded"
        for:
          minutes: 2
    actions:
      - action: notify.notify
        data:
          title: "🔴 CardBoard: HA API Unreachable"
          message: "CardBoard cannot reach the Home Assistant API."
```

> **Note:** After adding entries to `configuration.yaml`, HA must be reloaded:  
> **Developer Tools → YAML → Check & Reload All YAML Configuration**

---

## nginx as Reverse Proxy

CardBoard itself only speaks HTTP. For external access, place nginx in front as an HTTPS reverse proxy. Port **17773** (Admin API) must **not** be proxied.

### Important Headers

| Header | Purpose |
|---|---|
| `X-Forwarded-For` | Real client IP (for login log and notifications) |
| `X-Forwarded-Proto` | Sets the `Secure` flag on the session cookie when using HTTPS |

### Example Configuration

```nginx
server {
    listen 80;
    server_name cardboard.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name cardboard.example.com;

    ssl_certificate     /etc/letsencrypt/live/cardboard.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cardboard.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location / {
        proxy_pass         http://localhost:17772;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

> Do **not** include port `17773` (Admin API) in nginx.  
> SSL certificates can be obtained for free using [Let's Encrypt](https://letsencrypt.org/) and Certbot.

---

## Login

- Web interface: `http://<HA-IP>:17772` (internal) or nginx URL (external)
- After successful login: cookie session (configurable, default: 7 days)
- The session cookie automatically receives the `Secure` flag when HTTPS is detected
- When the session expires: automatic redirect to the login page with an info message
- Users can only view their dashboard, not change any configuration
