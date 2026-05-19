#!/bin/sh
# PulseAudio mit virtuellem Sink — eigener Runtime-Dir unter /tmp um
# den Konflikt mit /run/user/1000 (UID 911, KasmVNC-intern) zu umgehen.

PULSE_RUNTIME_DIR=/tmp/pulse-runtime
PULSE_SOCKET="${PULSE_RUNTIME_DIR}/native"
PULSE_CFG=/config/.config/pulse

mkdir -p "${PULSE_RUNTIME_DIR}" "${PULSE_CFG}"
chown abc:abc "${PULSE_RUNTIME_DIR}" "${PULSE_CFG}"
chmod 700 "${PULSE_RUNTIME_DIR}"

cat > "${PULSE_CFG}/default.pa" << 'EOF'
load-module module-null-sink sink_name=webtop sink_properties=device.description="Webtop"
set-default-sink webtop
load-module module-native-protocol-unix socket=/tmp/pulse-runtime/native
load-module module-always-sink
EOF
chown abc:abc "${PULSE_CFG}/default.pa"

cat > "${PULSE_CFG}/client.conf" << 'EOF'
default-sink = webtop
autospawn = no
daemon-binary = /bin/true
EOF
chown abc:abc "${PULSE_CFG}/client.conf"

su -s /bin/sh abc -c "
    export HOME=/config
    export XDG_RUNTIME_DIR=/tmp/pulse-runtime
    export PULSE_CONFIG_PATH=/config/.config/pulse
    nohup pulseaudio \
        --daemonize=yes \
        --exit-idle-time=-1 \
        --file=/config/.config/pulse/default.pa \
        --log-target=file:/tmp/pulseaudio.log \
        >/tmp/pulse-start.log 2>&1
"

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
