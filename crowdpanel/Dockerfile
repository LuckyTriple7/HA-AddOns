FROM python:3.14-alpine

LABEL org.opencontainers.image.title="CrowdPanel"
LABEL org.opencontainers.image.description="CrowdSec control panel for Home Assistant"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache curl

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Jede Datei einzeln — kein Platzhalter, sonst wandern dev_run.py und dev_data/
# mit ins Image.
COPY app.py .
COPY lapi.py .
# Nur wegen der Versionszeile — damit das Panel zeigen kann, welcher Stand laeuft.
COPY config.yaml .
COPY templates/ templates/
COPY static/ static/
COPY icon*.png static/
COPY locales/ locales/
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17797

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:17797/health || exit 1

CMD ["/run.sh"]
