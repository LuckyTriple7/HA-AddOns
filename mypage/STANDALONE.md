# MyPage ohne Home Assistant betreiben (Standalone)

MyPage ist im Kern eine normale Flask-App in einem Standard-Docker-Image — Home Assistant ist nur die bequeme Verpackung, keine Voraussetzung. Du kannst MyPage daher auf jedem Server mit **Docker** betreiben.

> Das fertige Image liegt unter `ghcr.io/luckytriple7/mypage:latest` (amd64 + aarch64). Du brauchst den Quellcode **nicht** — nur Docker und eine `docker-compose.yml`.

---

## Schnellstart

```bash
# 1. Starten — es ist nichts vorzubereiten
docker compose up -d

# 2. Erzeugtes Admin-Passwort aus dem Protokoll holen
docker compose logs mypage | grep -A 3 "Neue Installation"

# 3. Aufrufen
#   Öffentliche Seite:  http://<server>:17760
#   Admin-Panel:        http://<server>:17761   (Benutzer "admin", Passwort aus Schritt 2)
```

Beim ersten Start legt MyPage seine Daten im Ordner `./data` an (`site.json`, `uploads/`, Mitglieder, Spielstände …) und erzeugt dabei ein zufälliges Admin-Passwort (16 Zeichen, Groß- und Kleinbuchstaben plus Ziffern). Es steht **nur im Protokoll** — auf der Platte liegt bloß ein Hash in `./data/admin_login.json`. Also gleich notieren und danach im Admin-Panel ein eigenes vergeben.

---

## Mehrere Instanzen auf einem Server (Dockge)

