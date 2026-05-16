# Stage 1: Firefox-Laufzeit-Abhängigkeiten aus sauberem Debian holen.
# jlesage's Debian-Base hat keine GUI-Pakete in seinen Repos — deswegen
# schlägt apt-get install libgtk-3-0 etc. dort fehl.
FROM debian:bookworm-slim AS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libxt6 \
    libpci3 \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Hauptimage auf jlesage-Basis
FROM jlesage/baseimage-gui:debian-12-v4

ENV APP_NAME="Firefox" \
    LANG=de_DE.UTF-8 \
    KEEP_APP_RUNNING=1 \
    DISPLAY_WIDTH=1280 \
    DISPLAY_HEIGHT=720 \
    USER_ID=0 \
    GROUP_ID=0

# GTK3 und alle transitiven Abhängigkeiten aus Stage 1 übernehmen.
# COPY überschreibt nicht — jlesage-eigene Libs bleiben erhalten.
COPY --from=deps /usr/lib/x86_64-linux-gnu /usr/lib/x86_64-linux-gnu
RUN ldconfig

# Kleine Utilities: diese Pakete sind in jlesage's konfigurierten Repos vorhanden
# (nur GUI-Pakete wie libgtk-3-0 fehlen dort).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    jq \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*
ARG FIREFOX_VERSION=140.10.2esr
RUN curl -sL --fail \
    "https://releases.mozilla.org/pub/firefox/releases/${FIREFOX_VERSION}/linux-x86_64/en-US/firefox-${FIREFOX_VERSION}.tar.xz" \
    -o /tmp/firefox.tar.xz \
    && tar -xJ -C /opt -f /tmp/firefox.tar.xz \
    && ln -sf /opt/firefox/firefox /usr/local/bin/firefox \
    && rm /tmp/firefox.tar.xz

COPY rootfs/ /
RUN chmod +x /startapp.sh \
    /etc/cont-init.d/08-clear-tmp-dir.sh \
    /etc/cont-env.d/DISPLAY_WIDTH \
    /etc/cont-env.d/DISPLAY_HEIGHT \
    /etc/cont-env.d/DARK_MODE \
    /etc/cont-env.d/VNC_PASSWORD \
    /etc/cont-env.d/KEEP_APP_RUNNING \
    /etc/cont-env.d/TZ
