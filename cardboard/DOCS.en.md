# CardBoard – Documentation

## Overview

CardBoard renders Jinja2 templates directly via the HA Template API and displays the results as Markdown cards in the browser. Multiple users can use their own views simultaneously.

---

## Add-on Options

| Option | Description | Default |
|---|---|---|
| `ha_token` | HA Long-Lived Access Token | – |
| `ha_url` | URL of the HA instance | `http://homeassistant.local:8123` |
| `refresh_interval` | Auto-refresh interval in seconds | `30` |
| `login_message` | Personal greeting on the login page (optional) | – |
| `uptime_sensor` | Entity ID of the HA uptime sensor (optional) | `sensor.uptime` |

The uptime sensor is used for the "online since" indicator on the login and view pages. It requires the **Uptime integration** to be set up: <https://www.home-assistant.io/integrations/uptime/>  
If no value is available (sensor missing or `unavailable`), the indicator is simply omitted.

Create a Long-Lived Access Token in HA under:  
**Profile → Security → Long-lived access tokens → Create token**

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

- `username` is compared case-insensitively (capitalization does not matter at login)
- `display_name` (optional) – shown as greeting ("Hello …"). If omitted, `username` is used
- `lang` (optional) – display language: `de` (default) or `en`. Affects all UI text and time format
- `password` – plaintext or SHA-256 hash (64 hex characters). A hash is recommended for external access
- `templates` determines the number of cards (max. 3); order = display order in the browser
- Template files are located in the subfolder named after the username

---

## Hashing Passwords

Instead of a plaintext password, a SHA-256 hash can be stored in `users.yaml`. The hash is 64 hex characters long and replaces the plaintext password directly.

**Linux / macOS (Terminal):**
```sh
echo -n "MyPassword" | sha256sum
```

**macOS alternative:**
```sh
echo -n "MyPassword" | shasum -a 256
```

**Windows (PowerShell):**
```powershell
[System.BitConverter]::ToString(
  [System.Security.Cryptography.SHA256]::Create().ComputeHash(
    [System.Text.Encoding]::UTF8.GetBytes("MyPassword")
  )
).Replace("-","").ToLower()
```

**Home Assistant Terminal Add-on:**
```sh
echo -n "MyPassword" | sha256sum
```

The result (only the 64 hex characters, without the trailing ` -`) is entered as the `password` value:

```yaml
users:
  - username: user1
    password: a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3
```

> **Important:** Use `echo -n` — without `-n` a newline is included in the hash and the result will be incorrect.

---

## Template Files (.j2)

Templates use the full HA Jinja2 syntax. All functions available in the HA Markdown card work here too:

```jinja2
{%- set temp = states('sensor.living_room_temperature') | float(0) -%}
{%- set rain = states('binary_sensor.rain_detected') -%}

## Living Room

Temperature: **{{ temp | round(1) }}°C**
Rain: {% if rain == 'on' %}🌧️ Yes{% else %}☀️ No{% endif %}
```

### Note on Alignment

For space-aligned text (as commonly used in HA Markdown cards), content is displayed in a monospace font and spaces are preserved. Standard Markdown syntax like `**bold**`, `## Heading`, or tables is also rendered.

---

## Admin API

The Admin API runs on a separate port (default: **17773**) and is accessible exclusively from the local network. Requests from public IPs are rejected with `403 Forbidden`.

Accepted IP ranges:

| Range | Description |
|---|---|
| `10.0.0.0/8` | Private IPv4 (RFC-1918) |
| `172.16.0.0/12` | Private IPv4 (RFC-1918) |
| `192.168.0.0/16` | Private IPv4 (RFC-1918) |
| `127.0.0.0/8` | Loopback IPv4 |
| `::1` | Loopback IPv6 |
| `169.254.0.0/16` | Link-Local IPv4 |
| `fe80::/10` | Link-Local IPv6 |

> **nginx**: Do **not** include port 17773 in the nginx configuration — only proxy port 17772.

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

Query parameters:

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

```json
{
  "total": 4,
  "limit": 100,
  "offset": 0,
  "events": [
    { "timestamp": "2025-05-28T14:22:01", "username": "user1", "success": false, "ip": "192.168.1.42" }
  ]
}
```

#### `GET /api/admin/health`
Checks the connection to the HA API.

```json
{ "status": "ok", "ha_api": { "reachable": true, "message": "ok" } }
```

---

## Integrating the Admin API in Home Assistant

The Admin API can be integrated directly as an HA sensor to display login statistics on the dashboard or to receive notifications on suspicious logins.

Since HA and CardBoard run on the same host, the Admin API is accessible internally via `http://localhost:17773`.

### REST Sensors (`configuration.yaml`)

```yaml
sensor:
  - platform: rest
    name: "CardBoard Total Logins"
    unique_id: cardboard_total_logins
    resource: http://localhost:17773/api/admin/stats
    value_template: "{{ value_json.total_logins }}"
    scan_interval: 300
    icon: mdi:account-key

  - platform: rest
    name: "CardBoard Successful Logins"
    unique_id: cardboard_successful_logins
    resource: http://localhost:17773/api/admin/stats
    value_template: "{{ value_json.successful_logins }}"
    scan_interval: 300
    icon: mdi:account-check

  - platform: rest
    name: "CardBoard Failed Logins"
    unique_id: cardboard_failed_logins
    resource: http://localhost:17773/api/admin/stats
    value_template: "{{ value_json.failed_logins }}"
    scan_interval: 300
    icon: mdi:account-alert

  - platform: rest
    name: "CardBoard Failed Logins 24h"
    unique_id: cardboard_failed_logins_24h
    resource: http://localhost:17773/api/admin/stats
    value_template: "{{ value_json.last_24h.failed }}"
    scan_interval: 300
    icon: mdi:account-alert-outline

  - platform: rest
    name: "CardBoard HA API Status"
    unique_id: cardboard_ha_api_status
    resource: http://localhost:17773/api/admin/health
    value_template: "{{ value_json.status }}"
    scan_interval: 60
    icon: mdi:api
```

### Template Sensor for Last Failed Login

This sensor shows the timestamp and IP address of the last failed login attempt:

```yaml
sensor:
  - platform: rest
    name: "CardBoard Last Failed Login"
    unique_id: cardboard_last_failed_login
    resource: "http://localhost:17773/api/admin/logins?status=failed&limit=1"
    value_template: >
      {% if value_json.events | length > 0 %}
        {{ value_json.events[0].timestamp }} ({{ value_json.events[0].ip }})
      {% else %}
        None
      {% endif %}
    scan_interval: 300
    icon: mdi:shield-alert
```

### Automation: Notification on Failed Login

```yaml
automation:
  - alias: "CardBoard Login Failed Attempt"
    description: "Notification when someone enters incorrect credentials"
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

## Login

- The web interface is accessible at `http://<HA-IP>:17772`
- After a successful login, a cookie session is stored for 7 days
- Users can only view their dashboard, not change any configuration
