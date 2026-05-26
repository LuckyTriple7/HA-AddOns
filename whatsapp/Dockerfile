ARG BUILD_ARCH=amd64
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base:latest

LABEL org.opencontainers.image.title="WhatsApp for Home Assistant"
LABEL org.opencontainers.image.description="WhatsApp Web with REST API and webhook support"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

# Install Node.js, Chromium and dependencies
RUN apk add --no-cache \
    nodejs \
    npm \
    chromium \
    chromium-chromedriver \
    curl \
    jq \
    ca-certificates \
    font-noto \
    font-noto-emoji \
    && update-ca-certificates

# Prevent Puppeteer from downloading its own Chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV CHROMIUM_PATH=/usr/bin/chromium-browser

WORKDIR /app

COPY package.json .
RUN npm install --omit=dev --no-fund --no-audit

COPY server.js .
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17776

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:17776/api/status || exit 1

CMD ["/run.sh"]
