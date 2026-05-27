# Collabora Online

Collabora Online Office-Server für Nextcloud — öffne und bearbeite `.docx`, `.xlsx`, `.pptx` und ODF-Dateien direkt im Browser, ohne Download.

## Einrichtung

### 1. Add-on konfigurieren und starten

| Option | Beschreibung |
|--------|--------------|
| `nextcloud_url` | URL deiner Nextcloud-Instanz (z.B. `https://192.168.178.100:7443`) |
| `admin_user` | Benutzername für das Collabora-Admin-Panel (Standard: `admin`) |
| `admin_password` | Passwort für das Collabora-Admin-Panel |
| `aliasgroup1` | Erlaubte Domain als regulärer Ausdruck (überschreibt `nextcloud_url`-Erkennung, z.B. `192\\.168\\.178\\.100`) |
| `domain1` | Externer Hostname des Collabora-Servers — nur für Reverse-Proxy-Setups nötig |
| `extra_params` | Zusätzliche coolwsd-Parameter (leer lassen für Standardwerte) |

### 2. Nextcloud Office-App aktivieren

1. In Nextcloud: **Apps → Office & Text → Nextcloud Office** installieren
2. **Einstellungen → Verwaltung → Nextcloud Office** öffnen
3. **„Eigenen Server verwenden"** wählen
4. URL eintragen: `http://<HA-IP>:9980`
5. Speichern — der grüne Haken bestätigt die Verbindung

### 3. WOPI-Allowlist setzen (empfohlen)

Nextcloud zeigt sonst eine Sicherheitswarnung, dass WOPI-Anfragen nicht eingeschränkt sind. Im **Nextcloud-Terminal** ausführen:

```sh
ALLOW_ROOT=1 php /app/www/public/occ config:app:set richdocuments wopi_allowlist --value="172.30.0.0/16"
```

Der Bereich `172.30.0.0/16` umfasst alle HA-Add-on-Container und ist damit zukunftssicher, da sich Container-IPs bei Neustarts ändern können.

## Admin-Panel

Erreichbar unter: `http://<HA-IP>:9980/browser/dist/admin/admin.html`

Benutzername und Passwort wie in der Konfiguration gesetzt.

## Web-Terminal

Das Add-on enthält ein Web-Terminal, erreichbar über den **„Collabora Terminal"-Eintrag in der HA-Seitenleiste**.

Nützlich um z.B. die Konfiguration direkt zu prüfen:
```sh
coolconfig get-admin-password
cat /config/coolwsd.xml
```

## Hinweise

- Collabora speichert keine Dateien — alle Daten verbleiben in Nextcloud
- SSL ist für lokale Nutzung deaktiviert (Nextcloud und Collabora kommunizieren intern per HTTP)
- Die Domain-Beschränkung verhindert, dass fremde Nextcloud-Instanzen den Server nutzen können
- Bei Zugriff über einen Reverse-Proxy muss der Proxy WebSocket-Verbindungen durchleiten

---

# Collabora Online (English)

Collabora Online office server for Nextcloud — open and edit `.docx`, `.xlsx`, `.pptx` and ODF files directly in the browser, without downloading.

## Setup

### 1. Configure and Start the Add-on

| Option | Description |
|--------|-------------|
| `nextcloud_url` | URL of your Nextcloud instance (e.g. `https://192.168.178.100:7443`) |
| `admin_user` | Username for the Collabora admin panel (default: `admin`) |
| `admin_password` | Password for the Collabora admin panel |
| `aliasgroup1` | Allowed domain as a regular expression (overrides `nextcloud_url` detection, e.g. `192\\.168\\.178\\.100`) |
| `domain1` | External hostname of the Collabora server — only needed for reverse proxy setups |
| `extra_params` | Additional coolwsd parameters (leave empty for defaults) |

### 2. Activate the Nextcloud Office App

1. In Nextcloud: **Apps → Office & Text → Nextcloud Office** install
2. Open **Settings → Administration → Nextcloud Office**
3. Select **"Use your own server"**
4. Enter URL: `http://<HA-IP>:9980`
5. Save — a green checkmark confirms the connection

### 3. Set WOPI Allowlist (recommended)

Without this, Nextcloud shows a security warning that WOPI requests are unrestricted. Run in the **Nextcloud Terminal**:

```sh
ALLOW_ROOT=1 php /app/www/public/occ config:app:set richdocuments wopi_allowlist --value="172.30.0.0/16"
```

The range `172.30.0.0/16` covers all HA add-on containers and is future-proof since container IPs can change on restart.

## Admin Panel

Available at: `http://<HA-IP>:9980/browser/dist/admin/admin.html`

Username and password as configured.

## Web Terminal

The add-on includes a web terminal, accessible via the **"Collabora Terminal" entry in the HA sidebar**.

Useful for inspecting the configuration directly:
```sh
coolconfig get-admin-password
cat /config/coolwsd.xml
```

## Notes

- Collabora does not store files — all data stays in Nextcloud
- SSL is disabled for local use (Nextcloud and Collabora communicate internally via HTTP)
- The domain restriction prevents other Nextcloud instances from using the server
- When using a reverse proxy, the proxy must forward WebSocket connections
