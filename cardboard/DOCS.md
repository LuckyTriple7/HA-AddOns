# CardBoard – Dokumentation

## Übersicht

CardBoard rendert Jinja2-Templates direkt über die HA-Template-API und stellt die Ergebnisse als Markdown-Karten im Browser dar. Mehrere Benutzer können gleichzeitig ihre eigenen Ansichten nutzen. Benutzer und Templates werden über das integrierte Admin-Panel verwaltet.

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
| `admin_password` | Passwort für das Admin-Panel (optional). Leer = Admin-Panel ohne Passwort aus dem LAN erreichbar | – |
| `max_cards` | Maximale Anzahl gleichzeitig angezeigter Karten pro Benutzer (optional) | `3` |
| `cards_per_row` | Anzahl Karten nebeneinander auf dem Desktop (optional, 1–6). Mobile: immer eine Karte pro Zeile. | `3` |

Den Long-Lived Access Token erstellst du in HA unter:  
**Profil → Sicherheit → Langlebige Zugangstoken → Token erstellen**

Der Uptime-Sensor wird für die „online seit"-Anzeige auf der Login- und View-Seite verwendet. Er muss über die **Uptime-Integration** eingerichtet sein: <https://www.home-assistant.io/integrations/uptime/>

---

## Admin-Panel

Das Admin-Panel ist die zentrale Verwaltungsoberfläche für Benutzer und Templates — ohne manuelle Bearbeitung von Dateien.

### Zugang

| Weg | URL |
|---|---|
| HA Sidebar (Ingress) | Über den CardBoard-Eintrag in der HA-Seitenleiste |
| Direkt (LAN) | `http://<HA-IP>:17773/admin/` |

Ist `admin_password` gesetzt, erscheint beim ersten Aufruf eine Login-Seite. Die Admin-Session ist 4 Stunden gültig.  
Ist kein Passwort gesetzt, ist das Admin-Panel ohne Login aus dem LAN erreichbar.

> **nginx**: Port 17773 und Port 17774 (Ingress) **nicht** in nginx eintragen — nur Port 17772 proxyen.

### Benutzerverwaltung

| Funktion | Beschreibung |
|---|---|
| **Benutzer anlegen** | Benutzername, Anzeigename, Sprache, initiales Passwort. Das Benutzerverzeichnis wird automatisch angelegt. `force_pw_change` wird gesetzt — Benutzer muss Passwort beim ersten Login ändern. |
| **Benutzer bearbeiten** | Anzeigename, Sprache und `force_pw_change`-Flag anpassen. |
| **Passwort zurücksetzen** | Neues Passwort setzen; `force_pw_change` wird automatisch aktiviert. |
| **Benutzer löschen** | Entfernt den Eintrag aus `users.yaml`. Das Verzeichnis mit den Templates bleibt erhalten. |
| **Login-Verlauf** | 📊-Button pro Benutzer zeigt die letzten 50 Login-Ereignisse (Zeitpunkt, Ergebnis, IP). |

### Template-Editor

Der Template-Editor ist über den 📝-Button in der Benutzertabelle erreichbar.

| Funktion | Beschreibung |
|---|---|
| **Templates anlegen** | Dateiname (`.j2`), optionaler Titel, Inhalt direkt im Browser eingeben. |
| **Templates bearbeiten** | Klick auf ein Template in der Liste öffnet es im Editor. |
| **Reihenfolge ändern** | ↑/↓-Buttons bestimmen die Anzeigereihenfolge der Karten. |
| **Live-Vorschau** | 👁-Button rendert das Template über die HA-API und zeigt die Karte in Echtzeit. |
| **Speichern** | Button oder **Ctrl+S** (Cmd+S auf Mac). |
| **Template löschen** | 🗑-Button pro Template, mit Bestätigungsdialog. |

> Sind mehr als `max_cards` Templates vorhanden, erscheint ein Hinweis — nur die ersten `max_cards` Templates werden in der View-Ansicht angezeigt.

### Gesperrte IPs (Rate Limiting)

Im unteren Bereich des Admin-Panels wird eine Liste aktuell gesperrter IPs angezeigt. Eine IP wird nach 5 fehlgeschlagenen Login-Versuchen innerhalb von 10 Minuten für 15 Minuten gesperrt.

- Lokale/private IPs (LAN) sind von der Sperre **ausgenommen**
- Gesperrte IPs können per **Entsperren**-Button manuell freigegeben werden

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

Die `users.yaml` wird normalerweise über das Admin-Panel verwaltet. Zur manuellen Bearbeitung:

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
- `display_name` (optional) – wird als Begrüßung angezeigt. Fehlt das Feld, wird der `username` verwendet
- `lang` (optional) – Anzeigesprache: `de` (Standard) oder `en`
- `password` – Klartext oder SHA-256-Hash (64 Hex-Zeichen)
- `templates` – Reihenfolge = Reihenfolge im Browser; max. `max_cards` Karten werden angezeigt
- `force_pw_change: true` – Benutzer wird beim nächsten Login zur Passwortänderung gezwungen

---

## Passwort hashen

Statt eines Klartextpassworts kann ein SHA-256-Hash in `users.yaml` hinterlegt werden.

**Linux / macOS:**
```sh
echo -n "MeinPasswort" | sha256sum
```

