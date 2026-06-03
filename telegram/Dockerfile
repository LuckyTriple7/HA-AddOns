FROM node:lts-alpine

LABEL org.opencontainers.image.title="Telegram for Home Assistant"
LABEL org.opencontainers.image.description="Telegram client with chat UI, REST API and webhook support"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache \
    jq \
    ca-certificates \
    python3 \
    make \
    g++ \
    && update-ca-certificates

WORKDIR /ui

COPY package.json ./
RUN npm install --omit=dev --no-fund --no-audit \
    && apk del python3 make g++

COPY server.js ./
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