MyPage kennt keine Instanzsperre: Auf einem Server laufen beliebig viele Container nebeneinander, solange jeder **eigene Host-Ports** und einen **eigenen Datenordner** bekommt. In [Dockge](https://github.com/louislam/dockge) heißt das: **ein Stack pro Instanz**. Jeder Stack hat seinen eigenen Ordner unter `/opt/docker/stacks/`, und `./data` zeigt automatisch dorthin — es ist nichts zu benennen oder zu trennen.

```
/opt/docker/stacks/
├── mypagea/       compose.yaml  data
└── mypageb/       compose.yaml  data
```

`/opt/docker/stacks/mypagea/compose.yaml`:

```yaml
services:
  mypage:
    image: ghcr.io/luckytriple7/mypage:latest
    container_name: mypagea
    ports:
      - "17760:17760"        # öffentliche Homepage
      - "17761:17761"        # Admin-Panel
    volumes:
      - ./data:/config
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:17760/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

`/opt/docker/stacks/mypageb/compose.yaml` — dieselbe Datei, drei Zeilen anders:

```yaml
    container_name: mypageb
    ports:
      - "17770:17760"
      - "17771:17761"
```

Die Ports **17760** und **17761** rechts vom Doppelpunkt sind containerintern fest verdrahtet und bleiben in jeder Instanz gleich; unterscheiden muss sich nur die linke, serverweit eindeutige Seite.

Nach *Deploy* das erzeugte Passwort im Log-Tab des Stacks abholen (Benutzer `admin`), einloggen und unter **System → Zugang** ein eigenes setzen — je Instanz ein anderes. Es gibt keine gemeinsame Anmeldung über mehrere Container.

Danach in jeder Instanz unter **Design → Öffentliche URL** die passende Adresse eintragen. Ohne diesen Eintrag rät MyPage `http://<host>:17760` — bei jeder Instanz außer der ersten also falsch, mit Folgen für Vorschau, Sitemap, RSS, PWA und Mail-Links.

**Worauf zu achten ist:**

- **Nie zwei Container auf denselben Datenordner.** `site.json`, Besucherzähler, Spielstände und Sitzungen würden sich gegenseitig überschreiben.
- **SMB-Speicher** braucht je Container `cap_add: [SYS_ADMIN, DAC_READ_SEARCH]` und `security_opt: [apparmor:unconfined]`. Zwei Instanzen dürfen nicht denselben Unterordner der Freigabe benutzen — in den Einstellungen je Instanz ein eigenes *Unterverzeichnis* setzen.
- **Der Brute-Force-Schutz zählt je Container**, nicht serverweit. Hinter einem Reverse Proxy in jeder Instanz `trusted_proxies` setzen (siehe unten), sonst sieht MyPage nur die Proxy-Adresse und sperrt bei einem Angriff alle Besucher zugleich aus.
- **Speicher**: grob 200–400 MB je Instanz. Auf einem kleinen VPS mitrechnen.

---

## Konfiguration

### Admin-Zugang — Passwort ändern

Im Admin-Panel unter **System → Zugang**: aktuelles Passwort eingeben (bei aktiver 2FA zusätzlich den Code), Benutzername und neues Passwort setzen. Verlangt werden mindestens **12 Zeichen mit Groß-, Kleinbuchstaben und Ziffer**. Beim Wechsel werden alle übrigen Admin-Sitzungen beendet — die eigene bleibt.

Gespeichert wird in `./data/admin_login.json`, und zwar nur der Hash. Die Datei kommt **nicht** ins Backup-ZIP: Ein Restore von letzter Woche würde sonst still das alte Passwort zurückholen.

### Passwort vergessen

```bash
cd /opt/docker/stacks/mypagea      # Ordner des Stacks bzw. der Compose-Datei
rm ./data/admin_login.json
docker compose restart
docker compose logs | grep -A 3 "Neue Installation"
```

Das Passwort steht danach auch im Log-Tab des Stacks in Dockge. Bei mehreren Instanzen betrifft das nur die eine, in deren Ordner du gelöscht hast — die übrigen bleiben unverändert.

MyPage erzeugt dann ein neues Passwort und schreibt es ins Protokoll. Inhalte, Mitglieder und Einstellungen bleiben unberührt. **2FA bleibt aktiv** — das Löschen der Datei ist bewusst kein kompletter Freifahrtschein für jeden mit Dateizugriff. Wer auch den zweiten Faktor verloren hat, löscht zusätzlich `./data/admin_2fa.json`.

> Erscheint die Meldung „Neue Installation" unerwartet, ist meist der Volume-Pfad falsch und MyPage startet auf einem leeren Ordner. Erst das Mount prüfen, bevor du Inhalte anlegst.

### Speicherlimit (nur über die compose.yaml)

Standardmäßig darf MyPage so viel Platz belegen, wie die Platte hergibt. Ein Gesamtlimit setzt du in der compose.yaml:

```yaml
    environment:
      MYPAGE_STORAGE_MAX_MB: 2048     # 0 oder weglassen = unbegrenzt
```

Gezählt wird alles im Datenordner: Bilder, Bibliothek-PDFs, Logos, Mitglieder-Dateien, Anhänge, Spielstände und die automatischen Sicherungen. Liegen die Mitglieder-Dateien auf einer SMB-Freigabe, stehen sie außerhalb und zählen nicht mit.

Ist das Limit erreicht, werden **neue Uploads abgewiesen** — Bedienen, Löschen und Aufräumen laufen weiter, damit man sich wieder Luft verschaffen kann. Statt eines neuen automatischen Backups werden die vorhandenen ausgedünnt. Mitglieder sehen in ihrem Bereich das kleinere von persönlicher Quote und verbleibendem Gesamtplatz.

Das Limit steht **absichtlich nicht im Admin-Panel**: Wer es dort ändern könnte, hätte keins. Im Panel gibt es unter **System → Speicherbelegung** nur die Anzeige — Balken, Gesamtwert und eine Aufschlüsselung nach Bereichen (Bilder, PDFs, Mitglieder-Dateien, Sicherungen …), damit man sieht, was den Platz frisst. Bei mehreren Instanzen setzt du je Stack einen eigenen Wert.

### Seite im Aufbau ansehen (Vorschau-Link)

Im Wartungsmodus antwortet jede öffentliche Adresse mit 503, und abgeschaltete Bereiche mit 404 — auch für dich. Unter **System → Betrieb → Vorschau-Link** erzeugst du deshalb eine Adresse, die genau das aufhebt:

```
https://deine-domain.de/?vorschau=<token>
```

Beim ersten Aufruf wandert der Token in einen Cookie und aus der Adresse heraus. Ab da siehst du die echte Seite mit Navigation und Unterseiten — inklusive der Bereiche, die unter Design auf NEIN stehen. Alle anderen sehen weiterhin die Wartungsseite.

Ein schmaler Balken unten erinnert daran, dass die Vorschau läuft, und beendet sie auf Klick. Gültigkeit wählbar (1 Stunde, 8 Stunden, 7 Tage), Antworten tragen `noindex, nofollow` und `private, no-store`, eigene Aufrufe zählt der Besucherzähler nicht mit. *Alle Links zurückziehen* macht jede ausgegebene Adresse sofort ungültig.

Der Link ist teilbar — Vorstand, Kunde oder Partner können vor dem Livegang draufschauen, ohne Zugang zum Admin.

### `options.json` — optional

Wird nicht mehr für den Login gebraucht. Wer sie mountet (nach `/data/options.json`, read-only), kann darin noch zwei Dinge setzen:

| Schlüssel | Bedeutung | Standard |
|---|---|---|
| `session_hours` | Gültigkeit der Admin-Sitzung in Stunden | `24` |
| `trusted_proxies` | Adressen, deren Weiterleitungs-Kopfzeilen geglaubt werden | alle privaten Netze |

Wer aus einer älteren Fassung kommt und dort `username`/`password` stehen hatte: Beim ersten Start nach dem Update übernimmt MyPage die Daten gehasht nach `admin_login.json`, die Anmeldung bleibt also unverändert. Danach sind die beiden Einträge wirkungslos und die Datei kann entfallen.

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
2. Den Ordner **`./data`** sichern (enthält zusätzlich Uploads, Mitglieder-Dateien, `settings.key` und `admin_login.json`) — dieser Ordner gehört an einen sicheren Ort.

---

## Sicherheitshinweise

- **Startpasswort ersetzen**: Das erzeugte Passwort steht im Container-Protokoll, und Protokolle werden weitergereicht, gesammelt und archiviert. Unter *System → Zugang* ein eigenes setzen — ohne Ingress schützt nur dieses Login das Admin-Panel.
- **`data/admin_login.json` liegt im Datenordner**, damit man sich per SSH aussperren *und* wieder hereinlassen kann. Wer Dateizugriff auf den Server hat, kann den Zugang also zurücksetzen — bei einem gemieteten Server heißt das: dem Anbieter vertrauen oder verschlüsseltes Dateisystem verwenden.
- `./data/settings.key` entschlüsselt alle gespeicherten Zugangsdaten: Datei nicht weitergeben und nicht in ein öffentliches Repository legen.
- Admin-Panel **nur über HTTPS** erreichbar machen (Caddy/Cloudflare Tunnel).
- **Brute-Force-Schutz**: fünf Fehlversuche je Adresse sperren diese für 15 Minuten, zwanzig Fehlversuche je Verbindung sperren die Gegenstelle. Bis 0.11.29 zählte nur die erste Sperre — und die Adresse stammte aus einer Kopfzeile, die jeder selbst setzen kann; durch Weiterdrehen war sie wirkungslos. **Mit älteren Fassungen als 0.11.30 darf der Admin-Port nicht öffentlich erreichbar sein.**
- **Ohne Ingress ist der Ingress-Weg gar nicht vorhanden**: `_is_ingress()` ist unter Docker immer falsch, es gilt ausnahmslos das Login. Die Option `ingress_trust_net` bleibt **leer** — wer dort das Docker-Bridge-Netz einträgt, lässt jeden Container ohne Anmeldung in den Admin.
- **2FA einschalten** (Admin → System → Zugang). Sie gilt für den direkten Login, also für den einzigen Weg, den es hier gibt. Der Notausgang „über Home Assistant anmelden und 2FA abschalten" existiert unter Docker **nicht** — Backup-Codes aufbewahren; im Notfall hilft nur, `data/admin_2fa.json` zu löschen.
- Das Admin-Panel **nicht ohne Not öffentlich exponieren**: In der Beispiel-Compose steht bewusst `expose: 17761` statt `ports:`, erreichbar ist es damit nur für Caddy im internen Netz. Wenn es doch nach außen muss: eigene Subdomain, zusätzlich Firewall, Basic-Auth, CrowdSec oder fail2ban davor — oder nur an `127.0.0.1` binden und per SSH-Tunnel bzw. VPN darauf zugreifen.
- **`trusted_proxies`** (optional): Standardmäßig gelten alle privaten Adressen als Zwischenglied, deren Weiterleitungs-Kopfzeilen geglaubt werden. Steht der Proxy fest, trag ihn dort ein (z. B. `172.18.0.0/16`) — dann darf wirklich nur er eine Besucheradresse melden.
