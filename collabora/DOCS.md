# Collabora Online

Collabora Online Office-Server für Nextcloud — öffne und bearbeite `.docx`, `.xlsx`, `.pptx` und ODF-Dateien direkt im Browser, ohne Download.

## Einrichtung

### 1. Add-on konfigurieren und starten

| Option | Beschreibung |
|--------|--------------|
| `nextcloud_url` | URL deiner Nextcloud-Instanz (z.B. `https://192.168.178.100:7443`) |
| `admin_user` | Benutzername für das Collabora-Admin-Panel |
| `admin_password` | Passwort für das Collabora-Admin-Panel |
| `extra_params` | Zusätzliche coolwsd-Parameter (leer lassen für Standardwerte) |

### 2. Nextcloud Office-App aktivieren

1. In Nextcloud: **Apps → Office & Text → Nextcloud Office** installieren
2. **Einstellungen → Verwaltung → Nextcloud Office** öffnen
3. **„Eigenen Server verwenden"** wählen
4. URL eintragen: `http://<HA-IP>:9980`
5. Speichern — der grüne Haken bestätigt die Verbindung

## Admin-Panel

Erreichbar unter: `http://<HA-IP>:9980/browser/dist/admin/admin.html`

Benutzername und Passwort wie in der Konfiguration gesetzt.

## Hinweise

- Collabora speichert keine Dateien — alle Daten verbleiben in Nextcloud
- SSL ist für lokale Nutzung deaktiviert (Nextcloud und Collabora kommunizieren intern per HTTP)
- Bei Zugriff über einen Reverse-Proxy muss der Proxy WebSocket-Verbindungen durchleiten

---

# Collabora Online (English)

Collabora Online office server for Nextcloud — open and edit `.docx`, `.xlsx`, `.pptx` and ODF files directly in the browser, without downloading.

## Setup

### 1. Configure and Start the Add-on

| Option | Description |
|--------|-------------|
| `nextcloud_url` | URL of your Nextcloud instance (e.g. `https://192.168.178.100:7443`) |
| `admin_user` | Username for the Collabora admin panel |
| `admin_password` | Password for the Collabora admin panel |
| `extra_params` | Additional coolwsd parameters (leave empty for defaults) |

### 2. Activate the Nextcloud Office App

1. In Nextcloud: **Apps → Office & Text → Nextcloud Office** install
2. Open **Settings → Administration → Nextcloud Office**
3. Select **"Use your own server"**
4. Enter URL: `http://<HA-IP>:9980`
5. Save — a green checkmark confirms the connection

## Admin Panel

Available at: `http://<HA-IP>:9980/browser/dist/admin/admin.html`

Username and password as configured.

## Notes

- Collabora does not store files — all data stays in Nextcloud
- SSL is disabled for local use (Nextcloud and Collabora communicate internally via HTTP)
- When using a reverse proxy, the proxy must forward WebSocket connections
