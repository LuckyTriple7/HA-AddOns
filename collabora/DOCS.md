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
4. URL eintragen: `https://<HA-IP>:9980`
5. Speichern — der grüne Haken bestätigt die Verbindung

### 3. WOPI-Allowlist setzen (empfohlen)

Nextcloud zeigt sonst eine Sicherheitswarnung, dass WOPI-Anfragen nicht eingeschränkt sind.

**Empfohlen — automatisch via Nextcloud Add-on:**

Im Nextcloud Add-on `update_wopi_ip: true` aktivieren. Das Add-on erkennt die externe IP automatisch und hält die WOPI-Allowlist aktuell (wichtig bei dynamischer ISP-IP hinter Reverse-Proxy).

**Alternativ — manuell im Nextcloud-Terminal:**

```sh
ALLOW_ROOT=1 php /app/www/public/occ config:app:set richdocuments wopi_allowlist --value="<externe-IP>"
```

> Hinweis: Es muss die **externe IP** eingetragen werden (die IP, über die Nextcloud von außen erreichbar ist), nicht die interne Docker-IP.

## Admin-Panel

Erreichbar unter: `https://<HA-IP>:9980/browser/dist/admin/admin.html`

coolwsd liefert https mit einem selbst erzeugten Zertifikat aus, die Browser-Warnung ist also normal. Nur wenn `extra_params` ein `--o:ssl.enable=false` enthält, ist es stattdessen `http://`.

Benutzername und Passwort wie in der Konfiguration gesetzt.

## Web-Terminal

Das Add-on enthält ein Web-Terminal (ttyd), erreichbar über den **„Collabora Terminal"-Eintrag in der HA-Seitenleiste** oder direkt unter `http://<HA-IP>:7682`.

> Der direkte Port-Zugang ist nicht durch die Home-Assistant-Anmeldung geschützt: Wer im Netzwerk `http://<HA-IP>:7682` aufruft, bekommt ohne Passwort eine schreibfähige Root-Shell im Container. Nur der Weg über die Seitenleiste (Ingress) läuft hinter der HA-Authentifizierung. Wenn du den Direktzugang nicht brauchst, entferne `7682/tcp` aus `ports` in der Add-on-Konfiguration.

Nützlich um z.B. die Konfiguration direkt zu prüfen:
```sh
ps aux | grep coolwsd
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
4. Enter URL: `https://<HA-IP>:9980`
5. Save — a green checkmark confirms the connection

### 3. Set WOPI Allowlist (recommended)

Without this, Nextcloud shows a security warning that WOPI requests are unrestricted.

**Recommended — automatic via Nextcloud add-on:**

Enable `update_wopi_ip: true` in the Nextcloud add-on. It automatically detects the external IP and keeps the WOPI allowlist up to date (important when using a dynamic ISP IP behind a reverse proxy).

**Alternative — manual via Nextcloud Terminal:**

```sh
ALLOW_ROOT=1 php /app/www/public/occ config:app:set richdocuments wopi_allowlist --value="<external-IP>"
```

> Note: Enter the **external IP** (the IP via which Nextcloud is reachable from the internet), not the internal Docker IP.

## Admin Panel

Available at: `https://<HA-IP>:9980/browser/dist/admin/admin.html`

coolwsd serves https with a self-generated certificate, so the browser warning is expected. Only if `extra_params` contains `--o:ssl.enable=false` is it `http://` instead.

Username and password as configured.

## Web Terminal

The add-on includes a web terminal (ttyd), accessible via the **"Collabora Terminal" entry in the HA sidebar** or directly at `http://<HA-IP>:7682`.

> The direct port is not protected by the Home Assistant login: anyone on the network who opens `http://<HA-IP>:7682` gets a writable root shell inside the container, without a password. Only the sidebar route (ingress) sits behind HA authentication. If you do not need the direct access, remove `7682/tcp` from `ports` in the add-on configuration.

Useful for inspecting the configuration directly:
```sh
ps aux | grep coolwsd
cat /config/coolwsd.xml
```

## Notes

- Collabora does not store files — all data stays in Nextcloud
- SSL is disabled for local use (Nextcloud and Collabora communicate internally via HTTP)
- The domain restriction prevents other Nextcloud instances from using the server
- When using a reverse proxy, the proxy must forward WebSocket connections
