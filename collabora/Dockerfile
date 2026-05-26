FROM collabora/code:latest

LABEL org.opencontainers.image.title="Collabora Online for Home Assistant"
LABEL org.opencontainers.image.description="Collabora Online office server for Nextcloud"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends jq gosu \
    && rm -rf /var/lib/apt/lists/*

COPY run.sh /run.sh
RUN chmod +x /run.sh

# run.sh läuft als root, wechselt via gosu zu cool (uid 1001) — wie alexbelgium
CMD ["/run.sh"]
