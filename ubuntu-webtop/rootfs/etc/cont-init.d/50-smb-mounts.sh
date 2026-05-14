#!/usr/bin/with-contenv bash
# Mountet CIFS/SMB-Shares aus den Add-on-Optionen nach /mnt/<sharename>.

OPTIONS_FILE="/data/options.json"
[ -f "${OPTIONS_FILE}" ] || exit 0

NETWORKDISKS=$(jq -r '.networkdisks // ""' "${OPTIONS_FILE}")
[ -z "${NETWORKDISKS}" ] && exit 0

CIFSUSER=$(jq -r '.cifsusername // ""' "${OPTIONS_FILE}")
CIFSPASS=$(jq -r '.cifspassword // ""' "${OPTIONS_FILE}")
CIFSDOMAIN=$(jq -r '.cifsdomain // ""' "${OPTIONS_FILE}")
PUID=$(jq -r '.PUID // "1000"' "${OPTIONS_FILE}")
PGID=$(jq -r '.PGID // "1000"' "${OPTIONS_FILE}")

modprobe cifs 2>/dev/null || true

CRED_FILE=$(mktemp /tmp/cifs-cred.XXXXXX)
chmod 600 "${CRED_FILE}"
printf 'username=%s\npassword=%s\n' "${CIFSUSER}" "${CIFSPASS}" > "${CRED_FILE}"
[ -n "${CIFSDOMAIN}" ] && printf 'domain=%s\n' "${CIFSDOMAIN}" >> "${CRED_FILE}"

BASE_OPTS="rw,file_mode=0775,dir_mode=0775,credentials=${CRED_FILE},nobrl,mfsymlinks,uid=${PUID},gid=${PGID},iocharset=utf8"

is_mounted() {
    grep -q " $1 " /proc/mounts 2>/dev/null
}

IFS=',' read -ra SHARES <<< "${NETWORKDISKS}"
for SHARE in "${SHARES[@]}"; do
    SHARE="${SHARE// /}"
    [ -z "${SHARE}" ] && continue

    SHARENAME="${SHARE##*/}"
    SHARENAME="${SHARENAME//[^a-zA-Z0-9_-]/_}"
    MOUNTPOINT="/mnt/${SHARENAME}"
    mkdir -p "${MOUNTPOINT}"

    echo "[ubuntu-webtop] Versuche SMB-Mount: ${SHARE} → ${MOUNTPOINT}"

    MOUNTED=false
    for VERS in "" ",vers=3.0" ",vers=2.1" ",vers=2.0" ",vers=1.0"; do
        for SEC in "" ",sec=ntlmssp" ",sec=ntlmv2"; do
            OPTS="${BASE_OPTS}${VERS}${SEC}"
            ERR=$(mount -t cifs "${SHARE}" "${MOUNTPOINT}" -o "${OPTS}" 2>&1) || true
            if is_mounted "${MOUNTPOINT}"; then
                echo "[ubuntu-webtop] SMB erfolgreich gemountet: ${SHARE} → ${MOUNTPOINT}${VERS}${SEC}"
                MOUNTED=true
                break 2
            else
                echo "[ubuntu-webtop]   Fehler${VERS}${SEC}: ${ERR}"
            fi
        done
    done

    if [ "${MOUNTED}" = false ]; then
        echo "[ubuntu-webtop] FEHLER: SMB-Mount fehlgeschlagen für ${SHARE}"
        rmdir "${MOUNTPOINT}" 2>/dev/null || true
    fi
done

rm -f "${CRED_FILE}"
