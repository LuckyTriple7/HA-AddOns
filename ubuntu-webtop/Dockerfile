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

# Alle gepinnten Paketversionen — wenn sich eine ändert, werden alle nachfolgenden
# Layer (inkl. LibreOffice, XFCE, etc.) beim nächsten "Neu Aufbauen" rebuilt.
# BUILD_VERSION kommt aus config.yaml und wird von HA bei jedem Update übergeben.
ARG BUILD_VERSION
ARG IPSCAN_VERSION=3.9.3
ARG BITWARDEN_VERSION=2026.6.1
ARG VSCODE_VERSION=1.128.1
ARG GH_CLI_VERSION=2.96.0
ARG FIREFOX_VERSION=152.0.6
ARG THUNDERBIRD_VERSION=152.0.1
ARG RCLONE_VERSION=1.74.4

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
        pulseaudio \
        gvfs \
        gvfs-backends \
        gvfs-fuse \
        cifs-utils \
        smbclient \
        geany \
        gedit \
        nmap \
        ristretto \
        atril \
        vlc \
        vlc-plugin-access-extra \
        totem \
        gstreamer1.0-libav \
        gstreamer1.0-plugins-bad \
        galculator \
        xarchiver \
        flameshot \
        gthumb \
        remmina \
        remmina-plugin-rdp \
        remmina-plugin-vnc \
        baobab \
        seahorse \
        git \
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
        fuse3 \
        unzip \
        nfs-common \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# rclone direkt installieren (Debian-Paket ist veraltet und hat OneDrive-Download-Bug)
ARG RCLONE_VERSION
RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in \
        amd64)   RCLONE_ARCH="amd64" ;; \
        aarch64|arm64) RCLONE_ARCH="arm64" ;; \
        *) echo "Unsupported arch: $ARCH" && exit 1 ;; \
    esac \
    && curl -fsSL "https://downloads.rclone.org/v${RCLONE_VERSION}/rclone-v${RCLONE_VERSION}-linux-${RCLONE_ARCH}.zip" -o /tmp/rclone.zip \
    && unzip -q /tmp/rclone.zip -d /tmp/rclone \
    && cp "/tmp/rclone/rclone-v${RCLONE_VERSION}-linux-${RCLONE_ARCH}/rclone" /usr/local/bin/rclone \
    && chmod 755 /usr/local/bin/rclone \
    && rm -rf /tmp/rclone.zip /tmp/rclone

# Java separat installieren: /usr/share/man/man1 muss vorher existieren,
# sonst schlägt das ca-certificates-java Postinst-Skript im Docker-Build fehl.
RUN mkdir -p /usr/share/man/man1 \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        default-jre-headless \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# FUSE: user_allow_other erlauben, damit rclone-Mounts (als root gemountet) für abc erreichbar sind
RUN sed -i 's/^#user_allow_other/user_allow_other/' /etc/fuse.conf; \
    grep -q "^user_allow_other" /etc/fuse.conf || echo "user_allow_other" >> /etc/fuse.conf

# Angry IP Scanner: arch-spezifisches .deb extrahieren (enthält SWT-JAR für die GUI).
# Der _all.deb enthält kein SWT → NoClassDefFoundError bei Start.
# dpkg-deb -x umgeht die Dependency-Prüfung (Bookworm-inkompatible Deps).
RUN ARCH=$(dpkg --print-architecture) \
    && curl -fsSL \
        "https://github.com/angryip/ipscan/releases/download/${IPSCAN_VERSION}/ipscan_${IPSCAN_VERSION}_${ARCH}.deb" \
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

# Bitwarden Desktop: gepinnte Version, via GitHub Releases
# --no-sandbox Wrapper: Chrome-Sandbox braucht Kernel-Namespaces (in HA nicht verfügbar)
RUN ARCH=$(dpkg --print-architecture) \
    && curl -fsSL \
        "https://github.com/bitwarden/clients/releases/download/desktop-v${BITWARDEN_VERSION}/Bitwarden-${BITWARDEN_VERSION}-${ARCH}.deb" \
        -o /tmp/bitwarden.deb \
    && apt-get update \
    && apt-get install -y /tmp/bitwarden.deb \
    && rm -f /tmp/bitwarden.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && printf '#!/bin/sh\nexec /opt/Bitwarden/bitwarden-app --no-sandbox --disable-gpu "$@"\n' \
        > /usr/bin/bitwarden \
    && chmod +x /usr/bin/bitwarden \
    && sed -i 's|^Exec=.*|Exec=/opt/Bitwarden/bitwarden-app --no-sandbox --disable-gpu %U|' /usr/share/applications/bitwarden.desktop

