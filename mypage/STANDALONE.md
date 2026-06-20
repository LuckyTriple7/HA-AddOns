# MyPage ohne Home Assistant betreiben (Standalone)

MyPage ist im Kern eine normale Flask-App in einem Standard-Docker-Image — Home Assistant ist nur die bequeme Verpackung, keine Voraussetzung. Du kannst MyPage daher auf jedem Server mit **Docker** betreiben.

> Das fertige Image liegt unter `ghcr.io/luckytriple7/mypage:latest` (amd64 + aarch64). Du brauchst den Quellcode **nicht** — nur Docker, eine `docker-compose.yml` und eine `options.json`.

---

## Schnellstart

```bash
# 1. Beispiel-Konfiguration kopieren und Passwort ändern
cp options.example.json options.json
nano options.json          # mindestens "password" setzen!

# 2. Starten
docker compose up -d

# 3. Aufrufen
#   Öffentliche Seite:  http://<server>:17760
#   Admin-Panel:        http://<server>:17761   (Login: username/password aus options.json)
```

Beim ersten Start legt MyPage seine Daten im Ordner `./data` an (`site.json`, `uploads/`, Mitglieder, Spielstände …).

---

## Konfiguration (`options.json`)

Die Datei wird nach `/data/options.json` im Container gemountet (read-only) und beim Start gelesen. Alle Felder sind optional außer einem **sicheren Passwort**.

| Schlüssel | Bedeutung | Standard |
|---|---|---|
| `username` | Admin-Benutzername | `admin` |
| `password` | **Admin-Passwort — unbedingt setzen!** | _(leer)_ |
| `session_hours` | Gültigkeit der Admin-Sitzung in Stunden | `24` |
| `smtp_host` / `smtp_port` | Mailserver für Benachrichtigungen, Newsletter, Mitglieder-Mails | – / `587` |
| `smtp_user` / `smtp_password` | Zugangsdaten Mailserver | – |
| `smtp_from` / `smtp_to` | Absender / Empfänger für Kontakt-Benachrichtigungen | – |
| `smtp_tls` | STARTTLS verwenden | `true` |
| `telegram_bot_token` / `telegram_chat_id` | Optionale Telegram-Benachrichtigung bei neuen Nachrichten | – |
| `github_token` | Optionaler Token für den GitHub-Projekt-Import (höheres Rate-Limit) | – |
| `translate_email` | E-Mail für das kostenlose MyMemory-Übersetzungs-Limit | – |
| `user_upload_max_mb` | Max. Upload-Größe je Datei (Mitgliederbereich) | `200` |
| `visit_log_max` | Länge des Besucher-Logs | `500` |
| `geoip_lookup` / `geoip_api_key` | Länder-Auflösung in der Statistik (optional) | `false` |
| `smb_server` / `smb_share` / `smb_user` / `smb_password` | Optionaler SMB-Speicher für Mitglieder-Dateien | – |

Nach Änderungen an `options.json` den Container neu starten: `docker compose restart`.

---

## HTTPS (empfohlen für den Produktivbetrieb)

Ohne HA-Ingress ist das **Admin-Login die einzige Schutzschicht** — es darf daher **niemals über unverschlüsseltes HTTP** laufen. Setze einen Reverse-Proxy mit automatischem Let's-Encrypt-Zertifikat davor, z. B. **Caddy**.

`docker-compose.yml` (mit Caddy, Ports nicht mehr direkt nach außen):

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

Passende `Caddyfile` (öffentliche Seite auf der Hauptdomain, Admin auf einer Subdomain):

```caddyfile
deine-domain.de {
    reverse_proxy mypage:17760
}

admin.deine-domain.de {
    reverse_proxy mypage:17761
}
```

Caddy holt die Zertifikate automatisch. Trage in beide DNS-Einträge die IP deines Servers ein. Im Admin-Panel unter **Design → Öffentliche URL** anschließend `https://deine-domain.de` eintragen, damit Sitemap, RSS und Teilen-Links korrekte Adressen erzeugen.

> Alternativ funktioniert auch ein **Cloudflare Tunnel** (siehe README) — dann brauchst du keine offenen Ports.

---

## Was ohne Home Assistant fehlt

Diese drei Dinge sind HA-spezifisch und entfallen — **alles andere funktioniert unverändert**:

- **HA-Sensoren** (`sensor.mypage_*` mit Besucherzahl, offenen Anfragen …)
- **HA-Benachrichtigungen** im HA-Dashboard
- **Ingress** (Single-Sign-on übers HA-Menü) → stattdessen das eingebaute Benutzername/Passwort-Login

Voll nutzbar bleiben: öffentliche Seite mit allen Inhalts-Bausteinen, Blog, eigene Seiten, Formulare, Mitgliederbereich, Spiele, **E-Mail- und Telegram-Benachrichtigungen**, SMB-Speicher, Backup/Restore, SEO/Sitemap/Weiterleitungen, Teilen-Buttons.

---

## Updates

```bash
docker compose pull
docker compose up -d
```

Die Daten in `./data` bleiben dabei erhalten.

---

## Backup

Zwei Wege, am besten kombiniert:

1. **Im Admin-Panel** unter *System → Backup* ein ZIP mit allen Inhalten herunterladen (und per *Backup einspielen* zurückspielen).
2. Den Ordner **`./data`** sichern (enthält zusätzlich Uploads und Mitglieder-Dateien).

---

## Sicherheitshinweise

- **Starkes Admin-Passwort** in `options.json` setzen — ohne Ingress schützt nur dieses Login das Admin-Panel.
- Admin-Panel **nur über HTTPS** erreichbar machen (Caddy/Cloudflare Tunnel).
- Brute-Force-Schutz (Rate-Limit + temporäre Sperre) ist eingebaut; trotzdem das Admin-Panel nicht ohne Not öffentlich exponieren — idealerweise auf eine Subdomain legen oder per Firewall/Basic-Auth zusätzlich absichern.
