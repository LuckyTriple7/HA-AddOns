ARG BUILD_FROM
FROM lscr.io/linuxserver/nextcloud:latest

# cifs-utils für SMB-Mounts, jq für options.json
RUN apk add --no-cache \
    cifs-utils \
    samba-client \
    mariadb-client \
    jq \
    curl \
    netcat-openbsd

COPY rootfs/ /
RUN chmod +x /ha-config.sh /etc/cont-init.d/30-ha-init.sh

# ha-config.sh am Ende von linuxservers Nextcloud-Init ausführen
# (genau wie alexbelgium: nach occ-Init, vor nginx-Start)
RUN echo "[ -f /ha-config.sh ] && /ha-config.sh || true" \
    >> /etc/s6-overlay/s6-rc.d/init-nextcloud-config/run
