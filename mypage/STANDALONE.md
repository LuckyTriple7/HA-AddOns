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

## Konfiguration

### `options.json` — nur die Login-Daten

Die Datei wird nach `/data/options.json` im Container gemountet (read-only) und beim Start gelesen.

| Schlüssel | Bedeutung | Standard |
|---|---|---|
| `username` | Admin-Benutzername | `admin` |
| `password` | **Admin-Passwort — unbedingt setzen!** | _(leer)_ |
| `session_hours` | Gültigkeit der Admin-Sitzung in Stunden | `24` |

### Alles Weitere: Admin-Panel → **Einstellungen**

Mailversand, Telegram, GitHub-Token, KI-Keys, SMB-Speicher, Besucherzähler und Backup-Aufbewahrung stellst du im Admin-Panel im Reiter **Einstellungen** ein — kein Editor, kein Neustart.

Gespeichert wird in `./data/settings.json`. Tokens und Passwörter werden mit `./data/settings.key` **verschlüsselt** abgelegt, im Browser nie angezeigt (nur „gesetzt"/„nicht gesetzt") und beim Speichern nur als Feldname protokolliert.

* Ein leeres Geheimfeld heißt **„unverändert lassen"** — zum Entfernen den Knopf **Löschen** benutzen.
* Der Knopf **Schlüssel herunterladen** (Reiter *Einstellungen*) sichert `settings.key` mit einer Passphrase verpackt — die einzige Möglichkeit, die Zugangsdaten auf einer frischen Installation zurückzuholen. Vorher fragt MyPage das Admin-Passwort erneut ab.
* Fast alles greift sofort. Nur die **SMB-Felder** brauchen einen `docker compose restart`, wenn beim Start noch keine Freigabe eingerichtet war (die Oberfläche weist darauf hin).
* Wer aus einer älteren Version kommt: Beim ersten Start übernimmt MyPage die vorhandenen Werte aus `options.json` automatisch in `settings.json` — und verschlüsselt sie dabei. Danach sind die alten Einträge in `options.json` wirkungslos und können gelöscht werden.

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

1. **Im Admin-Panel** unter *System → Backup* ein ZIP mit allen Inhalten herunterladen (und per *Backup einspielen* zurückspielen). Das ZIP enthält `settings.json`, aber **nicht** den Schlüssel `settings.key` — Zugangsdaten sind darin also nicht lesbar. Beim Einspielen auf einer frischen Installation müssen sie einmal neu eingetragen werden.
2. Den Ordner **`./data`** sichern (enthält zusätzlich Uploads, Mitglieder-Dateien und `settings.key`) — dieser Ordner gehört an einen sicheren Ort.

---

## Sicherheitshinweise

- **Starkes Admin-Passwort** in `options.json` setzen — ohne Ingress schützt nur dieses Login das Admin-Panel.
- `./data/settings.key` entschlüsselt alle gespeicherten Zugangsdaten: Datei nicht weitergeben und nicht in ein öffentliches Repository legen.
- Admin-Panel **nur über HTTPS** erreichbar machen (Caddy/Cloudflare Tunnel).
- **Brute-Force-Schutz**: fünf Fehlversuche je Adresse sperren diese für 15 Minuten, zwanzig Fehlversuche je Verbindung sperren die Gegenstelle. Bis 0.11.29 zählte nur die erste Sperre — und die Adresse stammte aus einer Kopfzeile, die jeder selbst setzen kann; durch Weiterdrehen war sie wirkungslos. **Mit älteren Fassungen als 0.11.30 darf der Admin-Port nicht öffentlich erreichbar sein.**
- **Ohne Ingress ist der Ingress-Weg gar nicht vorhanden**: `_is_ingress()` ist unter Docker immer falsch, es gilt ausnahmslos das Login. Die Option `ingress_trust_net` bleibt **leer** — wer dort das Docker-Bridge-Netz einträgt, lässt jeden Container ohne Anmeldung in den Admin.
- **2FA einschalten** (Admin → System → Zugang). Sie gilt für den direkten Login, also für den einzigen Weg, den es hier gibt. Der Notausgang „über Home Assistant anmelden und 2FA abschalten" existiert unter Docker **nicht** — Backup-Codes aufbewahren; im Notfall hilft nur, `data/admin_2fa.json` zu löschen.
- Das Admin-Panel **nicht ohne Not öffentlich exponieren**: In der Beispiel-Compose steht bewusst `expose: 17761` statt `ports:`, erreichbar ist es damit nur für Caddy im internen Netz. Wenn es doch nach außen muss: eigene Subdomain, zusätzlich Firewall, Basic-Auth, CrowdSec oder fail2ban davor — oder nur an `127.0.0.1` binden und per SSH-Tunnel bzw. VPN darauf zugreifen.
- **`trusted_proxies`** (optional): Standardmäßig gelten alle privaten Adressen als Zwischenglied, deren Weiterleitungs-Kopfzeilen geglaubt werden. Steht der Proxy fest, trag ihn dort ein (z. B. `172.18.0.0/16`) — dann darf wirklich nur er eine Besucheradresse melden.
