##################################
#  Ubuntu Webtop XFCE – HA Addon #
##################################

ARG BUILD_FROM=lscr.io/linuxserver/webtop:ubuntu-xfce
ARG BUILD_VERSION

FROM ${BUILD_FROM}

# S6-Overlay: Warte auf Services und setze Timeouts
ENV S6_CMD_WAIT_FOR_SERVICES=1 \
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0 \
    S6_SERVICES_GRACETIME=0

USER root

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# s6-run-Skripte auf set +e patchen, damit einzelne Fehler den Start nicht abbrechen
RUN if ls /etc/services.d/*/run 1>/dev/null 2>&1; then \
        sed -i "1a set +e" /etc/services.d/*/run; \
    fi

# Firefox über Mozilla-PPA installieren (Ubuntu 22.04+ liefert Firefox nur als Snap aus,
# das in Containern ohne systemd nicht funktioniert)
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        software-properties-common \
        jq \
        curl \
        gnupg \
    && add-apt-repository -y ppa:mozillateam/ppa \
    && printf 'Package: *\nPin: release o=LP-PPA-mozillateam\nPin-Priority: 1001\n' \
        > /etc/apt/preferences.d/mozilla-firefox \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        firefox \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Eigene rootfs-Skripte einspielen
COPY rootfs/ /
RUN find /etc/cont-init.d -type f -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true

# Entrypoint installieren
COPY ha_entrypoint.sh /ha_entrypoint.sh
RUN chmod 755 /ha_entrypoint.sh

ENTRYPOINT ["/usr/bin/env"]
CMD ["/ha_entrypoint.sh"]

############
# Labels   #
############

ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ENV BUILD_VERSION="${BUILD_VERSION}"

LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION} \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.created=${BUILD_DATE} \
    org.opencontainers.image.revision=${BUILD_REF} \
    org.opencontainers.image.version=${BUILD_VERSION}
