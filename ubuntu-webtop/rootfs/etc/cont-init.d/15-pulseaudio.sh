#!/bin/sh
# Das Base-Image startet PulseAudio über svc-pulseaudio (s6-managed, als abc).
# abc's HOME=/config → Daemon liest /config/.config/pulse/default.pa.
# Wir schreiben nur die korrekte Konfiguration; den Start übernimmt s6.

PULSE_CFG=/config/.config/pulse

mkdir -p "${PULSE_CFG}"
chown abc:abc "${PULSE_CFG}" 2>/dev/null || true

cat > "${PULSE_CFG}/default.pa" << 'EOF'
load-module module-null-sink sink_name=auto_null sink_properties=device.description="Webtop Audio"
set-default-sink auto_null
load-module module-native-protocol-unix socket=/tmp/pulse-runtime/native auth-anonymous=1
load-module module-always-sink
EOF
chown abc:abc "${PULSE_CFG}/default.pa"

cat > "${PULSE_CFG}/client.conf" << 'EOF'
default-sink = auto_null
autospawn = no
daemon-binary = /bin/true
EOF
chown abc:abc "${PULSE_CFG}/client.conf"

# Socket-Verzeichnis erstellen (PulseAudio schreibt den Socket nach Start dort rein)
mkdir -p /tmp/pulse-runtime
chmod 777 /tmp/pulse-runtime

echo "[pulse] Konfiguration geschrieben: ${PULSE_CFG}/default.pa (Sink: auto_null)"
