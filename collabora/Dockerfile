# Gepinnt auf letzten bekannt funktionierenden Digest (Debian-basiert, apt/su vorhanden).
# collabora/code:latest ist seit 26.04.2.2 (2026-07-18) ein Nix-Rootfs ohne Shell/apt/su
# und schifft /opt/cool/systemplate ohne den LO-Share-Template-Baum (kein
# coolwsd-systemplate-setup/coolconfig im Image) -> Dokumente lassen sich damit nicht
# öffnen ("type detection failed"). Nicht wieder auf :latest umstellen, ohne das
# vorher in einem Testcontainer zu verifizieren.
FROM collabora/code@sha256:f8a308bcd12ad09babcd635662b512776b0749fc04c9a63db568865bd195b4d9

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
