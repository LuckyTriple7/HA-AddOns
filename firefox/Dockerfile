FROM jlesage/baseimage-gui:debian-12-v4

ENV APP_NAME="Firefox" \
    LANG=de_DE.UTF-8

# curl/ca-certificates für Firefox-Download, jq für Optionen-Parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

ARG FIREFOX_VERSION=128.10.0esr
RUN curl -sL --fail \
    "https://releases.mozilla.org/pub/firefox/releases/${FIREFOX_VERSION}/linux-x86_64/en-US/firefox-${FIREFOX_VERSION}.tar.bz2" \
    -o /tmp/firefox.tar.bz2 \
    && tar -xj -C /opt -f /tmp/firefox.tar.bz2 \
    && ln -sf /opt/firefox/firefox /usr/local/bin/firefox \
    && rm /tmp/firefox.tar.bz2

COPY rootfs/ /
RUN chmod +x /startapp.sh
