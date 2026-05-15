# Playwright Browser

Headless Chromium mit CDP-Endpoint (Chrome DevTools Protocol) für Browser-Automatisierung in Home Assistant.

## Verwendung

Das Add-on wird vom **Claude Code Add-on** automatisch erkannt und als Browser-Backend verwendet. Wenn `enable_playwright_mcp` im Claude Code Add-on aktiviert ist, verbindet sich Claude Code automatisch mit diesem Add-on über den CDP-Endpoint.

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `cdp_port` | `9222` | Port für den Chrome DevTools Protocol Endpoint |

## Funktionsweise

1. Chromium startet im Headless-Modus auf einem internen Port
2. Ein Python-CDP-Proxy leitet den konfigurierten CDP-Port auf den internen Port weiter
3. Der Proxy rewritet `localhost`-Adressen in den HTTP-Antworten, damit WebSocket-Verbindungen von außerhalb des Containers funktionieren
4. Das Claude Code Add-on findet dieses Add-on automatisch über die Supervisor API und registriert `@playwright/mcp` als MCP-Server

## Voraussetzungen

- Home Assistant OS oder Supervised
- Claude Code Add-on (optional, für KI-gesteuerte Browser-Automatisierung)
