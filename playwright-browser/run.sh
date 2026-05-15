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

# nginx config: proxies CDP port to internal Chromium port
# sub_filter rewrites localhost addresses so external clients can connect via WebSocket
cat > /tmp/nginx-cdp.conf << EOF
worker_processes 1;
error_log stderr;
pid /tmp/nginx-cdp.pid;

events {
    worker_connections 512;
}

http {
    access_log off;

    server {
        listen ${CDP_PORT};
        server_name _;

        location / {
            proxy_pass http://127.0.0.1:${INTERNAL_PORT};
            proxy_http_version 1.1;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host localhost;
            proxy_read_timeout 86400;

            sub_filter_once off;
            sub_filter_types application/json;
            sub_filter 'localhost:${INTERNAL_PORT}' '${CONTAINER_HOSTNAME}:${CDP_PORT}';
            sub_filter '127.0.0.1:${INTERNAL_PORT}' '${CONTAINER_HOSTNAME}:${CDP_PORT}';
        }
    }
}
EOF

bashio::log.info "Starting nginx proxy on port ${CDP_PORT}..."
nginx -c /tmp/nginx-cdp.conf

bashio::log.info "CDP endpoint ready at http://${CONTAINER_HOSTNAME}:${CDP_PORT}"

while true; do
    if ! kill -0 "${CHROMIUM_PID}" 2>/dev/null; then
        bashio::log.fatal "Chromium stopped unexpectedly!"
        nginx -s stop -c /tmp/nginx-cdp.conf 2>/dev/null || true
        exit 1
    fi
    sleep 5
done
