#!/bin/bash
set -e

# Read HA options
NEXTCLOUD_URL=$(jq -r '.nextcloud_url // ""' /data/options.json)
ALIASGROUP1=$(jq -r '.aliasgroup1 // ""' /data/options.json)
DOMAIN1=$(jq -r '.domain1 // ""' /data/options.json)
ADMIN_USER=$(jq -r '.admin_user // "admin"' /data/options.json)
ADMIN_PASSWORD=$(jq -r '.admin_password // ""' /data/options.json)
EXTRA_PARAMS=$(jq -r '.extra_params // ""' /data/options.json)

# aliasgroup1 (explicit domain regex) takes priority over nextcloud_url
if [ -n "$ALIASGROUP1" ]; then
    DOMAIN="$ALIASGROUP1"
else
    # Extract hostname/IP from URL and escape dots for Collabora regex
    # e.g. "https://192.168.1.100:7443" -> "192\.168\.1\.100"
    DOMAIN=$(echo "$NEXTCLOUD_URL" | sed -E 's|https?://||; s|/.*||; s|:[0-9]+||; s/\./\\./g')
fi

export domain="$DOMAIN"
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"
export extra_params="${EXTRA_PARAMS:---o:ssl.enable=false --o:net.proto=IPv4}"

# domain1 = Collabora's own public hostname (server_name), needed for reverse proxy
if [ -n "$DOMAIN1" ]; then
    export server_name="$DOMAIN1"
fi

# Persist coolwsd.xml config across container rebuilds
COOL_CONFIG="/etc/coolwsd/coolwsd.xml"
CONFIG_DEST="/config/coolwsd.xml"
mkdir -p /config
if [ ! -e "${CONFIG_DEST}" ]; then
    mv "${COOL_CONFIG}" "${CONFIG_DEST}" 2>/dev/null || true
    chown root:root "${CONFIG_DEST}" 2>/dev/null || true
    chmod 644 "${CONFIG_DEST}"
else
    rm -f "${COOL_CONFIG}"
fi
ln -sf "${CONFIG_DEST}" "${COOL_CONFIG}"

# Update network files in systemplate chroot
SYSTEMPLATE_DIR="/opt/cool/systemplate/etc"
if [ -d "${SYSTEMPLATE_DIR}" ]; then
    cp /etc/hosts "${SYSTEMPLATE_DIR}/hosts"
    cp /etc/hostname "${SYSTEMPLATE_DIR}/hostname" 2>/dev/null || true
    cp /etc/resolv.conf "${SYSTEMPLATE_DIR}/resolv.conf"
fi

# Set correct ownership for cool user (uid 1001)
chown -R 1001 /opt/cool/systemplate 2>/dev/null || true
chown -R 1001 /etc/coolwsd 2>/dev/null || true
chmod -R 755 /opt/cool/systemplate 2>/dev/null || true

echo "[INFO] Starting Collabora Online..."
echo "[INFO] Allowed domain: $DOMAIN"
[ -n "$DOMAIN1" ] && echo "[INFO] Server name: $DOMAIN1"

# Drop from root to cool user (uid 1001) — coolwsd refuses to run as root
exec su -p -s /bin/bash "$(getent passwd 1001 | cut -d: -f1)" -c "/start-collabora-online.sh"
