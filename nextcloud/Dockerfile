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

# ttyd für Web-Terminal (Ingress)
RUN curl -L https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64 \
    -o /usr/local/bin/ttyd && \
    chmod +x /usr/local/bin/ttyd

COPY rootfs/ /
RUN chmod +x /ha-config.sh /etc/cont-init.d/30-ha-init.sh /etc/s6-overlay/s6-rc.d/svc-ttyd/run /etc/s6-overlay/s6-rc.d/svc-wopi-updater/run

# ha-config.sh am Ende von linuxservers Nextcloud-Init ausführen
# (genau wie alexbelgium: nach occ-Init, vor nginx-Start)
RUN echo "[ -f /ha-config.sh ] && /ha-config.sh || true" \
    >> /etc/s6-overlay/s6-rc.d/init-nextcloud-config/run