**Windows (PowerShell):**
```powershell
[System.BitConverter]::ToString(
  [System.Security.Cryptography.SHA256]::Create().ComputeHash(
    [System.Text.Encoding]::UTF8.GetBytes("MeinPasswort")
  )
).Replace("-","").ToLower()
```

> **Wichtig:** `echo -n` verwenden — ohne `-n` wird ein Zeilenumbruch mit gehasht.

---

## Template-Dateien (.j2)

Templates verwenden die vollständige HA-Jinja2-Syntax:

```jinja2
{%- set temp = states('sensor.wohnzimmer_temperature') | float(0) -%}
{%- set regen = states('binary_sensor.rain_detected') -%}

## Wohnzimmer

Temperatur: **{{ temp | round(1) }}°C**
Regen: {% if regen == 'on' %}🌧️ Ja{% else %}☀️ Nein{% endif %}
```

Inhalte werden in einer Monospace-Schrift dargestellt, Leerzeichen-Ausrichtung bleibt erhalten. Standard-Markdown-Syntax wie `**fett**`, `## Überschrift` oder Tabellen wird vollständig gerendert.

---

## PWA – Als App installieren

CardBoard unterstützt die Installation als Progressive Web App (PWA).

| Gerät | Voraussetzung | Vorgehen |
|---|---|---|
| **iPhone / iPad** | beliebiger Browser | Safari: Teilen (📤) → „Zum Home-Bildschirm" |
| **Android** | HTTPS | Chrome: Menü → „Zum Startbildschirm hinzufügen" oder automatischer Banner |
| **Desktop** | HTTPS | Chrome/Edge: Installieren-Symbol in der Adressleiste |

Nach der Installation öffnet sich CardBoard ohne Browser-Chrome als eigenständige App. Die Statusleiste folgt dem gewählten Dark/Light-Theme.

> Für Android/Desktop ist HTTPS erforderlich (z. B. via nginx mit Let's Encrypt).

---

## Admin-API

Die Admin-API läuft auf Port **17773** und ist ausschließlich aus dem lokalen Netzwerk erreichbar.

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

#### `GET /api/admin/health`
Prüft die Verbindung zur HA-API.

```json
{ "status": "ok", "ha_api": { "reachable": true, "message": "ok" } }
```

---

## Admin-API in Home Assistant einbinden

Da HA und CardBoard auf demselben physischen Host laufen, die Ports aber auf den Host gemappt sind, ist die Admin-API über den Hostnamen der HA-Instanz erreichbar — **nicht** über `localhost`.

```
http://homeassistant.local:17773
```

### REST-Sensoren (`configuration.yaml`)

```yaml
sensor:
  - platform: rest
    name: "CardBoard Logins gesamt"
    unique_id: cardboard_total_logins
    resource: http://homeassistant.local:17773/api/admin/stats
    value_template: "{{ value_json.total_logins }}"
    scan_interval: 300
    icon: mdi:account-key

  - platform: rest
    name: "CardBoard Fehlgeschlagene Logins 24h"
    unique_id: cardboard_failed_logins_24h
    resource: http://homeassistant.local:17773/api/admin/stats
    value_template: "{{ value_json.last_24h.failed }}"
    scan_interval: 300
    icon: mdi:account-alert-outline

  - platform: rest
    name: "CardBoard Letzter erfolgreicher Login"
    unique_id: cardboard_last_successful_login
    resource: "http://homeassistant.local:17773/api/admin/logins?status=success&limit=1"
    value_template: >
      {% if value_json.events | length > 0 %}
        {{ value_json.events[0].username }} — {{ value_json.events[0].timestamp[:16].replace('T',' ') }} ({{ value_json.events[0].ip }})
      {% else %}-{% endif %}
    scan_interval: 300
    icon: mdi:account-check

  - platform: rest
    name: "CardBoard Letzter fehlgeschlagener Login"
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

### Automation: Benachrichtigung bei fehlgeschlagenem Login

```yaml
automation:
  - alias: "CardBoard Login Fehlversuch"
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

## nginx als Reverse-Proxy

CardBoard selbst spricht nur HTTP. Für externen Zugriff nginx als HTTPS-Reverse-Proxy davor schalten. Port **17773** (Admin-API) darf dabei **nicht** proxied werden.

### Wichtige Header

| Header | Zweck |
|---|---|
| `X-Forwarded-For` | Echte Client-IP (für Login-Log und Benachrichtigungen) |
| `X-Forwarded-Proto` | Setzt das `Secure`-Flag am Session-Cookie bei HTTPS |

### Beispiel-Konfiguration

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

> Port `17773` (Admin-API) **nicht** in nginx eintragen.  
> SSL-Zertifikat z. B. mit [Let's Encrypt](https://letsencrypt.org/) und Certbot.

---

## Anmeldung

- Web-Oberfläche: `http://<HA-IP>:17772` (intern) oder nginx-URL (extern)
- Nach erfolgreichem Login: Cookie-Session (konfigurierbar, Standard: 7 Tage)
- Das Session-Cookie erhält das `Secure`-Flag automatisch wenn HTTPS erkannt wird
- Bei abgelaufener Session: automatische Weiterleitung zur Login-Seite mit Hinweismeldung
- Benutzer können nur die Ansicht lesen, keine Konfiguration ändern
