#!/bin/sh
# PulseAudio mit virtuellem Sink.
# Alles unter /tmp: /config und /run/user/1000 sind beim Start von
# cont-init.d Nr. 15 noch nicht für abc zugänglich.

PULSE_RUNTIME_DIR=/tmp/pulse-runtime
PULSE_CFG=/tmp/pulse-config
PULSE_SOCKET="${PULSE_RUNTIME_DIR}/native"

mkdir -p "${PULSE_RUNTIME_DIR}" "${PULSE_CFG}"
chmod 777 "${PULSE_RUNTIME_DIR}" "${PULSE_CFG}"

cat > "${PULSE_CFG}/default.pa" << 'EOF'
load-module module-null-sink sink_name=auto_null sink_properties=device.description="Webtop Audio"
set-default-sink auto_null
load-module module-native-protocol-unix socket=/tmp/pulse-runtime/native
load-module module-always-sink
EOF

cat > "${PULSE_CFG}/client.conf" << 'EOF'
default-sink = auto_null
autospawn = no
daemon-binary = /bin/true
EOF

su -s /bin/sh abc -c "
    export HOME=/tmp
    export XDG_RUNTIME_DIR=/tmp/pulse-runtime
    nohup pulseaudio \
        --daemonize=yes \
        --exit-idle-time=-1 \
        --file=/tmp/pulse-config/default.pa \
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
