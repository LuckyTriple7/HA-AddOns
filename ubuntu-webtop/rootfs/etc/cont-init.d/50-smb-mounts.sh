#!/usr/bin/with-contenv bash
# Mountet CIFS/SMB-Shares aus den Add-on-Optionen nach /mnt/<sharename>.
# Konfiguration über networkdisks (kommagetrennt), cifsusername, cifspassword, cifsdomain.

OPTIONS_FILE="/data/options.json"
[ -f "${OPTIONS_FILE}" ] || exit 0

NETWORKDISKS=$(jq -r '.networkdisks // ""' "${OPTIONS_FILE}")
[ -z "${NETWORKDISKS}" ] && exit 0

CIFSUSER=$(jq -r '.cifsusername // ""' "${OPTIONS_FILE}")
CIFSPASS=$(jq -r '.cifspassword // ""' "${OPTIONS_FILE}")
CIFSDOMAIN=$(jq -r '.cifsdomain // ""' "${OPTIONS_FILE}")
PUID=$(jq -r '.PUID // "1000"' "${OPTIONS_FILE}")
PGID=$(jq -r '.PGID // "1000"' "${OPTIONS_FILE}")

# Temporäre Credentials-Datei (wird nach dem Mounten gelöscht)
CRED_FILE=$(mktemp /tmp/cifs-cred.XXXXXX)
chmod 600 "${CRED_FILE}"
printf 'username=%s\npassword=%s\n' "${CIFSUSER}" "${CIFSPASS}" > "${CRED_FILE}"
[ -n "${CIFSDOMAIN}" ] && printf 'domain=%s\n' "${CIFSDOMAIN}" >> "${CRED_FILE}"

mount_share() {
    local share="$1"
    local mountpoint="$2"
    local extra_opts="${3:-}"

    mount -t cifs "${share}" "${mountpoint}" \
        -o "rw,file_mode=0775,dir_mode=0775,credentials=${CRED_FILE},nobrl,uid=${PUID},gid=${PGID},iocharset=utf8${extra_opts}" \
        2>/dev/null
}

IFS=',' read -ra SHARES <<< "${NETWORKDISKS}"
for SHARE in "${SHARES[@]}"; do
    SHARE="${SHARE// /}"
    [ -z "${SHARE}" ] && continue

    # Mount-Punkt: letztes Pfadsegment des Share-Namens, nur alphanumerisch
    SHARENAME="${SHARE##*/}"
    SHARENAME="${SHARENAME//[^a-zA-Z0-9_-]/_}"
    MOUNTPOINT="/mnt/${SHARENAME}"
    mkdir -p "${MOUNTPOINT}"

    if mount_share "${SHARE}" "${MOUNTPOINT}"; then
        echo "[ubuntu-webtop] SMB gemountet: ${SHARE} → ${MOUNTPOINT}"
    elif mount_share "${SHARE}" "${MOUNTPOINT}" ",vers=2.1"; then
        echo "[ubuntu-webtop] SMB gemountet (vers=2.1): ${SHARE} → ${MOUNTPOINT}"
    elif mount_share "${SHARE}" "${MOUNTPOINT}" ",vers=1.0"; then
        echo "[ubuntu-webtop] SMB gemountet (vers=1.0): ${SHARE} → ${MOUNTPOINT}"
    else
        echo "[ubuntu-webtop] FEHLER: SMB-Share konnte nicht gemountet werden: ${SHARE}"
        rmdir "${MOUNTPOINT}" 2>/dev/null || true
    fi
done

rm -f "${CRED_FILE}"
