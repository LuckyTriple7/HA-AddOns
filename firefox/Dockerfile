FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=de_DE.UTF-8 \
    LANGUAGE=de_DE:de \
    LC_ALL=de_DE.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    firefox-esr \
    firefox-esr-l10n-de \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    locales \
    jq \
    procps \
    fonts-liberation \
    fonts-noto-core \
    && locale-gen de_DE.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

COPY rootfs/ /
RUN chmod +x /run.sh

EXPOSE 5800

CMD ["/run.sh"]
