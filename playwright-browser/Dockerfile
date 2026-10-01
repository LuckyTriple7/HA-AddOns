# Playwright MCP needs Node.js 20+, Debian bookworm only ships 18.
# Install it in the official Node image and copy node + the package over.
FROM node:22-bookworm-slim AS mcp

ARG PLAYWRIGHT_MCP_VERSION=0.0.83
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /opt/playwright-mcp
RUN npm install --omit=dev --no-audit --no-fund "@playwright/mcp@${PLAYWRIGHT_MCP_VERSION}"

FROM debian:bookworm-slim

LABEL \
    io.hass.version="1.0.16" \
    io.hass.type="addon" \
    io.hass.arch="amd64|aarch64"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        chromium \
        python3 \
        curl \
        jq \
    && rm -rf /var/lib/apt/lists/*

COPY --from=mcp /usr/local/bin/node /usr/local/bin/node
COPY --from=mcp /opt/playwright-mcp /opt/playwright-mcp

COPY run.sh /run.sh
COPY cdp_proxy.py /cdp_proxy.py
COPY mcp_proxy.py /mcp_proxy.py
RUN chmod +x /run.sh

EXPOSE 9222 17799

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:9222/json/version || exit 1

CMD ["/run.sh"]
