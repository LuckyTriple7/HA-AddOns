# HA-AddOns

Eigene Home Assistant Add-ons von [LuckyTriple7](https://github.com/LuckyTriple7).

> Ich bin kein klassischer Programmierer — aber mit Claude Code als KI-Assistenten entwickle und pflege ich diese Add-ons selbst. Feedback und Fragen gerne als [GitHub Issue](https://github.com/LuckyTriple7/HA-AddOns/issues).

## Installation

Repository in Home Assistant hinzufügen:

**Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**

```
https://github.com/LuckyTriple7/HA-AddOns
```

## Add-ons

### [Claude Code](claudecode/)

KI-Assistent direkt in Home Assistant — zum Erstellen von Automatisierungen, Debuggen und Verwalten der Konfiguration. Fork von [apbb2/robsonfelix-hass-addons](https://github.com/apbb2/robsonfelix-hass-addons/tree/main/claudecode) mit Playwright-Fix.

- Web-Terminal direkt in der HA-Sidebar
- Vollständige Integration mit Home Assistant (MCP-Server)
- Playwright-Browser-Automatisierung über CDP
- Automatische Claude Code Updates beim Start

→ [Dokumentation & Changelog](claudecode/README.md)

### [Playwright Browser](playwright-browser/)

Headless-Chromium-Browser mit CDP-Endpoint für Browser-Automatisierung. Wird vom **Claude Code Add-on** verwendet, um Websites aufzurufen und zu steuern.

- Chrome DevTools Protocol (CDP) auf Port 9222
- Automatisch erkannt vom Claude Code Add-on
- Unterstützung für amd64 und aarch64

→ [Dokumentation & Changelog](playwright-browser/README.md)

### [Webtop XFCE](ubuntu-webtop/)

Vollständiger XFCE-Desktop im Webbrowser, direkt in Home Assistant integriert.

- KasmVNC-Streaming (CPU-effizient, delta-basiert)
- Systemsprache Deutsch (de_DE.UTF-8)
- Firefox, Thunderbird, Geany, VLC, Thunar mit SMB-Netzwerkzugriff und mehr
- Persistente Konfiguration über Updates hinweg

| | |
|---|---|
| **Zugriff HTTP** | `http://<HA-IP>:7776` |
| **Zugriff HTTPS** | `https://<HA-IP>:7777` |
| **Benutzername** | `abc` |

→ [Dokumentation & Changelog](ubuntu-webtop/README.md)
