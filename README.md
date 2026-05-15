# HA-AddOns

Eigene Home Assistant Add-ons von [LuckyTriple7](https://github.com/LuckyTriple7).

## Installation

Repository in Home Assistant hinzufügen:

**Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**

```
https://github.com/LuckyTriple7/HA-AddOns
```

## Add-ons

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

### [Playwright Browser](playwright-browser/)

Headless-Chromium-Browser mit CDP-Endpoint für Browser-Automatisierung. Wird vom **Claude Code Add-on** verwendet, um Websites aufzurufen und zu steuern.

- Chrome DevTools Protocol (CDP) auf Port 9222
- Automatisch erkannt vom Claude Code Add-on
- Unterstützung für amd64 und aarch64

→ [Dokumentation & Changelog](playwright-browser/README.md)