# VS Code aus Microsofts offiziellem Debian-Repo installieren
RUN apt-get update \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        -o /etc/apt/keyrings/packages.microsoft.com.asc \
    && echo "deb [arch=amd64,arm64 signed-by=/etc/apt/keyrings/packages.microsoft.com.asc] https://packages.microsoft.com/repos/code stable main" \
        > /etc/apt/sources.list.d/vscode.list \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        code \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && mv /usr/bin/code /usr/bin/code.orig \
    && printf '#!/bin/sh\nexec /usr/bin/code.orig --no-sandbox --disable-gpu "$@"\n' > /usr/bin/code \
    && chmod +x /usr/bin/code \
    && sed -i '/^Exec=/ s|/usr/share/code/code |/usr/share/code/code --no-sandbox --disable-gpu |g' /usr/share/applications/code.desktop \
    && sed -i '/^Exec=/ s|/usr/share/code/code |/usr/share/code/code --no-sandbox --disable-gpu |g' /usr/share/applications/code-url-handler.desktop 2>/dev/null || true

# GitHub CLI aus offiziellem GitHub-Repo installieren
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        gh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

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

# Claude Desktop (Electron, inoffizielles Debian-Paket von aaddrick/claude-desktop-debian)
# --no-sandbox Wrapper: Chrome-Sandbox braucht Kernel-Namespaces (in HA nicht verfügbar)
RUN curl -fsSL https://pkg.claude-desktop-debian.dev/KEY.gpg \
        | gpg --dearmor -o /usr/share/keyrings/claude-desktop.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/claude-desktop.gpg arch=amd64,arm64] https://pkg.claude-desktop-debian.dev stable main" \
        > /etc/apt/sources.list.d/claude-desktop.list \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        claude-desktop \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && CLAUDE_BIN=$(find /opt /usr/lib /usr/bin -name "claude-desktop" -type f 2>/dev/null | head -1) \
    && if [ -n "$CLAUDE_BIN" ] && [ "$CLAUDE_BIN" != "/usr/bin/claude-desktop" ]; then \
        printf '#!/bin/sh\nexec "%s" --no-sandbox --disable-gpu "$@"\n' "$CLAUDE_BIN" > /usr/bin/claude-desktop \
        && chmod +x /usr/bin/claude-desktop; \
    else \
        mv /usr/bin/claude-desktop /usr/bin/claude-desktop.orig 2>/dev/null || true \
        && printf '#!/bin/sh\nexec /usr/bin/claude-desktop.orig --no-sandbox --disable-gpu "$@"\n' > /usr/bin/claude-desktop \
        && chmod +x /usr/bin/claude-desktop; \
    fi \
    && sed -i 's|^Exec=.*claude-desktop.*|Exec=/usr/bin/claude-desktop %U|' \
        /usr/share/applications/claude-desktop.desktop 2>/dev/null || true

# Totem als Standard-Videoplayer für alle gängigen Formate setzen
RUN printf '[Default Applications]\nvideo/mp4=org.gnome.Totem.desktop\nvideo/x-msvideo=org.gnome.Totem.desktop\nvideo/x-matroska=org.gnome.Totem.desktop\nvideo/quicktime=org.gnome.Totem.desktop\nvideo/mpeg=org.gnome.Totem.desktop\nvideo/webm=org.gnome.Totem.desktop\nvideo/x-m4v=org.gnome.Totem.desktop\nvideo/3gpp=org.gnome.Totem.desktop\nvideo/x-flv=org.gnome.Totem.desktop\nvideo/x-ms-wmv=org.gnome.Totem.desktop\n' \
    > /usr/share/applications/mimeapps.list

# Tracker3 (Indexierungsdienst) und dleyna (DLNA) Grilo-Plugins entfernen — im Container nicht verfügbar
RUN find /usr/lib -name "libgrltracker3.so" -delete \
    && find /usr/lib -name "libgrldleyna.so" -delete

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
