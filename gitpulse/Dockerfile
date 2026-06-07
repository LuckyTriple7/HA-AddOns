FROM python:3.11-alpine

LABEL org.opencontainers.image.title="GitPulse"
LABEL org.opencontainers.image.description="GitHub Control Panel for Home Assistant"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache curl

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ templates/
COPY static/ static/
COPY icon*.png static/
COPY locales/ locales/
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17792

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:17792/health || exit 1

CMD ["/run.sh"]
