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
| `enable_caveman_skill` | `false` | Optionalen "Caveman"-Skill (knappe Antworten) installieren |

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

Auf Touch-Geräten (auch in der HA Companion App) blendet das Terminal zwei Scroll-Knöpfe unten rechts ein, und ein Wisch nach oben/unten scrollt. Das Terminal-Frontend (xterm.js) schaltet sein eigenes Touch-Scrollen ab, sobald eine Anwendung die Maus-Erfassung aktiviert — im Modus `tmux` also immer. Die Option `mobile_scroll_ui` (Standard: aktiviert) ersetzt es und funktioniert in **beiden** Scroll-Modi. Desktop-Browser bleiben unverändert; abschaltbar über die Option.

## Update-Benachrichtigungen

Bei aktiviertem `auto_update_claude` prüft das Add-on stündlich auf neue Claude Code Versionen. Bei einem Update erscheint eine persistente HA-Benachrichtigung. Nach dem Neustart des Add-ons wird automatisch aktualisiert.

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
| `enable_caveman_skill` | `false` | Install the optional "Caveman" skill (terse responses) |

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

On touch devices (including the HA Companion App) the terminal shows two scroll buttons in the bottom-right corner, and swiping up/down scrolls. The terminal frontend (xterm.js) disables its own touch scrolling as soon as an application turns on mouse tracking — which is always the case in `tmux` mode. The `mobile_scroll_ui` option (default: enabled) replaces it and works in **both** scroll modes. Desktop browsers are left unchanged; the option turns it off.

## Update Notifications

With `auto_update_claude` enabled, the add-on checks hourly for new Claude Code versions. A persistent HA notification appears when an update is available. Restarting the add-on installs the latest version automatically.
