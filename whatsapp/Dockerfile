FROM node:24-alpine3.24

LABEL org.opencontainers.image.title="WhatsApp for Home Assistant"
LABEL org.opencontainers.image.description="WhatsApp Web with REST API and webhook support"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

# Install Chromium and dependencies
RUN apk add --no-cache \
    chromium=155.0.8059.84-r0 \
    chromium-chromedriver=155.0.8059.84-r0 \
    curl=8.23.0-r0 \
    jq=1.8.2-r0 \
    ca-certificates=20261020-r0 \
    font-noto=2026.06.01-r0 \
    font-noto-emoji=2.051-r0 \
    && update-ca-certificates

# Prevent Puppeteer from downloading its own Chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV CHROMIUM_PATH=/usr/bin/chromium-browser

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-fund --no-audit

COPY patches/ ./patches/
RUN for f in patches/*.js; do node "$f" || exit 1; done

COPY server.js .
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17776

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:17776/api/status || exit 1

CMD ["/run.sh"]
