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

### [WhatsApp](whatsapp/)

WhatsApp Web als persistente Session direkt in Home Assistant — mit Chat-UI, REST-API und Webhook-Support.

- QR-Code einmalig scannen, Session bleibt über Neustarts erhalten
- Chat-Liste mit Kontaktnamen und Nachrichtenvorschau (wie WhatsApp Web)
- Nachrichten senden und empfangen direkt in der HA-Sidebar
- REST-API für Automatisierungen (`POST /api/send`)
- Webhook für eingehende Nachrichten (HA-Webhook-Trigger)
- Responsives Design für Desktop und Handy

→ [Dokumentation & Changelog](whatsapp/README.md)

---

# HA-AddOns (English)

Custom Home Assistant add-ons by [LuckyTriple7](https://github.com/LuckyTriple7).

> I'm not a traditional programmer — but with Claude Code as my AI assistant I develop and maintain these add-ons myself. Feedback and questions welcome as a [GitHub Issue](https://github.com/LuckyTriple7/HA-AddOns/issues).

## Installation

Add the repository in Home Assistant:

**Settings → Add-ons → Add-on Store → ⋮ → Repositories**

```
https://github.com/LuckyTriple7/HA-AddOns
```

## Add-ons

### [Claude Code](claudecode/)

AI assistant directly in Home Assistant — for creating automations, debugging and managing your configuration. Forked from [apbb2/robsonfelix-hass-addons](https://github.com/apbb2/robsonfelix-hass-addons/tree/main/claudecode) with a Playwright fix.

- Web terminal directly in the HA sidebar
- Full Home Assistant integration (MCP server)
- Playwright browser automation via CDP
- Automatic Claude Code updates on startup

→ [Documentation & Changelog](claudecode/README.md)

### [Playwright Browser](playwright-browser/)

Headless Chromium browser with CDP endpoint for browser automation. Used by the **Claude Code add-on** to browse and control websites.

- Chrome DevTools Protocol (CDP) on port 9222
- Automatically detected by the Claude Code add-on
- Supports amd64 and aarch64

→ [Documentation & Changelog](playwright-browser/README.md)

### [Webtop XFCE](ubuntu-webtop/)

Full XFCE desktop in the browser, directly integrated into Home Assistant.

- KasmVNC streaming (CPU-efficient, delta-based)
- System language German (de_DE.UTF-8)
- Firefox, Thunderbird, Geany, VLC, Thunar with SMB network access and more
- Persistent configuration across updates

| | |
|---|---|
| **HTTP access** | `http://<HA-IP>:7776` |
| **HTTPS access** | `https://<HA-IP>:7777` |
| **Username** | `abc` |

→ [Documentation & Changelog](ubuntu-webtop/README.md)

### [WhatsApp](whatsapp/)

WhatsApp Web as a persistent session directly in Home Assistant — with chat UI, REST API and webhook support.

- Scan QR code once, session persists across restarts
- Chat list with contact names and message preview (like WhatsApp Web)
- Send and receive messages directly in the HA sidebar
- REST API for automations (`POST /api/send`)
- Webhook for incoming messages (HA webhook trigger)
- Responsive design for desktop and mobile

→ [Documentation & Changelog](whatsapp/README.md)
