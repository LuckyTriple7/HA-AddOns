##################################
#  Ubuntu Webtop XFCE – HA Addon #
##################################

ARG BUILD_FROM=ghcr.io/linuxserver/baseimage-kasmvnc:debianbookworm
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

# XFCE Desktop-Umgebung + Anwendungen installieren
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        xfwm4 \
        xfdesktop4 \
        xfce4-panel \
        xfce4-settings \
        xfce4-terminal \
        xfce4-notifyd \
        xfce4-taskmanager \
        thunar \
        thunar-volman \
        tumbler \
        gvfs \
        gvfs-backends \
        gvfs-fuse \
        cifs-utils \
        smbclient \
        geany \
        nmap \
        ristretto \
        atril \
        vlc \
        galculator \
        xarchiver \
        flameshot \
        pinta \
        jq \
        curl \
        gnupg \
        ca-certificates \
        dbus-x11 \
        locales \
        desktop-base \
        libreoffice \
        libreoffice-l10n-de \
        libreoffice-help-de \
        gnome-keyring \
        libsecret-tools \
        putty \
        avahi-daemon \
        inotify-tools \
        iputils-ping \
        iputils-tracepath \
        traceroute \
        python3-gi \
        python3-gi-cairo \
        gir1.2-gtk-3.0 \
        xdg-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Java separat installieren: /usr/share/man/man1 muss vorher existieren,
# sonst schlägt das ca-certificates-java Postinst-Skript im Docker-Build fehl.
RUN mkdir -p /usr/share/man/man1 \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        default-jre-headless \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Angry IP Scanner: arch-spezifisches .deb extrahieren (enthält SWT-JAR für die GUI).
# Der _all.deb enthält kein SWT → NoClassDefFoundError bei Start.
# dpkg-deb -x umgeht die Dependency-Prüfung (Bookworm-inkompatible Deps).
RUN ARCH=$(dpkg --print-architecture) \
    && curl -fsSL \
        "https://github.com/angryip/ipscan/releases/download/3.9.3/ipscan_3.9.3_${ARCH}.deb" \
        -o /tmp/ipscan.deb \
    && dpkg-deb -x /tmp/ipscan.deb /tmp/ipscan \
    && find /tmp/ipscan -name "*.jar" -exec install -Dm644 {} /usr/share/ipscan/ipscan.jar \; \
    && find /tmp/ipscan/usr/share/applications -name "*.desktop" \
        -exec cp {} /usr/share/applications/ \; 2>/dev/null || true \
    && find /tmp/ipscan/usr/share/pixmaps -name "ipscan*" \
        -exec cp {} /usr/share/pixmaps/ \; 2>/dev/null || true \
    && printf '#!/bin/sh\nexec java -jar /usr/share/ipscan/ipscan.jar "$@"\n' \
        > /usr/bin/ipscan \
    && chmod +x /usr/bin/ipscan \
    && rm -rf /tmp/ipscan*

# Bitwarden Desktop: neueste stabile Version via GitHub API
# --no-sandbox Wrapper: Chrome-Sandbox braucht Kernel-Namespaces (in HA nicht verfügbar)
RUN ARCH=$(dpkg --print-architecture) \
    && BW_VERSION=$(curl -fsSL "https://api.github.com/repos/bitwarden/clients/releases" \
        | jq -r '[.[] | select(.tag_name | startswith("desktop-v")) | select(.prerelease==false)][0].tag_name' \
        | sed 's/desktop-v//') \
    && curl -fsSL \
        "https://github.com/bitwarden/clients/releases/download/desktop-v${BW_VERSION}/Bitwarden-${BW_VERSION}-${ARCH}.deb" \
        -o /tmp/bitwarden.deb \
    && apt-get update \
    && apt-get install -y /tmp/bitwarden.deb \
    && rm -f /tmp/bitwarden.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && printf '#!/bin/sh\nexec /opt/Bitwarden/bitwarden-app --no-sandbox "$@"\n' \
        > /usr/bin/bitwarden \
    && chmod +x /usr/bin/bitwarden \
    && sed -i 's|^Exec=.*|Exec=/opt/Bitwarden/bitwarden-app --no-sandbox %U|' /usr/share/applications/bitwarden.desktop

# Firefox + Thunderbird über Mozillas offizielles Debian-Repo installieren
RUN apt-get update \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://packages.mozilla.org/apt/repo-signing-key.gpg \
        -o /etc/apt/keyrings/packages.mozilla.org.asc \
    && echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" \
        > /etc/apt/sources.list.d/mozilla.list \
    && printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1001\n' \
        > /etc/apt/preferences.d/mozilla \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        firefox \
        firefox-l10n-de \
        thunderbird \
        thunderbird-l10n-de \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Deutsche Locale generieren
RUN sed -i 's/# de_DE.UTF-8 UTF-8/de_DE.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && update-locale LANG=de_DE.UTF-8

# Eigene rootfs-Skripte einspielen
COPY rootfs/ /
RUN find /etc/cont-init.d -type f -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true \
    && chmod +x /usr/local/bin/geany-gio

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
