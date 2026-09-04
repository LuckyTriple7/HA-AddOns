FROM python:3.14-alpine

LABEL org.opencontainers.image.title="NetToolbox"
LABEL org.opencontainers.image.description="Network and mail diagnostics for Home Assistant"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache curl iputils traceroute

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Jede Datei einzeln — kein Platzhalter, sonst wandern dev_run.py und dev_data/
# mit ins Image.
COPY app.py .
COPY netcore.py .
COPY mailauth.py .
COPY mailprovider.py .
COPY blocklists.py .
COPY tlscheck.py .
COPY domaininfo.py .
COPY httpcheck.py .
COPY smtpcheck.py .
COPY quiccheck.py .
COPY seocheck.py .
COPY netutils.py .
COPY geoip.py .
COPY monitor.py .
COPY settings.py .
COPY probes.py .
COPY remote.py .
# Nur wegen der Versionszeile — damit das Panel zeigen kann, welcher Stand laeuft.
COPY config.yaml .
COPY templates/ templates/
COPY static/ static/
COPY icon*.png static/
COPY locales/ locales/
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17798

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:17798/health || exit 1

CMD ["/run.sh"]
