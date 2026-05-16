FROM jlesage/baseimage-gui:debian-12-v4

ENV APP_NAME="Firefox" \
    LANG=de_DE.UTF-8 \
    KEEP_APP_RUNNING=1 \
    DISPLAY_WIDTH=1280 \
    DISPLAY_HEIGHT=720

# curl/ca-certificates für Firefox-Download, xz-utils für .tar.xz, jq für Optionen-Parsing
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
