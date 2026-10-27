FROM node:lts-alpine3.24

LABEL org.opencontainers.image.title="Telegram for Home Assistant"
LABEL org.opencontainers.image.description="Telegram client with chat UI, REST API and webhook support"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache \
    jq=1.8.2-r0 \
    ca-certificates=20261020-r0 \
    python3=3.14.8-r0 \
    make=4.4.1-r4 \
    g++ \
    && update-ca-certificates

WORKDIR /ui

COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-fund --no-audit \
    && apk del python3 make g++

COPY server.js mystatus.js status_templates.js ./
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
