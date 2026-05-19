#!/bin/sh
# Startet PulseAudio mit virtuellem Sink — kein echtes Audio-Gerät nötig,
# kein hassio_audio. KasmVNC (kclient) und VLC nutzen diesen Socket.

XDG_RUNTIME_DIR=/run/user/1000
PULSE_SOCKET="${XDG_RUNTIME_DIR}/pulse/native"
PULSE_CFG=/config/.config/pulse

mkdir -p "${XDG_RUNTIME_DIR}/pulse" "${PULSE_CFG}"
chown -R abc:abc "${XDG_RUNTIME_DIR}" "${PULSE_CFG}"

# PulseAudio-Konfiguration mit virtuellem Sink (keine Hardware nötig)
cat > "${PULSE_CFG}/default.pa" << 'EOF'
load-module module-null-sink sink_name=webtop sink_properties=device.description="Webtop"
set-default-sink webtop
load-module module-native-protocol-unix
load-module module-always-sink
EOF
chown abc:abc "${PULSE_CFG}/default.pa"

cat > "${PULSE_CFG}/client.conf" << 'EOF'
default-sink = webtop
autospawn = no
EOF
chown abc:abc "${PULSE_CFG}/client.conf"

# PulseAudio als abc-User im Hintergrund starten
su -s /bin/sh abc -c "
    export HOME=/config
    export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR}
    nohup pulseaudio \
        --daemonize=yes \
        --exit-idle-time=-1 \
        --file=${PULSE_CFG}/default.pa \
        --log-target=file:/tmp/pulseaudio.log \
        >/tmp/pulse-start.log 2>&1
"

# Warten bis Socket bereit (max 10s)
i=0
while [ ! -S "${PULSE_SOCKET}" ] && [ $i -lt 10 ]; do
    sleep 1
    i=$((i + 1))
done

if [ -S "${PULSE_SOCKET}" ]; then
    echo "[pulse] PulseAudio bereit: ${PULSE_SOCKET}"
else
    echo "[pulse] FEHLER beim Start — Log:"
    cat /tmp/pulse-start.log 2>/dev/null
    cat /tmp/pulseaudio.log 2>/dev/null
fi
