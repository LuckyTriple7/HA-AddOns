# CardBoard – Dokumentation

## Übersicht

CardBoard rendert Jinja2-Templates direkt über die HA-Template-API und stellt die Ergebnisse als Markdown-Karten im Browser dar. Mehrere Benutzer können gleichzeitig ihre eigenen Ansichten nutzen.

---

## Add-on Optionen

| Option | Beschreibung | Standard |
|---|---|---|
| `ha_token` | HA Long-Lived Access Token | – |
| `ha_url` | URL der HA-Instanz | `http://homeassistant.local:8123` |
| `refresh_interval` | Automatische Aktualisierung in Sekunden | `30` |
| `login_message` | Persönliche Begrüßung auf der Login-Seite (optional) | – |
| `uptime_sensor` | Entity-ID des HA-Uptime-Sensors (optional) | `sensor.uptime` |
| `session_lifetime` | Gültigkeit des Login-Cookies in Tagen (optional) | `7` |
| `notify_failed_login` | Persistente HA-Benachrichtigung bei fehlgeschlagenem Login (optional) | `true` |
| `pw_min_length` | Mindestlänge für neue Passwörter (optional) | `8` |
| `pw_require_special` | Passwort muss mindestens eine Zahl oder ein Sonderzeichen enthalten (optional) | `true` |

Der Uptime-Sensor wird für die „online seit"-Anzeige auf der Login- und View-Seite verwendet. Er muss über die **Uptime-Integration** eingerichtet sein: <https://www.home-assistant.io/integrations/uptime/>  
Wird kein Wert geliefert (Sensor nicht vorhanden oder `unavailable`), wird die Anzeige einfach weggelassen.

Den Long-Lived Access Token erstellst du in HA unter:  
**Profil → Sicherheit → Langlebige Zugangstoken → Token erstellen**

---

## Konfigurationsstruktur

Alle Benutzer-Konfigurationen liegen unter `/config/addons_config/cardboard/`:

```
/config/addons_config/cardboard/
├── users.yaml
├── user1/
│   ├── solar.j2
│   ├── temps.j2
│   └── netz.j2
└── user2/
    └── overview.j2
```

---

## users.yaml

```yaml
users:
  - username: user1
    password: geheim123
    display_name: Max Mustermann
    lang: de
    templates:
      - file: solar.j2
        title: Solar
      - file: temps.j2
        title: Temperaturen
      - file: netz.j2
        title: Netzverbrauch
  - username: user2
    password: anderes_passwort
    display_name: Jane Doe
    lang: en
    templates:
      - overview.j2        # Kurzform ohne Titel ist weiterhin gültig
```

- `username` wird kleingeschrieben verglichen (Groß-/Kleinschreibung egal beim Login)
- `display_name` (optional) – wird als Begrüßung angezeigt ("Hallo …"). Fehlt das Feld, wird der `username` verwendet
- `lang` (optional) – Anzeigesprache: `de` (Standard) oder `en`. Betrifft alle UI-Texte und das Zeitformat
- `password` – Klartext oder SHA-256-Hash (64 Hex-Zeichen). Für externen Zugriff wird ein Hash empfohlen
- `templates` bestimmt die Anzahl der Karten (max. 3); Reihenfolge = Reihenfolge im Browser
- Template-Dateien liegen im Unterordner mit dem Benutzernamen

---

## Passwort hashen

Statt eines Klartextpassworts kann ein SHA-256-Hash in `users.yaml` hinterlegt werden. Der Hash ist 64 Hex-Zeichen lang und ersetzt das Klartext-Passwort direkt.

**Linux / macOS (Terminal):**
```sh
echo -n "MeinPasswort" | sha256sum
```

**macOS alternativ:**
```sh
echo -n "MeinPasswort" | shasum -a 256
```

**Windows (PowerShell):**
```powershell
[System.BitConverter]::ToString(
  [System.Security.Cryptography.SHA256]::Create().ComputeHash(
    [System.Text.Encoding]::UTF8.GetBytes("MeinPasswort")
  )
).Replace("-","").ToLower()
```

**Home Assistant Terminal Add-on:**
```sh
echo -n "MeinPasswort" | sha256sum
```

Das Ergebnis (nur die 64 Hex-Zeichen, ohne das abschließende ` -`) wird als `password`-Wert eingetragen:

```yaml
users:
  - username: user1
    password: a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3
```

> **Wichtig:** `echo -n` verwenden — ohne `-n` wird ein Zeilenumbruch mit gehasht und der Hash stimmt nicht.

---

## Template-Dateien (.j2)

Templates verwenden die vollständige HA-Jinja2-Syntax. Alle Funktionen die auch in der HA Markdown-Karte verfügbar sind, funktionieren hier:

```jinja2
{%- set temp = states('sensor.wohnzimmer_temperature') | float(0) -%}
{%- set regen = states('binary_sensor.rain_detected') -%}

## Wohnzimmer

Temperatur: **{{ temp | round(1) }}°C**
Regen: {% if regen == 'on' %}🌧️ Ja{% else %}☀️ Nein{% endif %}
```

### Hinweis zur Ausrichtung

Für Leerzeichen-ausgerichteten Text (wie in HA Markdown-Karten üblich) wird der Inhalt in einer Monospace-Schrift dargestellt und Leerzeichen bleiben erhalten. Standard-Markdown-Syntax wie `**fett**`, `## Überschrift` oder Tabellen wird ebenfalls gerendert.

---

## Admin-API

