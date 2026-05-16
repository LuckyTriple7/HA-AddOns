FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=de_DE.UTF-8 \
    LANGUAGE=de_DE:de \
    LC_ALL=de_DE.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    firefox-esr \
    firefox-esr-l10n-de \
    tigervnc-standalone-server \
    websockify \
    matchbox-window-manager \
    autocutsel \
    curl \
    locales \
    dbus-x11 \
    libpci3 \
    libegl1 \
    libgl1-mesa-dri \
    libdbus-glib-1-2 \
    jq \
    procps \
    fonts-liberation \
    fonts-noto-core \
    && sed -i 's/# de_DE.UTF-8 UTF-8/de_DE.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && update-locale LANG=de_DE.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# noVNC direkt von GitHub (neueste Version) — enthält automatischen Clipboard-Sync
# via Browser Clipboard API (navigator.clipboard); Debian-Paket ist zu alt dafür
RUN NOVNC_TAG=$(curl -s https://api.github.com/repos/novnc/noVNC/releases/latest | grep '"tag_name"' | cut -d'"' -f4) \
    && NOVNC_VERSION=$(echo "$NOVNC_TAG" | tr -d 'v') \
    && echo "Installing noVNC ${NOVNC_TAG}" \
    && curl -sL "https://github.com/novnc/noVNC/archive/refs/tags/${NOVNC_TAG}.tar.gz" \
       | tar -xz -C /opt \
    && mv /opt/noVNC-${NOVNC_VERSION} /opt/novnc

COPY rootfs/ /
RUN chmod +x /run.sh

EXPOSE 5800

CMD ["/run.sh"]
