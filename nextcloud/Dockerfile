ARG BUILD_FROM
FROM lscr.io/linuxserver/nextcloud:latest

# cifs-utils für SMB-Mounts, mariadb-client für DB-Autodiscovery, jq für options.json
RUN apk add --no-cache \
    cifs-utils \
    samba-client \
    mariadb-client \
    jq \
    curl \
    netcat-openbsd

COPY rootfs/ /
RUN chmod +x /run.sh

CMD ["/run.sh"]