Die Admin-API läuft auf einem separaten Port (Standard: **17773**) und ist ausschließlich aus dem lokalen Netzwerk erreichbar. Anfragen von öffentlichen IPs werden mit `403 Forbidden` abgewiesen.

Zugelassene IP-Bereiche:

| Bereich | Beschreibung |
|---|---|
| `10.0.0.0/8` | Private IPv4 (RFC-1918) |
| `172.16.0.0/12` | Private IPv4 (RFC-1918) |
| `192.168.0.0/16` | Private IPv4 (RFC-1918) |
| `127.0.0.0/8` | Loopback IPv4 |
| `::1` | Loopback IPv6 |
| `169.254.0.0/16` | Link-Local IPv4 |
| `fe80::/10` | Link-Local IPv6 |

> **nginx**: Port 17773 **nicht** in der nginx-Konfiguration eintragen — nur Port 17772 proxyen.

### Endpunkte

#### `GET /api/admin/stats`
Gesamt-Statistik aller Login-Ereignisse.

```json
{
  "total_logins": 42,
  "successful_logins": 38,
  "failed_logins": 4,
  "last_24h": { "successful": 5, "failed": 1 }
}
```

#### `GET /api/admin/logins`
Login-Ereignisse, neueste zuerst.

Query-Parameter:

| Parameter | Werte | Standard |
|---|---|---|
| `status` | `all` / `success` / `failed` | `all` |
| `username` | Benutzername (optional) | – |
| `limit` | 1–500 | `100` |
| `offset` | Zahl | `0` |

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
Prüft die Verbindung zur HA-API.

```json
{ "status": "ok", "ha_api": { "reachable": true, "message": "ok" } }
```

---

## Admin-API in Home Assistant einbinden

Die Admin-API lässt sich direkt als HA-Sensor einbinden, um Login-Statistiken im Dashboard anzuzeigen oder bei verdächtigen Logins eine Benachrichtigung zu erhalten.

Da HA und CardBoard auf demselben Host laufen, ist die Admin-API intern über `http://localhost:17773` erreichbar.

### REST-Sensoren (`configuration.yaml`)

```yaml
sensor:
  - platform: rest
    name: "CardBoard Logins gesamt"
    unique_id: cardboard_total_logins
    resource: http://localhost:17773/api/admin/stats
    value_template: "{{ value_json.total_logins }}"
    scan_interval: 300
    icon: mdi:account-key

  - platform: rest
    name: "CardBoard Erfolgreiche Logins"
    unique_id: cardboard_successful_logins
    resource: http://localhost:17773/api/admin/stats
    value_template: "{{ value_json.successful_logins }}"
    scan_interval: 300
    icon: mdi:account-check

  - platform: rest
    name: "CardBoard Fehlgeschlagene Logins"
    unique_id: cardboard_failed_logins
    resource: http://localhost:17773/api/admin/stats
    value_template: "{{ value_json.failed_logins }}"
    scan_interval: 300
    icon: mdi:account-alert

  - platform: rest
    name: "CardBoard Fehlgeschlagene Logins 24h"
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

### Template-Sensor für letzten fehlgeschlagenen Login

Dieser Sensor zeigt Zeitpunkt und IP-Adresse des letzten fehlgeschlagenen Login-Versuchs:

```yaml
sensor:
  - platform: rest
    name: "CardBoard Letzter fehlgeschlagener Login"
    unique_id: cardboard_last_failed_login
    resource: "http://localhost:17773/api/admin/logins?status=failed&limit=1"
    value_template: >
      {% if value_json.events | length > 0 %}
        {{ value_json.events[0].timestamp }} ({{ value_json.events[0].ip }})
      {% else %}
        Keine
      {% endif %}
    scan_interval: 300
    icon: mdi:shield-alert
```

### Automation: Benachrichtigung bei fehlgeschlagenem Login

```yaml
automation:
  - alias: "CardBoard Login Fehlversuch"
    description: "Benachrichtigung wenn jemand falsche Zugangsdaten eingibt"
    triggers:
      - trigger: state
        entity_id: sensor.cardboard_fehlgeschlagene_logins_24h
    conditions:
      - condition: template
        value_template: >
          {{ trigger.to_state.state | int(0) > trigger.from_state.state | int(0) }}
    actions:
      - action: notify.notify
        data:
          title: "⚠️ CardBoard Login Fehlversuch"
          message: >
            Fehlgeschlagener Login-Versuch auf CardBoard.
            Fehlversuche letzte 24h: {{ states('sensor.cardboard_fehlgeschlagene_logins_24h') }}
```

### Automation: Alarm bei HA API Ausfall

```yaml
automation:
  - alias: "CardBoard HA API nicht erreichbar"
    triggers:
      - trigger: state
        entity_id: sensor.cardboard_ha_api_status
        to: "degraded"
        for:
          minutes: 2
    actions:
      - action: notify.notify
        data:
          title: "🔴 CardBoard: HA API nicht erreichbar"
          message: "CardBoard kann die Home Assistant API nicht erreichen."
```

> **Hinweis:** Nach dem Einfügen in `configuration.yaml` muss HA neu geladen werden:  
> **Entwicklerwerkzeuge → YAML → Alle YAML-Konfigurationen prüfen & neu laden**

---

## Anmeldung

- Die Web-Oberfläche ist über `http://<HA-IP>:17772` erreichbar
- Nach erfolgreichem Login wird eine Cookie-Session für 7 Tage gespeichert
- Benutzer können nur die Ansicht lesen, keine Konfiguration ändern
