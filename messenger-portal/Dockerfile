ARG BUILD_ARCH=amd64
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base:latest

LABEL org.opencontainers.image.title="MessengerPortal for Home Assistant"
LABEL org.opencontainers.image.description="Central launcher for Messenger add-ons with login protection"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache \
    python3 \
    py3-pip \
    curl \
    jq

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY app.py .
COPY templates/ templates/
COPY static/ static/
COPY icon-192.png static/icon-192.png
COPY icon-512.png static/icon-512.png
COPY locales/ locales/
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17770

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:17770/health || exit 1

CMD ["/run.sh"]
