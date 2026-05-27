FROM collabora/code:latest

LABEL org.opencontainers.image.title="Collabora Online for Home Assistant"
LABEL org.opencontainers.image.description="Collabora Online office server for Nextcloud"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends jq curl \
    && rm -rf /var/lib/apt/lists/*

# ttyd für Web-Terminal (Ingress)
RUN curl -L https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64 \
    -o /usr/local/bin/ttyd && chmod +x /usr/local/bin/ttyd

# cool user braucht Schreibrecht auf /etc/coolwsd (coolwsd.xml Symlink)
RUN chown -R cool:cool /etc/coolwsd

COPY run.sh /run.sh
RUN chmod +x /run.sh

ENTRYPOINT ["/run.sh"]
