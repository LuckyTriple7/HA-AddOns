# ReactorSim in Dockge betreiben

ReactorSim ist ein gewöhnlicher Container ohne Abhängigkeiten: kein Datenbank-
Server, kein Cache, kein zweiter Dienst. Das fertige Image liegt unter
`ghcr.io/luckytriple7/reactorsim` für **amd64 und arm64**. Den Quellcode
brauchst du nicht.

In Dockge ist das ein Stack. Lege ihn an, füge die Datei unten ein, starten.

```
/opt/stacks/reactorsim/
├── compose.yaml
└── data/            legt sich beim ersten Start selbst an
```

---

## Die Datei

`/opt/stacks/reactorsim/compose.yaml`:

```yaml
services:
  reactorsim:
    image: ghcr.io/luckytriple7/reactorsim:latest
    container_name: reactorsim
    restart: unless-stopped

    ports:
      # links der Port auf dem Server, rechts der im Container.
      # Nur die linke Seite darfst du ändern — innen hört der Dienst fest
      # auf 17779, und der Healthcheck unten prüft genau den.
      - "17779:17779"

    volumes:
      # Spielstände und Bestenliste. Mehr legt ReactorSim nicht ab.
      - ./data:/data

    environment:
      # Zugang. Ohne gesetztes Passwort erzeugt ReactorSim beim ersten Start
      # eines und schreibt es ins Protokoll — offen steht die Seite nie.
      - REACTORSIM_USER=admin
      - REACTORSIM_PASSWORD=bitte-aendern
      # Nur für die Zeitstempel in den Protokollzeilen.
      - TZ=Europe/Berlin

    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:17779/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

    # Auf einem Mietserver läuft sonst irgendwann die Platte mit Protokollen
    # voll. Drei Dateien à 10 MB reichen für jede Fehlersuche.
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Danach `http://<server>:17779`.

---

## Zugang

Ein Konto, Zugangsdaten aus der Konfiguration:

| Variable | Vorgabe | Bedeutung |
|---|---|---|
| `REACTORSIM_USER` | `admin` | Benutzername |
| `REACTORSIM_PASSWORD` | — | Passwort. Fehlt es, wird eines erzeugt |

Ist kein Passwort gesetzt, erzeugt ReactorSim beim ersten Start ein zufälliges,
schreibt es **einmal** ins Protokoll und legt nur den Hash in `./data/auth.json`
ab:

```bash
docker compose logs reactorsim | grep -A 3 "Passwort"
```

Ein gesetztes `REACTORSIM_PASSWORD` gewinnt immer gegen die gespeicherte
Fassung — ändern heißt also: Wert in Dockge ändern, Stack neu starten, fertig.

Die Anmeldung hält 30 Tage in einem HttpOnly-Cookie. Abmelden über den Link
unten auf dem Startbildschirm. Gegen Durchprobieren sind zehn Versuche je
Minute und Absenderadresse erlaubt.

Mehrbenutzerbetrieb kommt später; im Moment ist es ein Konto für alle, die den
Zugang kennen.

---

## Hinter einem Reverse Proxy

Empfohlen, sobald der Server aus dem Internet erreichbar ist. Dann soll der
Port **nicht** offen im Netz stehen, sondern nur lokal — der Proxy holt ihn
sich von dort:

```yaml
    ports:
      - "127.0.0.1:17779:17779"
```

Im Proxy (NPMplus, Nginx Proxy Manager, Caddy, Traefik) ein normales
HTTP-Ziel auf `127.0.0.1:17779`. Zu beachten ist nichts Besonderes:

- **Keine WebSockets.** Die Simulation läuft im Browser; der Server liefert nur
  die Seite und ein paar kleine JSON-Antworten.
- **Keine Sticky Sessions**, kein Zustand im Server-Speicher.
- **Latenz ist gleichgültig.** Zwischen Browser und Server geht nach dem Laden
  fast nichts mehr hin und her — ein Reaktor auf einem Server in Finnland fährt
  sich genauso flüssig wie einer auf dem Rechner nebenan.

