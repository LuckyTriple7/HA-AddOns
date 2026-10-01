# Playwright Browser

Headless Chromium mit CDP-Endpoint für Browser-Automatisierung — wird vom **Claude Code Add-on** automatisch erkannt und verwendet.

## Verwendung

Dieses Add-on wird automatisch vom Claude Code Add-on erkannt wenn `enable_playwright_mcp` dort aktiviert ist. Claude Code verbindet sich dann über den CDP-Endpoint mit diesem Add-on und kann Websites aufrufen und steuern.

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `cdp_port` | `9222` | Port für den Chrome DevTools Protocol Endpoint |
| `idle_timeout` | `5` | Minuten ohne Verbindung, nach denen Chromium beendet wird |
| `enable_mcp` | `false` | Eigenen Playwright MCP-Server starten (Port 17799) |
| `mcp_token` | leer | Pflicht-Token für den MCP, mindestens 16 Zeichen |

## Eingebauter Playwright MCP

Mit `enable_mcp` läuft im Add-on ein eigener Playwright MCP-Server. Andere MCP-Clients wie LiteLLM oder Hermes können den Browser damit direkt steuern, ohne Claude Code Add-on.

- Endpoint: `http://<HA-Host>:17799/mcp` (Streamable HTTP)
- Anmeldung: Header `Authorization: Bearer <mcp_token>`. Anfragen ohne gültigen Token bekommen 401.
- Chromium startet erst bei der ersten Browser-Aktion. Nach `idle_timeout` Minuten ohne Aktion trennt sich der MCP vom Browser, nach weiteren `idle_timeout` Minuten wird Chromium beendet.
- Der Port ist im ganzen Heimnetz erreichbar, nicht nur über Tailscale. Deshalb ist der Token Pflicht; ohne gültigen Token (mindestens 16 Zeichen) startet der MCP nicht.

Beispiel für LiteLLM (`config.yaml`):

```yaml
mcp_servers:
  playwright_mcp:
    url: "http://<HA-Host>:17799/mcp"
    transport: "http"
    auth_type: "bearer_token"
    auth_value: os.environ/PLAYWRIGHT_MCP_TOKEN
```

## Voraussetzungen

- Claude Code Add-on installiert und gestartet (nur für die Nutzung über Claude Code)
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
| `idle_timeout` | `5` | Minutes without a connection after which Chromium is stopped |
| `enable_mcp` | `false` | Start a built-in Playwright MCP server (port 17799) |
| `mcp_token` | empty | Required MCP token, at least 16 characters |

## Built-in Playwright MCP

With `enable_mcp` the add-on runs its own Playwright MCP server. Other MCP clients such as LiteLLM or Hermes can then control the browser directly, without the Claude Code add-on.

- Endpoint: `http://<HA host>:17799/mcp` (Streamable HTTP)
- Authentication: header `Authorization: Bearer <mcp_token>`. Requests without a valid token get 401.
- Chromium only starts on the first browser action. After `idle_timeout` minutes without activity the MCP disconnects from the browser, and Chromium is stopped after another `idle_timeout` minutes.
- The port is reachable from the whole home network, not only via Tailscale. That is why the token is required; without a valid token (at least 16 characters) the MCP does not start.

Example for LiteLLM (`config.yaml`):

```yaml
mcp_servers:
  playwright_mcp:
    url: "http://<HA host>:17799/mcp"
    transport: "http"
    auth_type: "bearer_token"
    auth_value: os.environ/PLAYWRIGHT_MCP_TOKEN
```

## Requirements

- Claude Code add-on installed and running (only for use via Claude Code)
- `enable_playwright_mcp: true` set in the Claude Code add-on
