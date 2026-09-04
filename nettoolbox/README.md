# NetToolbox

**Netzwerk- und Mail-Diagnose für Home Assistant** · [English](README.en.md)

DNS-Abfragen, Propagationscheck, Reverse-DNS, DNSSEC und ein vollständiger
Mail-Gesundheitscheck (SPF/DKIM/DMARC/MTA-STS/TLS-RPT/BIMI) — ohne fremde API
und ohne die eigenen Daten an einen Drittanbieter zu schicken.

## Funktionen

- **DNS** — alle gängigen Record-Typen, alle Standard-Typen in einem Rutsch, TXT, SOA mit
  Nameserver-Sync-Check
- **Mail-Gesundheit** — SPF (inklusive Lookup-Zähler und Include-Kette), DKIM (Schlüsselstärke,
  Selektoren werden geraten), DMARC (Richtlinie, Berichtsadressen, Fremd-Domain-Autorisierung),
  MTA-STS (Policy gegen echte MX-Einträge geprüft), TLS-RPT, BIMI — mit eigenem 0–100-Punktestand
- **Propagation** — dieselbe Abfrage gegen acht öffentliche Resolver gleichzeitig
- **Reverse-DNS / MX** — PTR mit Vorwärts-Abgleich, MX-Server mit Adressen und Reverse-Namen
- **Sperrlisten** — eine IP gegen 15 öffentliche DNSBL/RBL parallel geprüft, mit Begründungstext
- **SSL/TLS** — Zertifikatskette, Ablaufdatum, Hostname-Abdeckung, ausgehandelte TLS-Version
- **Whois/RDAP** — Registrar, Registrierungs-/Ablaufdatum, Nameserver; RDAP zuerst, WHOIS-Fallback für Endungen ohne RDAP (z. B. .de)
- **HTTP-Header** — Weiterleitungskette, Security-Header, HTTP/3-Ankündigung (Alt-Svc)
- **SMTP** — Domain genügt, der Mailserver wird über den MX-Eintrag selbst ermittelt; Banner,
  EHLO-Fähigkeiten, STARTTLS, Offene-Relais-Test (liefert nie tatsächlich Mail aus)
- **Anbieter-/Software-Erkennung** — Betreiber aus den MX-Namen (Microsoft 365, Google, IONOS, STRATO …), MTA-Software aus dem SMTP-Banner (Postfix, Exim, Exchange …)
- **HTTP/3 (QUIC)** — echter Handschlag über UDP/443, nicht nur die Alt-Svc-Ankündigung
- **Ping / Traceroute** — über die System-Werkzeuge im Container
- **IP-Lookup** — Standort, Anbieter und AS-Nummer einer IP (ip-api.com), inkl. eigener öffentlicher IP
- **DNSSEC** — DS/DNSKEY-Status, ob der Resolver die Antwort validiert (AD-Flag)
- **Monitoring** — Domains/IPs automatisch im gewählten Abstand prüfen (TLS-Ablauf, Sperrlisten,
  Mail-Gesundheit), Benachrichtigung per Mail oder Telegram bei Zustandswechsel; SMTP/Telegram
  über das Zahnradsymbol im Header eingerichtet, nicht über die Add-on-Optionen
