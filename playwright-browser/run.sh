#!/usr/bin/with-contenv bashio

CDP_PORT=$(bashio::config 'cdp_port')
INTERNAL_PORT=9223
CONTAINER_HOSTNAME=$(hostname)
TMPDIR=$(mktemp -d)

# Find Chromium binary
CHROMIUM_BIN=""
for candidate in chromium chromium-browser google-chrome-stable google-chrome; do
    if command -v "$candidate" >/dev/null 2>&1; then
        CHROMIUM_BIN="$candidate"
        break
    fi
done

if [ -z "$CHROMIUM_BIN" ]; then
    bashio::log.fatal "No Chromium binary found!"
    exit 1
fi

bashio::log.info "Starting ${CHROMIUM_BIN} on internal port ${INTERNAL_PORT}..."

"$CHROMIUM_BIN" \
    --headless=new \
    --no-sandbox \
    --disable-gpu \
    --disable-dev-shm-usage \
    --disable-setuid-sandbox \
    --no-first-run \
    --no-default-browser-check \
    --disable-background-networking \
    --disable-client-side-phishing-detection \
    --disable-sync \
    --disable-translate \
    --metrics-recording-only \
    --safebrowsing-disable-auto-update \
    --disable-v8-idle-tasks \
    --js-flags="--jitless" \
    --enable-low-end-device-mode \
    --remote-debugging-port=${INTERNAL_PORT} \
    --remote-debugging-address=127.0.0.1 \
    --user-data-dir="${TMPDIR}" \
    >/dev/null 2>&1 &
CHROMIUM_PID=$!

bashio::log.info "Waiting for Chromium to be ready..."
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${INTERNAL_PORT}/json/version" >/dev/null 2>&1; then
        bashio::log.info "Chromium is ready!"
        break
    fi
    sleep 1
    if [ "$i" -eq 30 ]; then
        bashio::log.fatal "Chromium did not start within 30 seconds!"
        exit 1
    fi
done

bashio::log.info "Starting CDP proxy on port ${CDP_PORT}..."
INTERNAL_PORT=${INTERNAL_PORT} \
EXTERNAL_PORT=${CDP_PORT} \
python3 /cdp_proxy.py &
PROXY_PID=$!

sleep 2

if ! kill -0 "${PROXY_PID}" 2>/dev/null; then
    bashio::log.fatal "CDP proxy failed to start!"
    exit 1
fi

if ! curl -sf "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
    bashio::log.fatal "CDP proxy on port ${CDP_PORT} not responding!"
    exit 1
fi

bashio::log.info "CDP endpoint ready: http://${CONTAINER_HOSTNAME}:${CDP_PORT}"

while true; do
    if ! kill -0 "${CHROMIUM_PID}" 2>/dev/null; then
        bashio::log.fatal "Chromium stopped unexpectedly!"
        kill "${PROXY_PID}" 2>/dev/null
        exit 1
    fi
    if ! kill -0 "${PROXY_PID}" 2>/dev/null; then
        bashio::log.fatal "CDP proxy stopped unexpectedly!"
        kill "${CHROMIUM_PID}" 2>/dev/null
        exit 1
    fi
    sleep 30
done