Läuft der Proxy in einem eigenen Container statt im Host-Netz, muss stattdessen
ein gemeinsames Docker-Netz her:

```yaml
services:
  reactorsim:
    image: ghcr.io/luckytriple7/reactorsim:latest
    container_name: reactorsim
    restart: unless-stopped
    volumes:
      - ./data:/data
    networks:
      - proxy
    # ports entfällt komplett — der Proxy erreicht den Container über das Netz
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:17779/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  proxy:
    external: true
```

Im Proxy zeigt das Ziel dann auf `http://reactorsim:17779` — auf den
Containernamen, nicht auf eine IP. Docker vergibt die IP bei jedem Neustart
neu, der Name bleibt.

---

## Version festnageln statt `latest`

`latest` holt beim nächsten `docker compose pull` die neueste Fassung. Wenn du
lieber selbst bestimmst, wann sich etwas ändert:

```yaml
    image: ghcr.io/luckytriple7/reactorsim:0.0.13
```

Verfügbare Marken siehst du unter
`https://github.com/LuckyTriple7?tab=packages`.

Aktualisieren in Dockge: **Update** am Stack, oder auf der Kommandozeile

```bash
cd /opt/stacks/reactorsim
docker compose pull && docker compose up -d
```

Der Datenordner bleibt dabei unberührt.

---

## Daten und Sicherung

Unter `./data` liegen:

```
data/
├── auth.json             Hash des erzeugten Passworts (0600)
├── secret.key            Signierschlüssel der Sitzungen (0600)
├── highscores.json       Bestenliste
└── players/<token>/      Spielstände je Gerät
```

`auth.json` und `secret.key` gehören in die Sicherung, sonst muss nach dem
Zurückspielen jeder neu anmelden — und ohne `auth.json` gilt ein erzeugtes
Passwort nicht mehr. Wer `REACTORSIM_PASSWORD` setzt, ist davon unabhängig.

Sichern heißt: den Ordner `data` kopieren. Es gibt keine Datenbank, die vorher
angehalten werden müsste — geschrieben wird atomar (erst daneben, dann
umbenannt), ein Kopiervorgang im laufenden Betrieb erwischt nie eine halbe
Datei.

Personenbezogene Daten entstehen keine: ein Spieler wird über ein zufälliges
Token im Cookie wiedererkannt, gespeichert wird nur, was er selbst in die
Bestenliste einträgt.

---

## Ressourcen

Der Container braucht im Leerlauf rund 60 MB Arbeitsspeicher und praktisch
keine CPU — die Physik rechnet der Browser des Spielers, nicht der Server. Ein
Server mit 1 GB RAM trägt ihn mühelos neben allem anderen.

Wer es begrenzen will:

```yaml
    deploy:
      resources:
        limits:
          memory: 256M
```

---

## Mehrere Instanzen

ReactorSim kennt keine Instanzsperre. Mehrere Stacks nebeneinander brauchen nur
je einen eigenen Host-Port, einen eigenen `container_name` und einen eigenen
Ordner — `./data` zeigt in Dockge automatisch in den jeweiligen Stack-Ordner.

```
/opt/stacks/
├── reactorsim/       compose.yaml  data     Port 17779
└── reactorsim-test/  compose.yaml  data     Port 17780
```

---

## Wenn es nicht läuft

```bash
cd /opt/stacks/reactorsim
docker compose logs --tail 50 reactorsim
curl -s http://127.0.0.1:17779/health
```

Beim Start steht genau eine Zeile im Protokoll:

```
[INFO] [2026-09-11 15:33:52] ReactorSim 0.0.10 laeuft auf Port 17779
```

Kommt sie nicht, ist der Container gar nicht hochgekommen — dann sagt
`docker compose logs` warum. Antwortet `/health` mit
`{"status":"ok","version":"…"}`, läuft der Dienst, und ein Problem liegt
zwischen Browser und Server (Port, Firewall, Proxy).
