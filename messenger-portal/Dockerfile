FROM python:3.15-alpine3.24

LABEL org.opencontainers.image.title="MessengerPortal for Home Assistant"
LABEL org.opencontainers.image.description="Central launcher for Messenger add-ons with login protection"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache \
    curl=8.23.0-r0 \
    jq=1.8.2-r0 \
    nginx=1.30.6-r0 \
    font-dejavu=2.37-r6 \
    ffmpeg=8.1.3-r0

# Remove default nginx config
RUN rm -f /etc/nginx/http.d/default.conf

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY gen_nginx.py .
COPY addon_hosts.py .
COPY status_mirror.py .
COPY status_queue.py .
COPY templates/ templates/
COPY static/ static/
COPY icon-192.png static/icon-192.png
COPY icon-512.png static/icon-512.png
COPY locales/ locales/
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17770 8099

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:17770/health || exit 1

CMD ["/run.sh"]
