# CardBoard – Dokumentation

## Übersicht

CardBoard rendert Jinja2-Templates direkt über die HA-Template-API und stellt die Ergebnisse als Markdown-Karten im Browser dar. Mehrere Benutzer können gleichzeitig ihre eigenen Ansichten nutzen.

---

## Add-on Optionen

| Option | Beschreibung | Standard |
|---|---|---|
| `port` | TCP-Port der Web-Oberfläche | `17772` |
| `admin_port` | TCP-Port der Admin-API (nur LAN) | `17773` |
| `ha_token` | HA Long-Lived Access Token | – |
| `ha_url` | URL der HA-Instanz (intern) | `http://homeassistant:8123` |
| `refresh_interval` | Automatische Aktualisierung in Sekunden | `30` |

Den Long-Lived Access Token erstellst du in HA unter:  
**Profil → Sicherheit → Langlebige Zugangstoken → Token erstellen**

---

## Konfigurationsstruktur

Alle Benutzer-Konfigurationen liegen unter `/config/addons_config/cardboard/`:

```
/config/addons_config/cardboard/
├── users.yaml
├── andy/
│   ├── solar.j2
│   ├── temps.j2
│   └── netz.j2
└── mika/
    └── uebersicht.j2
```

---

## users.yaml

```yaml
users:
  - username: andy
    password: geheim123
    display_name: Andreas Mustermann
    lang: de
    templates:
      - file: solar.j2
        title: Solar
      - file: temps.j2
        title: Temperaturen
      - file: netz.j2
        title: Netzverbrauch
  - username: mika
    password: anderes_passwort
    display_name: Mika Musterfrau
    lang: en
    templates:
      - uebersicht.j2        # Kurzform ohne Titel ist weiterhin gültig
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
  - username: andy
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

Die Admin-API läuft auf einem separaten Port (Standard: **17773**) und ist ausschließlich aus dem lokalen Netzwerk (RFC-1918-Adressen) erreichbar. Anfragen von öffentlichen IPs werden mit `403 Forbidden` abgewiesen.

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
curl http://<HA-IP>:17773/api/admin/logins?username=andy&limit=20
```

```json
{
  "total": 4,
  "limit": 100,
  "offset": 0,
  "events": [
    { "timestamp": "2025-05-28T14:22:01", "username": "andy", "success": false, "ip": "192.168.1.42" }
  ]
}
```

#### `GET /api/admin/health`
Prüft die Verbindung zur HA-API.

```json
{ "status": "ok", "ha_api": { "reachable": true, "message": "ok" } }
```

---

## Anmeldung

- Die Web-Oberfläche ist über `http://<HA-IP>:17772` erreichbar
- Nach erfolgreichem Login wird eine Cookie-Session für 7 Tage gespeichert
- Benutzer können nur die Ansicht lesen, keine Konfiguration ändern
