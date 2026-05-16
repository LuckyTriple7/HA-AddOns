FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=de_DE.UTF-8 \
    LANGUAGE=de_DE:de \
    LC_ALL=de_DE.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    firefox-esr \
    firefox-esr-l10n-de \
    tigervnc-standalone-server \
    novnc \
    websockify \
    openbox \
    autocutsel \
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

COPY rootfs/ /
RUN chmod +x /run.sh

EXPOSE 5800

CMD ["/run.sh"]