- **Root-Server-Worker** *(optional)* — eine Heim-Instanz kann ihre Prüfungen an eine zweite
  Instanz auf einem Root-Server durchreichen, wo Port 25 offen ist und Sperrlisten antworten.
  Wer NetToolbox ohnehin auf dem Root-Server betreibt, braucht das nicht — siehe
  [Brauche ich den Root-Server-Worker?](#brauche-ich-den-root-server-worker)
- Verlauf, Rate-Limit, Dark/Light · DE/EN · HA Ingress

## Schnellstart

1. Add-on installieren, `password` in den Optionen ändern
2. Fertig — alle Prüfungen laufen sofort. Die Worker-Optionen sind **optional** und werden
   nur in dem Sonderfall gebraucht, den der nächste Abschnitt beschreibt.

## Ports

| Port | Funktion |
|------|----------|
| 17798 | NetToolbox Web-UI (direkt, Anmeldung erforderlich) |

## Brauche ich den Root-Server-Worker?

Kurze Antwort: **meistens nicht.** Der Worker löst genau ein Problem, und zwar das eines
gewöhnlichen Heimanschlusses:

- **Port 25 ausgehend gesperrt** — die meisten Provider sperren ihn, SMTP-Tests sind dann
  unmöglich.
- **Sperrlisten antworten nicht** — Spamhaus und andere DNSBL beantworten Abfragen von
  Consumer-IPs und großen öffentlichen Resolvern oft gar nicht.

Steht ein Root-Server mit fester IPv4 und offenem Port 25 zur Verfügung, kann eine zweite
NetToolbox-Instanz dort die Prüfungen übernehmen — die Heim-Instanz fragt, der Root-Server führt
aus.

**Die Entscheidung in einem Satz:**

| Aufbau | Was einzutragen ist |
|--------|---------------------|
| Nur eine Instanz, egal wo (auch direkt auf dem Root-Server) | **nichts.** Alle `worker_*`-Optionen leer bzw. `false` lassen — die Statusanzeige steht auf „Lokal", und das ist der gewünschte Zustand |
| Heim-Instanz **und** eine zweite auf dem Root-Server | beide Seiten eintragen, siehe unten |

Wer NetToolbox ohnehin direkt auf dem Root-Server betreibt, prüft bereits von genau der Leitung
aus, um die es geht. Es gibt dann nichts weiterzureichen.

### Einrichtung, wenn beide Instanzen laufen

Der Token ist der einzige Zugangsschutz, deshalb muss er auf **beiden** Seiten stehen. Ohne
`worker_enabled` sind die Endpunkte `/worker/info` und `/worker/probe` abgeschaltet und
antworten mit `worker_disabled` — der Client bekommt dann nur einen Fehler.

**1. Auf dem Root-Server** (die Instanz, die die Arbeit macht):

```json
"worker_enabled": true,
"worker_token": "<Ausgabe von: openssl rand -hex 32>"
```

**2. Zuhause im Home-Assistant-Add-on** (die Instanz, die fragt) unter *Einstellungen → Add-ons
→ NetToolbox → Konfiguration*:

| Option | Wert |
|--------|------|
| `worker_url` | Basisadresse des Root-Servers **ohne Pfad**, z. B. `https://nettoolbox.example.com` |
| `worker_token` | derselbe Zufallswert wie oben |
| `worker_tls_verify` | `true` lassen, solange ein echtes Zertifikat vorhanden ist |
| `worker_enabled` | bleibt hier `false` — die Heim-Instanz ist Client, nicht Worker |

Die Statusanzeige im Kopf zeigt danach „Worker verbunden" (zuhause) beziehungsweise
„Worker-Modus" (auf dem Root-Server).

> **Sicherheit:** Der Token geht als Kopfzeile `X-Nettoolbox-Token` bei jeder Anfrage mit. Über
> reines `http://` läuft er im Klartext durchs Internet, und wer ihn hat, kann den Root-Server
> als Scanner benutzen. Den Worker deshalb hinter einen Reverse-Proxy mit TLS stellen, statt
> Port 17798 offen ins Netz zu hängen.

## Standalone (ohne Home Assistant, z. B. mit Dockge)

Dasselbe Image läuft auch ohne Supervisor — siehe [docker-compose.yml](docker-compose.yml):

```sh
docker compose up -d
```

Beim ersten Start legt NetToolbox `data/options.json` selbst an, mit einem zufällig erzeugten
Passwort für den Benutzer `admin`. **Dieses Passwort steht nur in der Datei und niemals im
Protokoll** — Container-Logs sind zu leicht einsehbar und werden zu lange aufbewahrt:

```sh
cat ./data/options.json
```

Alle Optionen aus dem Abschnitt oben werden hier in derselben Datei gesetzt, mit denselben
Namen. Änderungen greifen sofort, ein Neustart ist nicht nötig: die Datei wird bei jeder
Änderung ihres Zeitstempels neu eingelesen.

Da Passwort und Token im Klartext darin stehen: `chmod 600 ./data/options.json`.

### Mit Dockge, Schritt für Schritt

Dockge legt jeden Stack unter `/opt/stacks/<stackname>/` ab. Das `./data`-Volume aus der
Compose-Datei landet damit in `/opt/stacks/nettoolbox/data/`.

1. In Dockge einen neuen Stack `nettoolbox` anlegen und den Inhalt von
   [docker-compose.yml](docker-compose.yml) einfügen, dann **Deploy**.
2. Beim ersten Start entsteht `/opt/stacks/nettoolbox/data/options.json` mit einem zufälligen
   Passwort für `admin`.
3. Diese Datei öffnen — über das **Terminal**, das Dockge zu jedem Stack anbietet (es startet im
   Stack-Verzeichnis auf dem Host), oder per SSH:
   ```sh
   cat /opt/stacks/nettoolbox/data/options.json     # Passwort ablesen
   vi  /opt/stacks/nettoolbox/data/options.json     # bearbeiten
   ```
4. Rechte einschränken, denn Passwort und Token stehen im Klartext darin:
   ```sh
   chmod 600 /opt/stacks/nettoolbox/data/options.json
   ```
5. Anmelden auf `http://<server>:17798` mit `admin` und dem abgelesenen Passwort.

### Worker-Optionen in der options.json setzen

Nur nötig, wenn zusätzlich eine Heim-Instanz existiert, die ihre Prüfungen hierher durchreichen
soll — siehe [Brauche ich den Root-Server-Worker?](#brauche-ich-den-root-server-worker). Diese
Instanz ist dann die **ausführende** Seite:

Zuerst einen Schlüssel erzeugen:

```sh
openssl rand -hex 32
```

Dessen Ausgabe kommt in `worker_token`:

```json
{
  "username": "admin",
  "password": "<dein Passwort>",
  "worker_enabled": true,
  "worker_token": "<die 64 Zeichen von openssl>",
  "worker_url": ""
}
```

`worker_url` bleibt hier leer — die Adresse wird auf der *fragenden* Seite eingetragen, also im
Home-Assistant-Add-on. Speichern genügt, ein Neustart des Stacks ist nicht nötig.

Soll es umgekehrt diese Standalone-Instanz sein, die ihre Prüfungen an einen Worker abgibt,
stehen hier stattdessen `worker_url` und `worker_token`, und `worker_enabled` bleibt `false`.
