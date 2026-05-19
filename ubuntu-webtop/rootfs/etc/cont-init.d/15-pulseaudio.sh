#!/bin/sh
# Startet eine eigene PulseAudio-Instanz mit virtuellem Sink.
# audio: false verhindert die Nutzung von hassio_audio —
# diese Instanz läuft komplett intern und belastet den Host nicht.

XDG_RUNTIME_DIR=/run/user/1000
PULSE_SOCKET="${XDG_RUNTIME_DIR}/pulse/native"

mkdir -p "${XDG_RUNTIME_DIR}/pulse"
chown -R abc:abc "${XDG_RUNTIME_DIR}"

# Bereits laufende Instanz überspringen
if [ -S "${PULSE_SOCKET}" ]; then
    echo "[pulse] PulseAudio läuft bereits"
    exit 0
fi

su -s /bin/sh abc -c "
    export HOME=/config
    export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR}
    pulseaudio \
        --start \
        --load='module-null-sink sink_name=webtop sink_properties=device.description=Webtop' \
        --load='module-native-protocol-unix auth-anonymous=1 socket=${PULSE_SOCKET}' \
        --exit-idle-time=-1 \
        --log-target=newfile:/tmp/pulseaudio.log \
        2>/dev/null || true
"

# Kurz warten bis Socket bereit ist
i=0
while [ ! -S "${PULSE_SOCKET}" ] && [ $i -lt 10 ]; do
    sleep 1
    i=$((i + 1))
done

if [ -S "${PULSE_SOCKET}" ]; then
    echo "[pulse] PulseAudio gestartet: ${PULSE_SOCKET}"
else
    echo "[pulse] WARNUNG: PulseAudio-Socket nicht gefunden nach 10s"
fi
