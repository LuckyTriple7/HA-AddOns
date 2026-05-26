FROM collabora/code:latest

LABEL org.opencontainers.image.title="Collabora Online for Home Assistant"
LABEL org.opencontainers.image.description="Collabora Online office server for Nextcloud"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*

# Allow cool user to write credentials into coolwsd.xml at startup
RUN chown -R cool:cool /etc/coolwsd

COPY run.sh /run.sh
RUN chmod +x /run.sh

# Restore cool user — newer Collabora images expect to run as cool, not root
USER cool

CMD ["/run.sh"]
