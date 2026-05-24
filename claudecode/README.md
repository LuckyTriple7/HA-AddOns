# Claude Code für Home Assistant

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=claudecode&style=flat-square)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

> **Basiert auf [apbb2/robsonfelix-hass-addons](https://github.com/apbb2/robsonfelix-hass-addons/tree/main/claudecode)**,
> welches wiederum auf [robsonfelix/robsonfelix-hass-addons](https://github.com/robsonfelix/robsonfelix-hass-addons) basiert.
> Dieser Fork ergänzt einen socat-basierten Port-Forward-Fix für den Playwright MCP CDP-Endpunkt.

Führe [Claude Code](https://docs.anthropic.com/en/docs/claude-code), den KI-gestützten Coding-Assistenten von Anthropic, direkt in der Home Assistant Seitenleiste aus – mit vollem Zugriff auf deine Konfiguration.

## Schnellstart

```bash
claude "Liste alle meine Automationen auf"
claude "Schalte alle Lichter im Wohnzimmer aus"
claude "Erstelle eine Automation, die bei Sonnenuntergang das Licht einschaltet"
claude "Warum funktioniert meine Bewegungsmelder-Automation nicht?"
```

## Voraussetzungen

- Home Assistant OS oder Supervised-Installation
- [Anthropic-Konto](https://console.anthropic.com/) (Authentifizierung erfolgt im Terminal)

## Funktionen

- **Web-Terminal**: Zugriff auf Claude Code über ein browserbasiertes Terminal
- **Konfigurationszugriff**: Lesen und Schreiben von Home Assistant Konfigurationsdateien
- **hass-mcp Integration**: Direkte Steuerung von HA-Entitäten und Diensten
- **Sitzungserhaltung**: Optionale tmux-Integration, damit Sitzungen nach einem Browser-Reload erhalten bleiben
- **Anpassbares Design**: Dunkles oder helles Terminal-Theme wählbar
- **Claude Auto-Start**: Claude startet optional automatisch beim Öffnen des Terminals
- **Multi-Architektur**: Unterstützt amd64, aarch64, armv7, armhf und i386
- **Sichere Authentifizierung**: Claude Code verwaltet die Authentifizierung selbst

## Einrichtung

### 1. Add-on installieren

1. Repository zu Home Assistant hinzufügen
2. Das Add-on „Claude Code" installieren
3. Add-on starten
4. Web-UI über die Seitenleiste öffnen

### 2. Mit Claude Code authentifizieren

Beim ersten Start wird Claude Code zur Authentifizierung auffordern:

1. Terminal über die HA-Seitenleiste öffnen
2. `claude` eingeben, um zu starten (oder `claude_autostart` aktivieren)
3. Den Anweisungen zur Authentifizierung folgen
4. Die Anmeldedaten werden sicher von Claude Code gespeichert

**Hinweis**: Das Add-on erfordert **keine** API-Schlüssel in der Konfiguration. Claude Code verwaltet die Authentifizierung selbst und speichert die Zugangsdaten sicher in einem eigenen Verzeichnis – sicherer als das Hinterlegen von Schlüsseln in der HA-Add-on-Konfiguration.

## Claude Code verwenden

### Grundlegende Nutzung

Nach der Authentifizierung hilft Claude Code bei:

- Bearbeiten von Home Assistant YAML-Konfigurationen
- Erstellen von Automationen und Skripten
- Debuggen von Konfigurationsproblemen
- Schreiben von Custom Integrations

### Home Assistant Integration

Mit aktiviertem hass-mcp kann Claude:

- Entitätszustände abfragen: „Wie warm ist es im Wohnzimmer?"
- Geräte steuern: „Schalte alle Lichter im Schlafzimmer aus"
- Dienste auflisten: „Welche Dienste stehen für die Klimasteuerung zur Verfügung?"
- Automationen debuggen: „Warum hat meine Morgenroutine nicht ausgelöst?"

### Beispielbefehle

```bash
# Interaktive Sitzung starten
claude

# Einzelbefehle
claude "Erstelle eine neue Automation, die das Terrassenlich bei Sonnenuntergang einschaltet"
claude "Prüfe meine configuration.yaml auf Fehler"
claude "Liste alle nicht verfügbaren Entitäten auf"

# Vorherige Unterhaltung fortsetzen
claude --continue
```

### Tastenkürzel

| Kürzel | Befehl |
|--------|--------|
| `c` | `claude` |
| `cc` | `claude --continue` |
| `ha-config` | Zum Konfigurationsverzeichnis wechseln |
| `ha-logs` | Home Assistant Logs anzeigen |

## Konfigurationsoptionen

| Option | Beschreibung | Standard |
|--------|-------------|---------|
| `enable_mcp` | HA-Integration aktivieren | true |
| `terminal_font_size` | Schriftgröße (10–24) | 14 |
| `terminal_theme` | dark oder light | dark |
| `working_directory` | Startverzeichnis | /homeassistant |
| `session_persistence` | tmux für persistente Sitzungen verwenden | true |
| `claude_autostart` | Claude beim Öffnen des Terminals automatisch starten | false |
| `auto_update_claude` | Claude Code beim Start automatisch aktualisieren | true |
| `model` | Zu verwendendes Claude-Modell | claude-sonnet-4-6 |

### Modellauswahl

Es stehen drei Modelle zur Verfügung:

| Modell | Am besten für |
|--------|--------------|
| `claude-sonnet-4-6` | Beste Balance aus Geschwindigkeit und Leistung (Standard) |
| `claude-opus-4-7` | Leistungsstärkstes Modell, für komplexe Aufgaben |
| `claude-haiku-4-5-20251001` | Schnellstes Modell, für einfache Anfragen |

`auto_update_claude` aktivieren, damit neue Modelle automatisch verfügbar werden, sobald Anthropic sie veröffentlicht – ohne Update des Add-ons.

## Update-Benachrichtigungen

Wenn `auto_update_claude` aktiviert ist, prüft das Add-on stündlich im Hintergrund auf neuere Versionen von Claude Code. Ist ein Update verfügbar:

- Eine **persistente Benachrichtigung** erscheint in der HA-UI-Benachrichtigungsglocke mit dem Titel „Claude Code Update Available"
- Ein **gelbes Banner** wird bei jeder neuen Terminal-Sitzung angezeigt

Beide werden automatisch entfernt, sobald das Add-on neu gestartet und die neueste Version installiert wurde.

## Dateipfade

| Pfad | Beschreibung | Zugriff |
|------|-------------|---------|
| `/homeassistant` | HA-Konfigurationsverzeichnis | Lesen/Schreiben |
| `/share` | Freigegebener Ordner | Lesen/Schreiben |
| `/media` | Medienordner | Lesen/Schreiben |
| `/ssl` | SSL-Zertifikate | Nur Lesen |
| `/backup` | Backups | Nur Lesen |

## Sitzungserhaltung

Wenn `session_persistence` aktiviert ist, verwendet das Add-on tmux, um die Terminal-Sitzung zu erhalten. Das bedeutet:

- Die Sitzung überlebt Browser-Neuladen
- Trennen und erneut Verbinden ohne Kontextverlust
- Claude Code-Unterhaltungen bleiben erhalten

### tmux-Befehle

Für tmux-Einsteiger:

| Taste | Aktion |
|-------|--------|
| `Ctrl+b d` | Sitzung trennen (läuft im Hintergrund weiter) |
| `Ctrl+b [` | Scroll-/Kopiermodus (Pfeiltasten zum Scrollen) |
| Mausrad | Rauf/runter scrollen (aktiviert Kopiermodus automatisch) |
| `q` | Scroll-/Kopiermodus beenden |

### Kopieren und Einfügen in tmux

Da tmux Mausereignisse abfängt, funktioniert Kopieren/Einfügen etwas anders:

| Aktion | Wie es geht |
|--------|-------------|
| **Kopieren** | `Ctrl+Shift` gedrückt halten und Text mit der Maus markieren |
| **Einfügen** | `Shift+Einfg` oder mittlere Maustaste |
| **Alternativ einfügen** | `Ctrl+Shift+V` (browserabhängig) |

**Hinweis**: Normales Rechtsklick-Einfügen und einfache Mausmarkierung funktionieren nicht, da tmux diese Ereignisse für das Scrollen abfängt.

#### Claude Code authentifizieren (Erststart)

Die Authentifizierungs-URL wird in einer einzelnen Zeile angezeigt, damit sie leicht anklickbar ist.

1. **Link anklicken** – öffnet sich in einem neuen Tab
2. Authentifizierung im Browser abschließen und **Auth-Code kopieren**
3. Zurück ins Terminal klicken und mit `Shift+Einfg` oder `Ctrl+Shift+V` **einfügen**

Falls der Link sich nicht direkt anklicken lässt: `Ctrl+Shift` gedrückt halten und die URL mit der Maus markieren, dann in die Adressleiste des Browsers einfügen.

### Vor- und Nachteile von Sitzungserhaltung

**Mit tmux (`session_persistence: true`):**
- ✅ Sitzung überlebt Browser-Reload/Trennung
- ✅ Trennen und wieder verbinden bei laufenden Sitzungen möglich
- ✅ Lange Claude-Aufgaben laufen im Hintergrund weiter
- ✅ Mausrad-Scrollen funktioniert (aktiviert Kopiermodus automatisch)
- ✅ 20.000 Zeilen Scrollback-Puffer
- ⚠️ Mittlere Maustaste oder Shift+Einfg zum Einfügen verwenden (Rechtsklick-Einfügen funktioniert ggf. nicht)

**Ohne tmux (`session_persistence: false`):**
- ✅ Natives Browser-Scrollen
- ✅ Einfacheres Terminal-Verhalten
- ✅ Standard Kopieren/Einfügen
- ❌ Sitzung geht bei Browser-Reload verloren
- ❌ Sitzung geht bei Add-on-Neustart verloren

**Empfehlung:**
- `session_persistence: true` (Standard) verwenden, wenn lange Aufgaben laufen oder Verbindungsabbrüche toleriert werden sollen
- `session_persistence: false` verwenden, wenn Standard-Kopieren/Einfügen benötigt wird

## Sicherheit

### Authentifizierung
- **Keine API-Schlüssel in der Add-on-Konfiguration**: Claude Code verwaltet die Authentifizierung selbst
- Zugangsdaten werden sicher im Verzeichnis von Claude Code gespeichert (`~/.claude/`)
- Sicherer als das Hinterlegen von Schlüsseln in der Home Assistant Konfiguration

### Container-Sicherheit
- Das Supervisor-Token wird automatisch verwaltet und nicht exponiert
- Dateizugriff ist auf gemappte Verzeichnisse beschränkt
- Das Add-on läuft in einem isolierten Container

## Fehlerbehebung

### Authentifizierungsprobleme

Claude Code verwaltet seine eigene Authentifizierung. Bei Problemen:
1. `claude` eingeben, um den Authentifizierungsablauf zu starten
2. Den Anweisungen zum Einloggen oder zur API-Key-Eingabe folgen
3. Zugangsdaten werden automatisch für zukünftige Sitzungen gespeichert

**URL lässt sich nicht kopieren oder Auth-Code nicht einfügen?** Das Terminal verwendet tmux, was das Kopieren/Einfügen verändert. Siehe [Kopieren und Einfügen in tmux](#kopieren-und-einf%C3%BCgen-in-tmux).

### hass-mcp funktioniert nicht

1. Sicherstellen, dass `enable_mcp` in der Konfiguration auf true gesetzt ist
2. Add-on-Logs auf Verbindungsfehler prüfen
3. Add-on nach Konfigurationsänderungen neu starten

### Terminal lädt nicht

1. Prüfen, ob das Add-on läuft (grüner Indikator)
2. Seite neu laden
3. Browser-Konsole auf Fehler prüfen
4. Add-on-Logs auf ttyd-Fehler prüfen

### Sitzung bleibt nicht erhalten

1. Sicherstellen, dass `session_persistence` auf true gesetzt ist
2. Die Sitzung heißt „claude" – sie wird beim erneuten Verbinden automatisch wiederhergestellt

### Konfigurationsänderungen werden nicht übernommen

Nach Konfigurationsänderungen:
1. Konfiguration speichern
2. Add-on vollständig neu starten

## Support

- [GitHub Issues](https://github.com/LuckyTriple7/HA-AddOns/issues)
- [Home Assistant Community](https://community.home-assistant.io/)

---

# Claude Code for Home Assistant

> **Forked from [apbb2/robsonfelix-hass-addons](https://github.com/apbb2/robsonfelix-hass-addons/tree/main/claudecode)**,
> which itself is based on [robsonfelix/robsonfelix-hass-addons](https://github.com/robsonfelix/robsonfelix-hass-addons).
> This fork adds a socat-based port forwarding fix for the Playwright MCP CDP endpoint.

Run [Claude Code](https://docs.anthropic.com/en/docs/claude-code), Anthropic's AI-powered coding assistant, directly in your Home Assistant sidebar with full access to your configuration.

## Quick Start

```bash
claude "List all my automations"
claude "Turn off all lights in the living room"
claude "Create an automation to turn on lights at sunset"
claude "Why isn't my motion sensor automation working?"
```

## Requirements

- Home Assistant OS or Supervised installation
- [Anthropic account](https://console.anthropic.com/) (authentication handled in terminal)

## Features

- **Web Terminal**: Access Claude Code through a browser-based terminal
- **Config Access**: Read and write Home Assistant configuration files
- **hass-mcp Integration**: Direct control of HA entities and services
- **Session Persistence**: Optional tmux integration to preserve sessions across page refreshes
- **Customizable Theme**: Choose between dark and light terminal themes
- **Claude Auto-Start**: Claude starts automatically when the terminal opens (optional)
- **Multi-Architecture**: Supports amd64, aarch64, armv7, armhf, and i386
- **Secure Authentication**: Claude Code handles its own authentication securely

## Setup

### 1. Install the Add-on

1. Add the repository to Home Assistant
2. Install the "Claude Code" add-on
3. Start the add-on
4. Open the Web UI from the sidebar

### 2. Authenticate with Claude Code

On first launch, Claude Code will prompt you to authenticate:

1. Open the terminal from the HA sidebar
2. Type `claude` to start (or enable `claude_autostart`)
3. Follow the authentication prompts
4. Your credentials are stored securely by Claude Code

**Note**: The add-on does NOT require you to enter API keys in the configuration. Claude Code handles authentication itself, storing credentials securely in its own configuration directory. This is more secure than storing keys in Home Assistant's add-on config.

## Using Claude Code

### Basic Usage

Once authenticated, Claude Code is ready to help with:

- Editing Home Assistant YAML configurations
- Creating automations and scripts
- Debugging configuration issues
- Writing custom integrations

### Home Assistant Integration

With hass-mcp enabled, Claude can:

- Query entity states: "What's the temperature in the living room?"
- Control devices: "Turn off all lights in the bedroom"
- List services: "What services are available for climate control?"
- Debug automations: "Why didn't my morning routine trigger?"

### Example Commands

```bash
# Start interactive session
claude

# One-off commands
claude "Add a new automation that turns on the porch light at sunset"
claude "Check my configuration.yaml for errors"
claude "List all unavailable entities"

# Continue previous conversation
claude --continue
```

### Keyboard Shortcuts

| Shortcut | Command |
|----------|---------|
| `c` | `claude` |
| `cc` | `claude --continue` |
| `ha-config` | Navigate to config directory |
| `ha-logs` | View Home Assistant logs |

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `enable_mcp` | Enable HA integration | true |
| `terminal_font_size` | Font size (10-24) | 14 |
| `terminal_theme` | dark or light | dark |
| `working_directory` | Start directory | /homeassistant |
| `session_persistence` | Use tmux for persistent sessions | true |
| `claude_autostart` | Auto-start Claude when terminal opens | false |
| `auto_update_claude` | Auto-update Claude Code on startup | true |
| `model` | Claude model to use | claude-sonnet-4-6 |

### Model Selection

Three models are available:

| Model | Best for |
|-------|----------|
| `claude-sonnet-4-6` | Best balance of speed and capability (default) |
| `claude-opus-4-7` | Most powerful, for complex tasks |
| `claude-haiku-4-5-20251001` | Fastest, for simple queries |

Enable `auto_update_claude` to ensure new models become available as Anthropic releases them, without needing an add-on update.

## Update Notifications

When `auto_update_claude` is enabled, the add-on checks for newer versions of Claude Code in the background every hour. If an update is available:

- A **persistent notification** appears in the HA UI notification bell with the title "Claude Code Update Available"
- A **yellow banner** is shown in the terminal each time you open a session

Both clear automatically after restarting the add-on, which installs the latest version on startup.

## File Locations

| Path | Description | Access |
|------|-------------|--------|
| `/homeassistant` | HA configuration directory | read-write |
| `/share` | Shared folder | read-write |
| `/media` | Media folder | read-write |
| `/ssl` | SSL certificates | read-only |
| `/backup` | Backups | read-only |

## Session Persistence

When `session_persistence` is enabled, the add-on uses tmux to maintain your terminal session. This means:

- Your session survives browser refreshes
- You can disconnect and reconnect without losing context
- Claude Code conversations are preserved

### tmux Commands

If you're new to tmux:

| Key | Action |
|-----|--------|
| `Ctrl+b d` | Detach from session (keeps it running) |
| `Ctrl+b [` | Enter scroll/copy mode (use arrow keys) |
| Mouse wheel | Scroll up/down (auto-enters copy mode) |
| `q` | Exit scroll/copy mode |

### Copy and Paste in tmux

Since tmux captures mouse events, copy/paste works differently:

| Action | How to do it |
|--------|--------------|
| **Copy** | Hold `Ctrl+Shift` while selecting text with mouse |
| **Paste** | `Shift+Insert` or middle-click |
| **Alternative paste** | `Ctrl+Shift+V` (browser dependent) |

**Note**: Regular right-click paste and simple mouse selection won't work because tmux intercepts these events for scrolling.

#### Authenticating Claude Code (first launch)

The authentication URL is displayed on a single line for easy clicking.

1. **Click the link** — it should open in a new tab
2. Complete authentication in the browser and **copy the auth code**
3. Click back on the terminal and **paste** with `Shift+Insert` or `Ctrl+Shift+V`

If clicking the link doesn't work, hold `Ctrl+Shift` while selecting the URL with your mouse to copy it, then paste it into your browser's address bar.

### Scrolling and Session Persistence Trade-offs

**With tmux (`session_persistence: true`):**
- ✅ Session survives browser refresh/disconnect
- ✅ Can detach and reattach to running sessions
- ✅ Long-running Claude tasks continue in background
- ✅ Mouse wheel scrolling works (enters copy mode automatically)
- ✅ 20,000 line scrollback buffer
- ⚠️ Use middle-click or Shift+Insert to paste (right-click paste may not work)

**Without tmux (`session_persistence: false`):**
- ✅ Native browser scrolling
- ✅ Simpler terminal behavior
- ✅ Standard copy/paste behavior
- ❌ Session lost on browser refresh
- ❌ Session lost if add-on restarts

**Recommendation:**
- Use `session_persistence: true` (default) if you run long tasks or need to survive disconnects
- Use `session_persistence: false` if you need standard copy/paste behavior

## Security

### Authentication
- **No API keys in add-on config**: Claude Code handles authentication itself
- Credentials are stored securely in Claude Code's own directory (`~/.claude/`)
- This is more secure than storing keys in Home Assistant's configuration

### Container Security
- The Supervisor token is automatically managed and not exposed
- File access is limited to mapped directories
- The add-on runs in an isolated container

## Troubleshooting

### Authentication issues

Claude Code manages its own authentication. If you have issues:
1. Type `claude` to start the authentication flow
2. Follow the prompts to log in or enter your API key
3. Credentials are saved automatically for future sessions

**Can't copy the URL or paste the auth code?** The terminal uses tmux, which changes how copy/paste works. See [Copy and Paste in tmux](#copy-and-paste-in-tmux) for instructions.

### hass-mcp not working

1. Verify `enable_mcp` is true in configuration
2. Check add-on logs for connection errors
3. Restart the add-on after configuration changes

### Terminal not loading

1. Check that the add-on is running (green indicator)
2. Try refreshing the page
3. Check browser console for errors
4. Review add-on logs for ttyd errors

### Session not persisting

1. Ensure `session_persistence` is set to true
2. The session is named "claude" - it will auto-attach on reconnect

### Configuration changes not applying

After changing configuration:
1. Save the configuration
2. Restart the add-on completely

## Support

- [GitHub Issues](https://github.com/LuckyTriple7/HA-AddOns/issues)
- [Home Assistant Community](https://community.home-assistant.io/)
