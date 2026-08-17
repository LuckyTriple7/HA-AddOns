# Backlog — Claude Code

Ideen, die nicht dringend sind. Kein Zeitplan.

## Claude Code und `hab` erst zur Laufzeit installieren

Beide Programme werden derzeit beim **Bau** ins Image gelegt, das öffentlich auf ghcr.io liegt — und für beide ist keine Weitergabeerlaubnis erteilt:

- **Claude Code** — die Lizenzdatei des Projekts lautet vollständig „© Anthropic PBC. All rights reserved. Use is subject to Anthropic's Commercial Terms of Service." Die Terms regeln die Nutzung der Dienste; eine Klausel zur Weitergabe der Software steht nicht darin, Abschnitt D.4 untersagt lediglich Weiterverkauf ohne Zustimmung. Ob das Mitliefern in einem öffentlichen Image gedeckt ist, ist ungeklärt.
- **`hab`** (`balloob/home-assistant-build-cli`) — das Projekt nennt überhaupt keine Lizenz. Ohne Lizenzangabe gilt das Urheberrecht ungeschmälert.

Einzelheiten stehen in [LICENSE.md](LICENSE.md).

Wird beides erst beim ersten Start geholt, enthält das veröffentlichte Image keinen fremden Code mehr, für den die Erlaubnis fehlt. Jede Installation käme direkt vom jeweiligen Anbieter — dasselbe Muster, das `ubuntu-webtop` bei VS Code sauber hält (kein `image:` in der config.yaml, lokaler Bau).

### Die Hälfte der Arbeit ist schon getan

Der Weg für Claude Code existiert bereits, er wird nur noch nicht beim ersten Start benutzt:

- `claude update` und der Alias `claude-update` installieren nach `/homeassistant/.claudecode/npm-global`
- der `PATH` in `.bashrc` stellt genau diesen Pfad nach vorne
- `/homeassistant` ist über Neustarts und Add-on-Updates hinweg beständig, die Installation überlebt also

Zu tun wäre also im Wesentlichen:

1. `RUN npm install -g @anthropic-ai/claude-code@stable` aus dem [Dockerfile](Dockerfile) entfernen, ebenso den `curl`-Aufruf für `hab`
2. In `run.sh` beim Start prüfen, ob beide vorhanden sind, und sie andernfalls nachinstallieren — mit Fortschrittsmeldung im Add-on-Protokoll, der erste Start dauert dadurch spürbar länger
3. Den Durchreich-`sudo` und `DISABLE_AUTOUPDATER` behalten, das Postinstall-Skript von Claude Code läuft dann zur Laufzeit
4. `org.opencontainers.image.licenses` im Dockerfile wieder verkleinern, sobald der proprietäre Anteil raus ist

### Was dagegen spricht

- **Der erste Start braucht Netz.** Ohne Verbindung zur npm-Registry startet das Add-on ohne Claude Code. Heute liegt es im Image und funktioniert offline.
- **Der erste Start dauert länger** — spürbar auf schwacher Hardware.
- **Die Fassung ist nicht mehr im Image festgeschrieben.** Zwei Nutzer, die dasselbe Add-on-Update einspielen, können unterschiedliche Claude-Code-Fassungen bekommen. Für die Fehlersuche unschön; `claude --version` im Protokoll auszugeben wäre dann Pflicht.
- **Eine neue Fehlerquelle**: schlägt die Installation fehl, muss das Add-on das verständlich melden, statt mit „command not found" zu starten.

Alternative mit weniger Bruch: nur `hab` zur Laufzeit holen (klein, ein einzelnes Binary) und für Claude Code erst einmal bei Anthropic nachfragen, ob das Mitliefern im Image in Ordnung geht. Eine Antwort erspart den ganzen Umbau.

## Feste Stände statt beweglicher Verweise

Drei Bestandteile werden ohne festgelegte Fassung geholt — in einem bestimmten Image steckt damit nicht nachvollziehbar, was drin ist:

| Bestandteil | Derzeit | Warum es stört |
|---|---|---|
| **mbpoll** | `git clone` des Standard-Zweigs | GPL-3.0; zum Quelltext-Angebot gehört der passende Stand |
| **`hab`** | `releases/latest` | Fassung wechselt zwischen zwei Builds unbemerkt |
| **Home Assistant CLI** | `releases/latest` | dito |

`ttyd` macht es bereits richtig vor: feste Version und SHA256-Prüfung im [Dockerfile](Dockerfile).
