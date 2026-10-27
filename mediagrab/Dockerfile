FROM python:3.15-alpine3.24

LABEL org.opencontainers.image.title="MediaGrab"
LABEL org.opencontainers.image.description="yt-dlp Web-GUI for Home Assistant"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="GPL-2.0-or-later AND LGPL-2.1-or-later AND MIT"

RUN apk add --no-cache \
    ffmpeg=8.1.3-r0 \
    curl=8.23.0-r0

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN yt-dlp --version

COPY app.py .
COPY templates/ templates/
COPY static/ static/
COPY icon*.png static/
COPY locales/ locales/
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17791

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:17791/health || exit 1

CMD ["/run.sh"]
