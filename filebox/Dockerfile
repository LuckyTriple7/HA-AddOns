FROM debian:bookworm-slim

# FileBrowser Quantum (gtsteffaniak/filebrowser), Stable-Kanal
ARG FILEBROWSER_VERSION=2.0.2-stable
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    jq \
    cifs-utils \
    smbclient \
    netcat-openbsd \
    && curl -fsSL \
    "https://github.com/gtsteffaniak/filebrowser/releases/download/v${FILEBROWSER_VERSION}/linux-amd64-filebrowser" \
    -o /usr/local/bin/filebrowser \
    && chmod +x /usr/local/bin/filebrowser \
    && rm -rf /var/lib/apt/lists/*

COPY rootfs/ /
RUN chmod +x /run.sh

EXPOSE 17771
CMD ["/run.sh"]
