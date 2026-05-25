#!/bin/sh
# Läuft als cont-init.d (root, vor nginx) — SMB-Mounts + PHP-Limits
OPTIONS=/data/options.json

PUID=$(jq -r '.PUID // 1000' "$OPTIONS" 2>/dev/null || echo 1000)
PGID=$(jq -r '.PGID // 1000' "$OPTIONS" 2>/dev/null || echo 1000)
MEMORY_LIMIT=$(jq -r '.memory_limit // "512M"' "$OPTIONS" 2>/dev/null || echo "512M")
UPLOAD_MAX=$(jq -r '.upload_max_filesize // "512M"' "$OPTIONS" 2>/dev/null || echo "512M")
POST_MAX=$(jq -r '.post_max_size // "512M"' "$OPTIONS" 2>/dev/null || echo "512M")

# /config/data anlegen und für linuxservers abc-User beschreibbar machen
mkdir -p /config/data
chown "$(id -u abc):$(id -g abc)" /config/data
chmod 755 /config/data

# PHP-Limits
mkdir -p /config/php
cat > /config/php/php-local.ini << EOF
memory_limit = ${MEMORY_LIMIT}
upload_max_filesize = ${UPLOAD_MAX}
post_max_size = ${POST_MAX}
max_execution_time = 300
max_input_time = 300
EOF
echo "[ha-init] PHP-Limits: memory=${MEMORY_LIMIT} upload=${UPLOAD_MAX} post=${POST_MAX}"

# PHP-FPM: mehr Worker-Prozesse (Standard linuxserver = 5, zu wenig)
for POOL_CONF in /etc/php*/php-fpm.d/www.conf; do
    [ -f "$POOL_CONF" ] || continue
    sed -i 's/^pm.max_children = .*/pm.max_children = 15/' "$POOL_CONF"
    sed -i 's/^pm.start_servers = .*/pm.start_servers = 5/' "$POOL_CONF"
    sed -i 's/^pm.min_spare_servers = .*/pm.min_spare_servers = 3/' "$POOL_CONF"
    sed -i 's/^pm.max_spare_servers = .*/pm.max_spare_servers = 10/' "$POOL_CONF"
    echo "[ha-init] PHP-FPM pool: max_children=15 (${POOL_CONF})"
done

# SMB-Mounts
do_mount() {
    SERVER=$1 SHARE=$2 USER=$3 PASS=$4 MOUNTPOINT=$5
    mkdir -p "$MOUNTPOINT"
    umount "$MOUNTPOINT" 2>/dev/null || true
    if ! nc -z -w 5 "$SERVER" 445 2>/dev/null; then
        echo "[ha-init] SMB FAIL: Port 445 auf ${SERVER} nicht erreichbar"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
        return
    fi
    OPTS="vers=3.0,uid=${PUID},gid=${PGID},file_mode=0755,dir_mode=0755,noperm,sec=ntlmssp,nodfs"
    [ -n "$USER" ] && OPTS="${OPTS},username=${USER}" || OPTS="${OPTS},guest"
    [ -n "$PASS" ] && OPTS="${OPTS},password=${PASS}"
    if mount -t cifs "//${SERVER}/${SHARE}" "$MOUNTPOINT" -o "$OPTS" 2>/tmp/smb_err; then
        echo "[ha-init] SMB OK: //${SERVER}/${SHARE} → ${MOUNTPOINT}"
    else
        echo "[ha-init] SMB FAIL: //${SERVER}/${SHARE}: $(cat /tmp/smb_err 2>/dev/null)"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
    fi
    rm -f /tmp/smb_err
}

for IDX in 1 2 3; do
    SERVER=$(jq -r ".smb_${IDX}_server // empty" "$OPTIONS" 2>/dev/null)
    SHARE=$(jq -r  ".smb_${IDX}_share // empty"  "$OPTIONS" 2>/dev/null)
    USER=$(jq -r   ".smb_${IDX}_user // empty"   "$OPTIONS" 2>/dev/null)
    PASS=$(jq -r   ".smb_${IDX}_password // empty" "$OPTIONS" 2>/dev/null)
    if [ -z "$SERVER" ]; then
        echo "[ha-init] SMB-${IDX}: nicht konfiguriert"
        continue
    fi
    [ -z "$SHARE" ] && echo "[ha-init] SMB-${IDX}: kein Share konfiguriert" && continue
    do_mount "$SERVER" "$SHARE" "$USER" "$PASS" "/mnt/smb${IDX}"
done

# Nginx security headers
cat > /config/nginx/security-headers.conf << 'HEADERS'
add_header Strict-Transport-Security "max-age=15552000; includeSubDomains; preload" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header Referrer-Policy "no-referrer" always;
add_header X-Permitted-Cross-Domain-Policies "none" always;
add_header X-XSS-Protection "1; mode=block" always;
HEADERS

NGINX_CONF=/config/nginx/site-confs/default.conf
if [ -f "$NGINX_CONF" ] && ! grep -q "security-headers.conf" "$NGINX_CONF"; then
    sed -i '/^server {/a\    include /config/nginx/security-headers.conf;' "$NGINX_CONF"
    echo "[ha-init] Nginx security headers: eingebunden"
else
    echo "[ha-init] Nginx security headers: bereits konfiguriert"
fi

echo "[ha-init] done"
