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
| `claude_autostart` | `false` | Claude beim Öffnen des Terminals automatisch starten |
| `auto_update_claude` | `true` | Claude Code beim Start automatisch aktualisieren |
| `model` | `claude-sonnet-4-6` | Zu verwendendes Claude-Modell |
| `enable_playwright_mcp` | `false` | Playwright Browser-MCP aktivieren (benötigt Playwright Browser Add-on) |
| `export_memory` | `false` | Claude-Speicher in `/config/memory/` exportieren |
| `export_memory_interval` | `60` | Export-Intervall in Minuten |

## Modellauswahl

| Modell | Für was |
|--------|---------|
| `claude-sonnet-4-6` | Beste Balance (Standard) |
| `claude-opus-4-7` | Stärkstes Modell, für komplexe Aufgaben |
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

## tmux — Kopieren & Einfügen

Das Terminal verwendet tmux für persistente Sessions. Kopieren/Einfügen funktioniert etwas anders:

| Aktion | Tastenkombination |
|--------|-------------------|
| Text kopieren | `Ctrl+Shift` halten + Maus markieren |
| Einfügen | `Shift+Einfg` oder mittlere Maustaste |
| Scroll-Modus verlassen | `q` |

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
| `claude_autostart` | `false` | Auto-start Claude when the terminal opens |
| `auto_update_claude` | `true` | Auto-update Claude Code on startup |
| `model` | `claude-sonnet-4-6` | Claude model to use |
| `enable_playwright_mcp` | `false` | Enable Playwright browser MCP (requires Playwright Browser add-on) |
| `export_memory` | `false` | Export Claude memory to `/config/memory/` |
| `export_memory_interval` | `60` | Export interval in minutes |

## Model Selection

| Model | Best for |
|-------|----------|
| `claude-sonnet-4-6` | Best balance (default) |
| `claude-opus-4-7` | Most powerful, for complex tasks |
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

## tmux — Copy & Paste

The terminal uses tmux for persistent sessions. Copy/paste works slightly differently:

| Action | Key combination |
|--------|-----------------|
| Copy text | Hold `Ctrl+Shift` + select with mouse |
| Paste | `Shift+Insert` or middle-click |
| Exit scroll mode | `q` |

## Update Notifications

With `auto_update_claude` enabled, the add-on checks hourly for new Claude Code versions. A persistent HA notification appears when an update is available. Restarting the add-on installs the latest version automatically.
