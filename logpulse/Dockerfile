FROM debian:bookworm-slim

LABEL org.opencontainers.image.title="LogPulse"
LABEL org.opencontainers.image.description="Centralized journald log collector for Home Assistant"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-systemd curl jq tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY app.py journal_reader.py ./
COPY templates/ templates/
COPY static/ static/
COPY locales/ locales/
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17795

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:17795/health || exit 1

CMD ["/run.sh"]
