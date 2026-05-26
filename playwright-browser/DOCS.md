# Playwright Browser

Headless Chromium mit CDP-Endpoint für Browser-Automatisierung — wird vom **Claude Code Add-on** automatisch erkannt und verwendet.

## Verwendung

Dieses Add-on wird automatisch vom Claude Code Add-on erkannt wenn `enable_playwright_mcp` dort aktiviert ist. Claude Code verbindet sich dann über den CDP-Endpoint mit diesem Add-on und kann Websites aufrufen und steuern.

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `cdp_port` | `9222` | Port für den Chrome DevTools Protocol Endpoint |

## Voraussetzungen

- Claude Code Add-on installiert und gestartet
- `enable_playwright_mcp: true` im Claude Code Add-on gesetzt

---

# Playwright Browser (English)

Headless Chromium with CDP endpoint for browser automation — automatically detected and used by the **Claude Code add-on**.

## Usage

This add-on is automatically detected by the Claude Code add-on when `enable_playwright_mcp` is enabled there. Claude Code then connects to this add-on via the CDP endpoint and can browse and control websites.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `cdp_port` | `9222` | Port for the Chrome DevTools Protocol endpoint |

## Requirements

- Claude Code add-on installed and running
- `enable_playwright_mcp: true` set in the Claude Code add-on
