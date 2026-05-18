FROM debian:bookworm-slim

ARG FILEBROWSER_VERSION=2.63.3
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    jq \
    cifs-utils \
    smbclient \
    && curl -fsSL \
    "https://github.com/filebrowser/filebrowser/releases/download/v${FILEBROWSER_VERSION}/linux-amd64-filebrowser.tar.gz" \
    -o /tmp/filebrowser.tar.gz \
    && tar -xz -C /usr/local/bin -f /tmp/filebrowser.tar.gz filebrowser \
    && rm /tmp/filebrowser.tar.gz \
    && rm -rf /var/lib/apt/lists/*

COPY rootfs/ /
RUN chmod +x /run.sh

EXPOSE 17771
CMD ["/run.sh"]
