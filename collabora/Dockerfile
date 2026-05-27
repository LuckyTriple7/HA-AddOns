FROM collabora/code:latest

LABEL org.opencontainers.image.title="Collabora Online for Home Assistant"
LABEL org.opencontainers.image.description="Collabora Online office server for Nextcloud"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends jq xmlstarlet \
    && rm -rf /var/lib/apt/lists/*

# cool user braucht Schreibrecht auf /etc/coolwsd (coolwsd.xml Symlink)
RUN chown -R cool:cool /etc/coolwsd

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
