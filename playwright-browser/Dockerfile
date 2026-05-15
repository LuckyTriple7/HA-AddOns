ARG BUILD_FROM
FROM ${BUILD_FROM}

LABEL \
    io.hass.version="1.0.2" \
    io.hass.type="addon" \
    io.hass.arch="amd64|aarch64"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        chromium \
        curl \
        jq \
    && rm -rf /var/lib/apt/lists/*

COPY run.sh /run.sh
COPY cdp_proxy.py /cdp_proxy.py
RUN chmod +x /run.sh

EXPOSE 9222

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:9222/json/version || exit 1

CMD ["/run.sh"]
