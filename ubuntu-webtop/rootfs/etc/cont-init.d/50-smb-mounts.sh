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

# cifs-Kernelmodul laden (wird im HA-Container oft nicht automatisch geladen)
modprobe cifs 2>/dev/null && echo "[ubuntu-webtop] cifs-Kernelmodul geladen" \
    || echo "[ubuntu-webtop] cifs-Kernelmodul konnte nicht geladen werden (evtl. bereits aktiv)"

# Temporäre Credentials-Datei
CRED_FILE=$(mktemp /tmp/cifs-cred.XXXXXX)
chmod 600 "${CRED_FILE}"
printf 'username=%s\npassword=%s\n' "${CIFSUSER}" "${CIFSPASS}" > "${CRED_FILE}"
[ -n "${CIFSDOMAIN}" ] && printf 'domain=%s\n' "${CIFSDOMAIN}" >> "${CRED_FILE}"

BASE_OPTS="rw,file_mode=0775,dir_mode=0775,credentials=${CRED_FILE},nobrl,uid=${PUID},gid=${PGID},iocharset=utf8"

try_mount() {
    local share="$1" mountpoint="$2" opts="$3"
    local err
    err=$(mount -t cifs "${share}" "${mountpoint}" -o "${opts}" 2>&1)
    local rc=$?
    [ $rc -ne 0 ] && echo "[ubuntu-webtop]   Fehler (${opts##*,}): ${err}"
    return $rc
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
            if try_mount "${SHARE}" "${MOUNTPOINT}" "${OPTS}"; then
                echo "[ubuntu-webtop] SMB erfolgreich gemountet: ${SHARE} → ${MOUNTPOINT}${VERS}${SEC}"
                MOUNTED=true
                break 2
            fi
        done
    done

    if [ "${MOUNTED}" = false ]; then
        echo "[ubuntu-webtop] FEHLER: Alle Mount-Versuche für ${SHARE} fehlgeschlagen"
        rmdir "${MOUNTPOINT}" 2>/dev/null || true
    fi
done

rm -f "${CRED_FILE}"
