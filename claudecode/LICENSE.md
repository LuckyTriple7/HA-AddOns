# Lizenzen — Claude-Code-Add-on

Dieses Add-on besteht aus eigenem Code und einer ganzen Reihe mitgelieferter Fremdbestandteile mit sehr unterschiedlichen Lizenzen — darunter **ein proprietärer**.

## Eigene Dateien

`config.yaml`, `Dockerfile`, `run.sh`, `mobile-scroll.js`, `translations/`, Symbole und die Markdown-Dateien in diesem Verzeichnis stammen aus diesem Repository und stehen unter der **MIT-Lizenz** (siehe [LICENSE](../LICENSE) im Wurzelverzeichnis).

## Claude Code CLI — proprietär

Der Dockerfile installiert `@anthropic-ai/claude-code` beim Bau des Images. Das Paket ist **nicht quelloffen**. Die Lizenzdatei des Projekts lautet vollständig:

> © Anthropic PBC. All rights reserved. Use is subject to Anthropic's [Commercial Terms of Service](https://www.anthropic.com/legal/commercial-terms).

- Projekt: <https://github.com/anthropics/claude-code>
- Paket: <https://www.npmjs.com/package/@anthropic-ai/claude-code> (Dist-Tag `stable`)

**Offener Punkt:** „All rights reserved" erteilt keine Erlaubnis zur Weitergabe. Die Commercial Terms of Service regeln die Nutzung der Dienste und enthalten keine ausdrückliche Klausel zur Weitergabe der Software; sie untersagen in Abschnitt D.4 den Weiterverkauf ohne Zustimmung. Ob das Mitliefern des Pakets in einem öffentlichen Container-Image gedeckt ist, ist damit **nicht abschließend geklärt**.

Die sichere Variante wäre, Claude Code nicht ins Image zu backen, sondern beim ersten Start aus der npm-Registry nach `/homeassistant/.claudecode/npm-global` zu installieren — dorthin schreibt bereits die Aktualisierungsfunktion des Add-ons, und der `PATH` bevorzugt diesen Pfad schon heute. Jede Installation käme dann direkt von Anthropic, dieses Repository gäbe nichts weiter.

Unabhängig davon gilt: Wer das Add-on benutzt, benutzt Claude Code unter Anthropics Bedingungen und braucht ein eigenes Konto.

## ttyd — verändert ausgeliefert

Das Web-Terminal [ttyd](https://github.com/tsl0922/ttyd) steht unter der **MIT-Lizenz**. Das Binary wird als offizielles Release eingebunden und über SHA256 geprüft (Fassung: `ARG TTYD_VERSION` im [Dockerfile](Dockerfile)).

**Änderung:** ttyd liefert seine Oberfläche als einzelne `index.html` aus. Der Build holt diese Seite von einer kurzlebigen ttyd-Instanz und fügt vor `</body>` das eigene `mobile-scroll.js` ein. Ausgeliefert wird also eine **veränderte** Fassung der ttyd-Oberfläche; das Binary selbst bleibt unverändert. Die MIT-Lizenz erlaubt das und verlangt lediglich, den Copyright-Vermerk zu erhalten.

## mbpoll — aus dem Quelltext gebaut

[mbpoll](https://github.com/epsilonrt/mbpoll) steht unter der **GPL-3.0** und wird im Build aus dem Quelltext übersetzt und ins Image gelegt.

> **Hinweis zur Nachvollziehbarkeit:** Der Dockerfile klont den Standard-Zweig ohne festen Stand. Welche Fassung in einem bestimmten Image steckt, verrät `mbpoll --version` im laufenden Container.

## Weitere gebündelte Software

| Bestandteil | Lizenz | Quelltext |
|---|---|---|
| **Caveman-Skills und -Agents** (`skills/`, `agents/`) | MIT | <https://github.com/JuliusBrussee/caveman> — Fassung und Vorgehen in [skills/UPSTREAM.md](skills/UPSTREAM.md), Lizenztext in [skills/LICENSE](skills/LICENSE) |
| **Hass-MCP** | MIT | <https://github.com/voska/hass-mcp> |
| **pymodbus**, **pyserial** | BSD-3-Clause | <https://github.com/pymodbus-dev/pymodbus>, <https://github.com/pyserial/pyserial> |
| **@playwright/mcp** (nur im npx-Cache) | Apache-2.0 | <https://github.com/microsoft/playwright-mcp> |
| **Home Assistant CLI** (`ha`) | Apache-2.0 | <https://github.com/home-assistant/cli> |
| **hab** (`home-assistant-build-cli`) | **keine Lizenzangabe im Projekt** | <https://github.com/balloob/home-assistant-build-cli> |

> **Offener Punkt bei `hab`:** Das Projekt nennt keine Lizenz. Ohne Lizenzangabe gilt das Urheberrecht ohne Einschränkung — eine Erlaubnis zur Weitergabe ist damit ebenfalls nicht erteilt. Wie bei Claude Code wäre ein Bezug zur Laufzeit statt eines Mitlieferns im Image der saubere Weg. Zusätzlich zieht der Dockerfile `releases/latest`, die enthaltene Fassung ist also nicht festgelegt.

## Betriebssystem-Pakete

Das Image basiert auf `python:3.14-alpine3.21`. Aus den Alpine-Paketquellen kommen unter anderem:

| Paket | Lizenz |
|---|---|
| `coreutils`, `findutils`, `grep`, `sed`, `gawk`, `nano` | GPL-3.0-or-later |
| `git` | GPL-2.0-only |
| `socat` | GPL-2.0-only WITH OpenSSL-Exception |
| `libmodbus` | LGPL-2.1-or-later |
| `docker-cli` | Apache-2.0 |
| `github-cli` | MIT |
| `ripgrep` | MIT OR Unlicense |
| `tmux` | ISC |
| `ncurses` | X11 |
| `vim` | Vim-Lizenz |
| `openssh-client` | SSH-OpenSSH |

Weitere Pakete (`bash`, `curl`, `jq`, `nodejs`, `npm`, `openssl`, `ca-certificates`, `p7zip`, `libstdc++`, `gcompat`) haben jeweils eigene Lizenzen. Die genaue Fassung und Lizenz eines Pakets im laufenden Container zeigt `apk info -L <paket>`; die Quelltexte liegen in den [aports](https://gitlab.alpinelinux.org/alpine/aports).

## Was das für das veröffentlichte Image bedeutet

`ghcr.io/luckytriple7/claudecode` ist **kein MIT-Image**. Es enthält:

- **proprietäre Software ohne erteilte Weitergabeerlaubnis** (Claude Code, `hab`),
- **Copyleft-Software** (mbpoll unter GPL-3.0, dazu die GNU-Werkzeuge der Alpine-Basis),
- permissiv lizenzierte Bestandteile und den eigenen MIT-Code.

Die eigenen Dateien bleiben MIT-lizenziert. Für alle anderen Bestandteile gelten deren Bedingungen; die Bezugsquellen der Quelltexte sind oben genannt.

## Kein Zusammenhang mit Anthropic

Dieses Add-on wird unabhängig gepflegt. Anthropic betreibt es nicht und unterstützt es nicht. „Claude" und „Anthropic" sind Marken der Anthropic PBC.

Fehlerberichte zum Add-on — Startskript, Optionen, Web-Terminal — gehören in [dieses Repository](https://github.com/LuckyTriple7/HA-AddOns/issues). Fehler in Claude Code selbst gehören zum [Projekt](https://github.com/anthropics/claude-code/issues).
