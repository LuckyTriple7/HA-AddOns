# Claude Code

Claude Code — KI-Coding-Assistent von Anthropic — direkt in der Home Assistant Seitenleiste.

## Einrichtung

1. Add-on starten
2. In der HA-Sidebar auf **Claude Code** klicken
3. `claude` eingeben und dem Authentifizierungsablauf folgen
4. Zugangsdaten werden dauerhaft gespeichert — kein API-Key in der Konfiguration nötig

## Schnellstart

```bash
claude "Liste alle meine Automationen auf"
claude "Erstelle eine Automation die bei Sonnenuntergang das Licht einschaltet"
claude "Warum funktioniert meine Bewegungsmelder-Automation nicht?"
claude --continue   # letzte Unterhaltung fortsetzen
```

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `enable_mcp` | `true` | HA-Integration aktivieren (Entitäten abfragen, Dienste steuern) |
| `terminal_font_size` | `14` | Schriftgröße im Terminal (10–24) |
| `terminal_theme` | `dark` | Terminal-Theme: `dark` oder `light` |
| `session_persistence` | `true` | tmux verwenden — Session überlebt Browser-Reload |
| `tmux_scroll_mode` | `browser` | Scroll-Verhalten mit tmux: `browser` (natives Scrollen/Touch/Copy-Paste) oder `tmux` (Mausrad scrollt tmux-Historie) |
| `mobile_scroll_ui` | `true` | Wisch-Scrollen und Scroll-Knöpfe auf Touch-Geräten (Handy/Tablet/HA App) |
| `claude_autostart` | `false` | Claude beim Öffnen des Terminals automatisch starten |
| `auto_update_claude` | `true` | Claude Code beim Start automatisch aktualisieren |
| `model` | `claude-sonnet-5` | Zu verwendendes Claude-Modell |
| `enable_playwright_mcp` | `false` | Playwright Browser-MCP aktivieren (benötigt Playwright Browser Add-on) |
| `export_memory` | `false` | Claude-Speicher in `/config/memory/` exportieren |
| `export_memory_interval` | `60` | Export-Intervall in Minuten |
| `enable_caveman_skill` | `false` | Optionale "Caveman"-Skills (knappe Antworten) installieren — 7 Skills + 3 Subagenten |
| `enable_direct_access` | `false` | Terminal zusätzlich auf Port 7683 anbieten, am Ingress vorbei ([Details](#direkter-browser-zugriff-port-7683)) |
| `direct_username` | `admin` | Benutzername für Port 7683 |
| `direct_password` | — | Passwort für Port 7683 — leer heißt: Port startet nicht |

## Modellauswahl

| Modell | Für was |
|--------|---------|
| `claude-sonnet-5` | Beste Balance (Standard) |
| `claude-fable-5` | Leistungsstärkstes Modell, für die schwierigsten Aufgaben |
| `claude-opus-5` | Sehr stark, für komplexe Aufgaben |
| `claude-haiku-4-5-20251001` | Schnellstes Modell, für einfache Anfragen |

## Tastenkürzel

| Kürzel | Befehl |
|--------|--------|
| `c` | `claude` starten |
| `cc` | `claude --continue` (letzte Unterhaltung fortsetzen) |
| `ha-config` | Zum HA-Konfigurationsverzeichnis wechseln |
| `ha-logs` | Home Assistant Logs anzeigen |
| `claude-update` | Claude Code manuell aktualisieren |

## Dateipfade

| Pfad | Zugriff |
|------|---------|
| `/homeassistant` | HA-Konfiguration (Lesen/Schreiben) |
| `/share` | Freigegebener Ordner (Lesen/Schreiben) |
| `/media` | Medienordner (Lesen/Schreiben) |
| `/ssl` | SSL-Zertifikate (Nur Lesen) |
| `/backup` | Backups (Nur Lesen) |

## Home Assistant Builder CLI (`hab`)

Neben dem `homeassistant` MCP-Server steht auch [`hab`](https://github.com/balloob/home-assistant-build-cli) zur Verfügung — ein CLI-Tool speziell für LLM-Nutzung, gedacht für Admin-Operationen, die über einfache Entity-Abfragen hinausgehen: Dashboard-CRUD, Area-/Floor-/Label-Verwaltung, Helper-Erstellung, Backup/Restore. Authentifizierung läuft automatisch über den Supervisor-Token — keine Einrichtung nötig.

```bash
hab guide                     # verfügbare Befehle entdecken
hab schema <command> --json   # Vertrag eines Befehls prüfen
hab <command> --plan --json   # Mutation vorab als Vorschau prüfen
```

Beim Start des Add-ons wird zusätzlich ein Home-Context-Snapshot (`hab overview`) in die CLAUDE.md geschrieben — Claude kennt so von Anfang an Anzahl der Areas, Entities, Automationen etc., ohne erst danach fragen zu müssen.

## Schutzregeln

Die CLAUDE.md enthält verbindliche Regeln für den Umgang mit deiner Installation. Die wichtigste: **niemals in die internen Verzeichnisse von Home Assistant schreiben** — `.storage/`, `.cloud/`, `deps/`, `tts/` und die Recorder-Datenbank. Dort liegt alles, was du über die HA-Oberfläche angelegt hast: UI-Automationen, Skripte, Szenen, Helper, Dashboards, Areas, Labels sowie die Entity- und Device-Registries. Diese Dateien verwaltet HA Core allein, sie haben kein stabiles Format — eine von Hand geänderte Datei in `.storage/` kann dazu führen, dass Home Assistant nicht mehr startet.

Claude soll solche Dinge stattdessen über den `homeassistant`-MCP-Server oder `hab` ändern. Geht beides nicht, sagt Claude das und überlässt dir den Weg über die Oberfläche. Dazu kommen: Inhalte aus `secrets.yaml` werden nie ausgegeben, vor jeder Dateiänderung wird die geplante Änderung gezeigt und deine Zustimmung abgewartet, und nach YAML-Änderungen wird auf Reload- bzw. Neustart-Bedarf hingewiesen.

### Option `protect_internal_config` (Standard: aktiviert)

Die CLAUDE.md ist eine Anweisung — kein technischer Riegel. Ist diese Option aktiv, trägt das Add-on zusätzlich Sperrregeln in die `settings.json` ein: Claude Code lehnt Schreibzugriffe auf die genannten Pfade dann selbst ab, unabhängig davon, was gerade im Kontext steht. **Lesen bleibt erlaubt** — Fehlersuche in `.storage/` funktioniert weiter, nur Schreiben nicht.

Abschalten kannst du das jederzeit. Manchmal ist ein gezielter Eingriff in `.storage/` genau das Richtige — das ist dann deine Entscheidung. Die Regeln werden bei jedem Start neu geschrieben, das Umschalten wirkt also sofort nach einem Add-on-Neustart. Eigene Einträge unter `permissions.deny` bleiben in beiden Richtungen erhalten.

Was die Sperre **nicht** abdeckt: Umwege über die Shell. `Bash`-Befehle wie `sed -i` oder `cp` auf denselben Pfaden werden davon nicht erfasst. Die Sperre fängt den häufigsten Fall ab, nicht jeden denkbaren.

## Direkter Browser-Zugriff (Port 7683)

Normalerweise läuft der Zugriff über das Ingress-Panel in Home Assistant — dort bist du bereits angemeldet, der Supervisor reicht die Verbindung durch. Wer das Terminal lieber in einem eigenen Browser-Tab hätte, ohne den Umweg über die HA-Oberfläche, schaltet `enable_direct_access` ein und setzt ein Passwort:

```yaml
enable_direct_access: true
direct_username: admin
direct_password: <langes, zufälliges Passwort>
```

Danach ist das Terminal unter `http://<HA-IP>:7683` erreichbar. Es ist **dieselbe** Sitzung wie im Ingress-Panel (beide hängen über `tmux` an der Session `claude`), nur ein zweiter Zugang — was du hier tippst, siehst du dort ebenfalls.

### Bevor du das einschaltest

Das Terminal ist eine **Root-Shell** auf einem Container mit `full_access`, Docker-Socket und Schreibrechten auf deine HA-Konfiguration. Über den Ingress schützt das der Home-Assistant-Login. Auf Port 7683 gibt es diesen Schutz nicht — dort steht nur das Passwort, das du hier setzt.

Deshalb gilt:

- **Ohne Passwort startet der Port nicht.** Lässt du `direct_password` leer, schreibt das Add-on einen Fehler ins Log und lässt 7683 zu — auch wenn `enable_direct_access` auf `true` steht. Das ist Absicht, ein offener Port wäre hier zu teuer.
- **Nimm ein langes, zufälliges Passwort.** Es ist das Einzige zwischen deinem Netz und einer Root-Shell.
- **Niemals im Router ins Internet weiterleiten.** Die Anmeldung läuft über HTTP Basic Auth, also unverschlüsselt — Passwort im Klartext auf der Leitung. Im eigenen LAN vertretbar, im Internet nicht. Willst du von außen ran, dann ausschließlich über VPN oder einen Reverse-Proxy mit TLS davor.
- Vergisst du das Passwort, kommst du weiterhin über das Ingress-Panel rein und kannst es dort neu setzen.

Zum Abschalten `enable_direct_access` auf `false` setzen und das Add-on neu starten. Ob der Port läuft, steht im Log:

```
[INFO] Direct access on port 7683, user 'admin' (HTTP Basic Auth — LAN only, never forward this port)
```

## Eigene Anweisungen (`CLAUDE.local.md`)

Die CLAUDE.md wird bei **jedem** Add-on-Start neu geschrieben — eigene Ergänzungen darin sind danach weg. Für dauerhafte eigene Anweisungen liegt in `/homeassistant/.claudecode/` die Datei `CLAUDE.local.md.example`. Benenne sie in `CLAUDE.local.md` um (`.example` entfernen), und Claude lädt sie ab dem nächsten Start in jeder Session mit.

An diese Datei rührt das Add-on nie, auch Updates nicht. Löschen genügt, um sie wieder loszuwerden — es gibt keine Option dafür. Bei Widersprüchen gewinnt die CLAUDE.md; die Schutzregeln oben lassen sich damit nicht aushebeln. Der Inhalt geht bei **jeder** Anfrage mit, also kurz halten: dauerhafte Vorlieben ja, Notizbuch nein. Keine Passwörter oder Tokens hineinschreiben — dafür ist `!secret` da.

## Tokens für MCP-Server (`.env`)

MCP-Server, die sich mit einem Token anmelden — etwa das offizielle GitHub-Plugin mit `${GITHUB_PERSONAL_ACCESS_TOKEN}` in der `.mcp.json` — lesen diesen Wert aus der Umgebung des laufenden `claude`-Prozesses. Ein `export` im Terminal hilft dabei nicht: es wirkt nur auf die aktuelle Shell und deren Kindprozesse, nie zurück auf den bereits gestarteten Elternprozess. Der Wert muss also stehen, **bevor** das Terminal startet.

Dafür liegt in `/homeassistant/.claudecode/` die Datei `.env.example`. In `.env` umbenennen (`.example` entfernen), Zeilen der Form `KEY=VALUE` eintragen, Add-on neu starten:

```
GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_11ABCDEFG0abcdefghijkl_...
```

**Die Raute muss weg.** In der Beispieldatei ist die Zeile auskommentiert; bleibt das `#` stehen, ist es ein Kommentar und der Token wird nicht geladen. Das Log sagt dann `.env contains no active variable`.

**Den Token unverändert einfügen.** Sein Präfix — `github_pat_` bei fine-grained Tokens, `ghp_` bei klassischen — gehört zum Token selbst. Der Platzhalter in der Beispieldatei ist vollständig zu ersetzen; wird stattdessen davor geschrieben, entsteht ein Wert wie `ghp_github_pat_11ABC…`, und GitHub antwortet mit einem nackten 401 (`Server rejected the configured Authorization header`), der nach fehlenden Rechten aussieht, nicht nach einem Tippfehler. Das Add-on warnt beim Start, wenn es ein doppeltes Präfix, ein Leerzeichen oder übrig gebliebenen Platzhaltertext im Wert sieht.

Format: eine Variable pro Zeile, `#` leitet einen Kommentar ein, Anführungszeichen um den Wert sind erlaubt und werden entfernt, ein vorangestelltes `export ` wird ignoriert. Zeilenumbrüche im Windows-Format (CRLF) und ein UTF-8-BOM werden abgeschnitten. Die Datei wird nicht ausgeführt, sondern Zeile für Zeile gelesen — `$(…)` darin bleibt Text.

### GitHub-MCP-Server einrichten

Der Token allein legt keinen Server an — er füllt nur den Platzhalter in dessen Konfiguration. Die Verbindung zu GitHub muss einmalig registriert werden:

```bash
claude mcp add-json github '{"type":"http","url":"https://api.githubcopilot.com/mcp/","headers":{"Authorization":"Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}"}}' -s user
```

`${GITHUB_PERSONAL_ACCESS_TOKEN}` bleibt dabei **genau so stehen**. Claude Code setzt den Wert beim Verbinden aus der Umgebung ein — Dein Token landet dadurch in keiner Konfigurationsdatei. Danach `claude` neu starten, `/mcp` zeigt `github` als verbundenen Server.

Der Eintrag liegt in `/root/.claude.json` und bleibt erhalten; das Add-on setzt beim Start nur `homeassistant` und `playwright` neu. Alternativ geht auch der Weg über `/plugin` → Marketplace → GitHub-Plugin; dessen `.mcp.json` verwendet dieselbe Variable.

Ignoriert werden `PATH`, `HOME`, `IFS`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `SUPERVISOR_TOKEN`, `HA_TOKEN` und `HA_URL`; sie zu überschreiben würde das Add-on lahmlegen. Im Log erscheinen nur die Namen der geladenen Variablen, nie deren Werte.

**Wo die Datei liegt, ist relevant:** `/homeassistant` steckt in jedem Home-Assistant-Backup, das Token damit auch. Vergib nur die nötigen Rechte (bei GitHub: fine-grained Token, minimaler Scope) und widerrufe es, wenn du es nicht mehr brauchst. Solange `protect_internal_config` aktiv ist, kann Claude die `.env` selbst nicht lesen — die Werte stehen ohnehin schon in seiner Umgebung.

## Git — Identität und Zugangsdaten

`/root` gehört zum Container-Image und ist nach jedem Rebuild leer. Deshalb liegen `~/.gitconfig` und die gespeicherten Zugangsdaten in `/homeassistant/.claudecode/` (`gitconfig` bzw. `.git-credentials`) und überstehen Neustarts wie Updates. Eine bereits vorhandene `~/.gitconfig` wird beim ersten Start übernommen, nicht überschrieben.

Einmalig einrichten:

```bash
git config --global user.name  "Dein Name"
git config --global user.email "du@example.com"
```

Als Credential-Helper ist `store` mit Ziel `/homeassistant/.claudecode/.git-credentials` voreingestellt — aber nur, wenn keiner konfiguriert ist. Ein eigener Helper bleibt unangetastet. Zugangsdaten hinterlegen, ohne sie in die History zu schreiben:

```bash
printf 'protocol=https\nhost=github.com\nusername=x-access-token\npassword=<PAT>\n' | git credential approve
```

Danach funktioniert `git push` auch nach einem Add-on-Neustart. Für die Datei gilt dasselbe wie für die `.env`: sie liegt im HA-Backup.

## tmux — Scrollen, Kopieren & Einfügen

Das Terminal verwendet tmux für persistente Sessions. Das Scroll-Verhalten steuert die Option `tmux_scroll_mode`:

**`browser` (Standard):** Ausgaben landen im nativen Browser-Scrollback (bis 20000 Zeilen). Mausrad, Touch-Scrollen (z. B. iPad) und normales Markieren/Kopieren funktionieren wie in jedem Terminal. Nach einem Browser-Reload ist nur der sichtbare Bildschirm da — ältere Historie über den tmux-Copy-Mode: `Ctrl+b [`, dann PageUp/Pfeiltasten, `q` zum Verlassen.

**`tmux`:** Das Mausrad scrollt direkt durch die tmux-Historie (Copy-Mode), die Browser-Reloads überlebt. Dafür kein Touch-Scrollen; Kopieren läuft über die tmux-Selektion.

> ⚠️ **Eingabe scheint tot?** Im `tmux`-Modus öffnet das erste Scrollen (Mausrad/Wisch) den Copy-Mode — Tastatureingaben gehen dann an den Copy-Mode statt an die Shell. Erkennbar am gelben Zähler oben rechts (z. B. `[0/1234]`). Mit **`q`** verlassen, dann funktioniert die Eingabe wieder.

| Aktion | Tastenkombination |
|--------|-------------------|
| Text kopieren | `Ctrl+Shift` halten + Maus markieren |
| Einfügen | `Shift+Einfg` oder mittlere Maustaste |
| Copy-Mode (ältere Historie) | `Ctrl+b [` — PageUp/Pfeiltasten |
| Scroll-/Copy-Mode verlassen | `q` |

Wer gar kein tmux möchte: `session_persistence: false` startet eine reine Bash — natives Scrollen und Kopieren ohne Einschränkungen, aber die Session überlebt keinen Browser-Reload.

### Scrollen auf Handy & Tablet

Auf Touch-Geräten (auch in der HA Companion App) blendet das Terminal zwei Scroll-Knöpfe unten rechts ein, und ein Wisch nach oben/unten scrollt.

> 💡 **Nach dem Update erst nur am rechten Rand scrollbar?** Dann hält die App noch die alte Terminal-Seite im Cache. HA Companion App komplett beenden (aus dem App-Umschalter wischen) und neu starten — ein Reload der Seite genügt nicht immer.


Das Terminal-Frontend (xterm.js) schaltet sein eigenes Touch-Scrollen ab, sobald eine Anwendung die Maus-Erfassung aktiviert — im Modus `tmux` also immer. Die Option `mobile_scroll_ui` (Standard: aktiviert) ersetzt es und funktioniert in **beiden** Scroll-Modi. Desktop-Browser bleiben unverändert; abschaltbar über die Option.

## Caveman-Skills

`enable_caveman_skill` installiert die Skills des Projekts [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) (MIT) nach `/root/.claude/skills/` — knappe, technisch vollständige Antworten ohne Füllwörter:

| Skill | Was er tut |
|-------|------------|
| `/caveman` | Der Modus selbst, Stufen `lite`/`full`/`ultra` (plus 文言文-Varianten) |
| `/caveman-commit` | Commit-Nachrichten im Conventional-Commits-Format, Betreff ≤ 50 Zeichen |
| `/caveman-review` | Code-Review-Kommentare, eine Zeile je Fund: Ort, Problem, Fix |
| `/caveman-compress` | Komprimiert Memory-Dateien (CLAUDE.md & Co.), Backup als `*.original.md` |
| `/caveman-help` | Übersicht aller Modi und Befehle |
| `/caveman-stats` | Token-Statistik der Sitzung |
| `/cavecrew` | Wann an die drei `cavecrew-*`-Subagenten delegiert wird (Agents werden mitinstalliert) |

Die Skills liegen versioniert im Add-on (Stand siehe `skills/UPSTREAM.md`) und werden bei jedem Start neu synchronisiert. Ausgeschaltet entfernt das Add-on genau diese Skills und Agents wieder — eigene bleiben unberührt.

> ℹ️ `/caveman-stats` liefert seine Zahlen beim Upstream aus einem Hook. Der Hook ist bewusst nicht gebündelt (er müsste sich in `settings.json` eintragen), der Skill bleibt daher ohne Zahlen.

## Update-Benachrichtigungen

Bei aktiviertem `auto_update_claude` prüft das Add-on stündlich auf neue Claude Code Versionen. Bei einem Update erscheint eine persistente HA-Benachrichtigung. Nach dem Neustart des Add-ons wird automatisch aktualisiert.

Verfolgt wird dabei nur der npm-Tag **`stable`**, nicht mehr jede veröffentlichte Version (`latest`). Anthropic setzt `stable` erst nach zusätzlicher Prüfung — dadurch deutlich seltenere Updates und weniger frische Regressionen, die installierte Version liegt dafür manchmal hinter der neuesten. Das gilt für alle drei Wege gleich: Image-Build, der stündliche Check und der manuelle Befehl `claude-update`. Auch der GitHub-Workflow, der neue Add-on-Versionen baut, wacht nur noch über `dist-tags.stable`.

---

# Claude Code (English)

Claude Code — Anthropic's AI coding assistant — directly in the Home Assistant sidebar.

## Setup

1. Start the add-on
2. Click **Claude Code** in the HA sidebar
3. Type `claude` and follow the authentication flow
4. Credentials are stored permanently — no API key needed in the configuration

## Quick Start

```bash
claude "List all my automations"
claude "Create an automation to turn on lights at sunset"
claude "Why isn't my motion sensor automation working?"
claude --continue   # continue last conversation
```

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `enable_mcp` | `true` | Enable HA integration (query entities, call services) |
| `terminal_font_size` | `14` | Terminal font size (10–24) |
| `terminal_theme` | `dark` | Terminal theme: `dark` or `light` |
| `session_persistence` | `true` | Use tmux — session survives browser reload |
| `tmux_scroll_mode` | `browser` | Scroll behavior with tmux: `browser` (native scrolling/touch/copy-paste) or `tmux` (mouse wheel scrolls tmux history) |
| `mobile_scroll_ui` | `true` | Swipe scrolling and scroll buttons on touch devices (phone/tablet/HA app) |
| `claude_autostart` | `false` | Auto-start Claude when the terminal opens |
| `auto_update_claude` | `true` | Auto-update Claude Code on startup |
| `model` | `claude-sonnet-5` | Claude model to use |
| `enable_playwright_mcp` | `false` | Enable Playwright browser MCP (requires Playwright Browser add-on) |
| `export_memory` | `false` | Export Claude memory to `/config/memory/` |
| `export_memory_interval` | `60` | Export interval in minutes |
| `enable_caveman_skill` | `false` | Install the optional "Caveman" skills (terse responses) — 7 skills + 3 subagents |
| `enable_direct_access` | `false` | Also serve the terminal on port 7683, bypassing ingress ([details](#direct-browser-access-port-7683)) |
| `direct_username` | `admin` | Username for port 7683 |
| `direct_password` | — | Password for port 7683 — empty means the port does not start |

## Model Selection

| Model | Best for |
|-------|----------|
| `claude-sonnet-5` | Best balance (default) |
| `claude-fable-5` | Most powerful, for the hardest tasks |
| `claude-opus-5` | Very capable, for complex tasks |
| `claude-haiku-4-5-20251001` | Fastest, for simple queries |

## Keyboard Shortcuts

| Shortcut | Command |
|----------|---------|
| `c` | Start `claude` |
| `cc` | `claude --continue` (resume last conversation) |
| `ha-config` | Navigate to HA config directory |
| `ha-logs` | Show Home Assistant logs |
| `claude-update` | Manually update Claude Code |

## File Paths

| Path | Access |
|------|--------|
| `/homeassistant` | HA configuration (read/write) |
| `/share` | Shared folder (read/write) |
| `/media` | Media folder (read/write) |
| `/ssl` | SSL certificates (read-only) |
| `/backup` | Backups (read-only) |

## Home Assistant Builder CLI (`hab`)

Alongside the `homeassistant` MCP server, [`hab`](https://github.com/balloob/home-assistant-build-cli) is also available — a CLI tool built specifically for LLM use, intended for admin operations beyond simple entity queries: dashboard CRUD, area/floor/label management, helper creation, backup/restore. Authentication happens automatically via the Supervisor token — no setup needed.

```bash
hab guide                     # discover available commands
hab schema <command> --json   # inspect a command's contract
hab <command> --plan --json   # preview a mutation before applying it
```

On startup, the add-on also writes a Home Context snapshot (`hab overview`) into CLAUDE.md — so Claude starts each session already knowing the number of areas, entities, automations, etc. instead of having to ask first.

## Safety Rules

CLAUDE.md carries binding rules for how your installation may be touched. The most important one: **never write to Home Assistant's internal directories** — `.storage/`, `.cloud/`, `deps/`, `tts/` and the recorder database. That is where everything you created through the HA user interface lives: UI automations, scripts, scenes, helpers, dashboards, areas, labels, plus the entity and device registries. Those files are managed by HA Core alone and have no stable format — a hand-edited file in `.storage/` can leave Home Assistant unable to start.

Claude is told to change such things through the `homeassistant` MCP server or `hab` instead. If neither can do it, Claude says so and leaves the UI route to you. On top of that: the contents of `secrets.yaml` are never displayed, every file change is shown and confirmed before it is written, and YAML changes come with a note on whether a reload or a full restart is required.

### Option `protect_internal_config` (default: enabled)

CLAUDE.md is guidance — not a technical barrier. With this option on, the add-on additionally writes deny rules into `settings.json`: Claude Code then refuses writes to those paths itself, regardless of what is currently in context. **Reading stays allowed** — troubleshooting inside `.storage/` still works, only writing does not.

You can turn it off at any time. Sometimes a deliberate edit in `.storage/` is exactly the right move — that call is yours. The rules are rewritten on every start, so toggling takes effect right after an add-on restart. Your own `permissions.deny` entries are preserved in both directions.

What the block does **not** cover: detours through the shell. `Bash` commands such as `sed -i` or `cp` on the same paths are not caught by it. This closes the common case, not every conceivable one.

## Direct Browser Access (port 7683)

Normally you reach the terminal through the ingress panel in Home Assistant — you are already logged in there and the Supervisor forwards the connection. If you would rather have the terminal in its own browser tab, without going through the HA interface, switch on `enable_direct_access` and set a password:

```yaml
enable_direct_access: true
direct_username: admin
direct_password: <long random password>
```

The terminal is then reachable at `http://<HA-IP>:7683`. It is the **same** session as the ingress panel (both attach to the `claude` tmux session), just a second way in — what you type here shows up there too.

### Before you switch this on

The terminal is a **root shell** on a container with `full_access`, the Docker socket, and write access to your HA configuration. Through ingress, the Home Assistant login protects it. On port 7683 that protection is gone — all that stands there is the password you set here.

So:

- **Without a password the port does not start.** Leave `direct_password` empty and the add-on logs an error and keeps 7683 closed, even with `enable_direct_access` set to `true`. That is deliberate; an open port here is too expensive to get wrong.
- **Use a long, random password.** It is the only thing between your network and a root shell.
- **Never forward it to the internet in your router.** Login uses HTTP Basic Auth, unencrypted — the password travels in clear text. Acceptable on your own LAN, not on the internet. To reach it from outside, use a VPN or put a TLS reverse proxy in front.
- If you forget the password, you can still get in through the ingress panel and set a new one there.

To turn it off, set `enable_direct_access` to `false` and restart the add-on. The log tells you whether the port is up:

```
[INFO] Direct access on port 7683, user 'admin' (HTTP Basic Auth — LAN only, never forward this port)
```

## Your Own Instructions (`CLAUDE.local.md`)

CLAUDE.md is rewritten on **every** add-on start, so anything you add there is gone afterwards. For permanent instructions of your own, `/homeassistant/.claudecode/` contains `CLAUDE.local.md.example`. Rename it to `CLAUDE.local.md` (drop the `.example`) and Claude loads it in every session from the next start on.

The add-on never touches that file, updates included. Delete it to stop loading it — there is no option to toggle. CLAUDE.md wins where the two conflict; the safety rules above cannot be overridden from here. The content is sent with **every** request, so keep it short: standing preferences yes, diary no. Never put passwords or tokens in it — that is what `!secret` is for.

## Tokens for MCP Servers (`.env`)

MCP servers that authenticate with a token — the official GitHub plugin, for instance, with `${GITHUB_PERSONAL_ACCESS_TOKEN}` in its `.mcp.json` — read that value from the environment of the running `claude` process. An `export` in the terminal does not help: it only affects the current shell and its children, never the already-running parent. The value has to be in place **before** the terminal starts.

That is what `.env.example` in `/homeassistant/.claudecode/` is for. Rename it to `.env` (drop the `.example`), add `KEY=VALUE` lines, restart the add-on:

```
GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_11ABCDEFG0abcdefghijkl_...
```

**Delete the leading `#`.** The line is commented out in the example file; leave the `#` in place and it stays a comment, so the token is never loaded. The log then says `.env contains no active variable`.

**Paste the token unchanged.** Its prefix — `github_pat_` for fine-grained tokens, `ghp_` for classic ones — is part of the token itself. Replace the placeholder in the example file completely; typing in front of it instead produces a value like `ghp_github_pat_11ABC…`, and GitHub answers with a bare 401 (`Server rejected the configured Authorization header`) that reads like missing permissions rather than a typo. The add-on warns on start when it sees a doubled prefix, a space or leftover placeholder text in a value.

Format: one variable per line, `#` starts a comment, quotes around the value are allowed and get stripped, a leading `export ` is ignored. Windows-style line endings (CRLF) and a UTF-8 BOM are stripped. The file is not executed but read line by line — `$(…)` inside it stays text.

### Setting up the GitHub MCP server

The token alone does not create a server — it only fills the placeholder in that server's configuration. The connection to GitHub has to be registered once:

```bash
claude mcp add-json github '{"type":"http","url":"https://api.githubcopilot.com/mcp/","headers":{"Authorization":"Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}"}}' -s user
```

Leave `${GITHUB_PERSONAL_ACCESS_TOKEN}` in there **exactly as written**. Claude Code substitutes the value from the environment when connecting, so your token never ends up in a config file. Then restart `claude` and `/mcp` lists `github` as connected.

The entry lives in `/root/.claude.json` and persists; the add-on only re-creates `homeassistant` and `playwright` on start. The `/plugin` → marketplace → GitHub plugin route works as well; its `.mcp.json` uses the same variable.

Ignored are `PATH`, `HOME`, `IFS`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `SUPERVISOR_TOKEN`, `HA_TOKEN` and `HA_URL`; overwriting those would break the add-on. The log lists only the names of the loaded variables, never their values.

**Where the file lives matters:** `/homeassistant` is part of every Home Assistant backup, and so is the token. Grant only the permissions you need (on GitHub: a fine-grained token with minimal scope) and revoke it once you are done. While `protect_internal_config` is on, Claude cannot read the `.env` itself — the values are already in its environment anyway.

## Git — Identity and Credentials

`/root` belongs to the container image and is empty after every rebuild. That is why `~/.gitconfig` and the stored credentials live in `/homeassistant/.claudecode/` (`gitconfig` and `.git-credentials`) and survive restarts as well as updates. An existing `~/.gitconfig` is carried over on first start, not overwritten.

One-time setup:

```bash
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"
```

The credential helper defaults to `store` pointing at `/homeassistant/.claudecode/.git-credentials` — but only when none is configured. Your own helper is left alone. Store credentials without putting them in the shell history:

```bash
printf 'protocol=https\nhost=github.com\nusername=x-access-token\npassword=<PAT>\n' | git credential approve
```

After that `git push` keeps working across add-on restarts. The same caveat as for `.env` applies: the file is included in HA backups.

## tmux — Scrolling, Copy & Paste

The terminal uses tmux for persistent sessions. Scroll behavior is controlled by the `tmux_scroll_mode` option:

**`browser` (default):** Output flows into the native browser scrollback (up to 20000 lines). Mouse wheel, touch scrolling (e.g. iPad) and normal select/copy work like in any terminal. After a browser reload only the visible screen remains — reach older history via tmux copy mode: `Ctrl+b [`, then PageUp/arrow keys, `q` to exit.

**`tmux`:** The mouse wheel scrolls directly through the tmux history (copy mode), which survives browser reloads. Touch scrolling is unavailable; copying goes through the tmux selection.

> ⚠️ **Input seems dead?** In `tmux` mode the first scroll (mouse wheel/swipe) opens copy mode — keystrokes then go to copy mode instead of the shell. You can tell by the yellow counter in the top-right corner (e.g. `[0/1234]`). Press **`q`** to exit, and input works again.

| Action | Key combination |
|--------|-----------------|
| Copy text | Hold `Ctrl+Shift` + select with mouse |
| Paste | `Shift+Insert` or middle-click |
| Copy mode (older history) | `Ctrl+b [` — PageUp/arrow keys |
| Exit scroll/copy mode | `q` |

If you don't want tmux at all: `session_persistence: false` starts plain bash — native scrolling and copying without restrictions, but the session does not survive a browser reload.

### Scrolling on phone & tablet

On touch devices (including the HA Companion App) the terminal shows two scroll buttons in the bottom-right corner, and swiping up/down scrolls.

> 💡 **After the update only the right edge scrolls?** The app is still holding the old terminal page in its cache. Fully quit the HA Companion App (swipe it away in the app switcher) and start it again — a page reload is not always enough.


The terminal frontend (xterm.js) disables its own touch scrolling as soon as an application turns on mouse tracking — which is always the case in `tmux` mode. The `mobile_scroll_ui` option (default: enabled) replaces it and works in **both** scroll modes. Desktop browsers are left unchanged; the option turns it off.

## Caveman Skills

`enable_caveman_skill` installs the skills from [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) (MIT) into `/root/.claude/skills/` — terse, technically complete answers without filler:

| Skill | What it does |
|-------|--------------|
| `/caveman` | The mode itself, levels `lite`/`full`/`ultra` (plus 文言文 variants) |
| `/caveman-commit` | Commit messages in Conventional Commits format, subject ≤ 50 chars |
| `/caveman-review` | Code review comments, one line per finding: location, problem, fix |
| `/caveman-compress` | Compresses memory files (CLAUDE.md & co.), backup as `*.original.md` |
| `/caveman-help` | Reference card for all modes and commands |
| `/caveman-stats` | Token statistics for the session |
| `/cavecrew` | When to delegate to the three `cavecrew-*` subagents (agents are installed too) |

The skills are vendored into the add-on (see `skills/UPSTREAM.md` for the version) and re-synced on every startup. Turning the option off removes exactly those skills and agents again — your own ones are left alone.

> ℹ️ Upstream, `/caveman-stats` gets its numbers from a hook. That hook is deliberately not bundled (it would have to register itself in `settings.json`), so the skill stays without numbers.

## Update Notifications

With `auto_update_claude` enabled, the add-on checks hourly for new Claude Code versions. A persistent HA notification appears when an update is available. Restarting the add-on installs the latest version automatically.

Only the npm tag **`stable`** is tracked, no longer every published release (`latest`). Anthropic sets `stable` after additional vetting — far fewer updates and fewer fresh regressions, at the price of sometimes running behind the newest release. This applies to all three paths alike: image build, the hourly check and the manual `claude-update` command. The GitHub workflow that builds new add-on versions also watches `dist-tags.stable` only.
