#!/bin/bash
#
# coolwsd starten.
#
# Das offizielle Image lieferte früher /start-collabora-online.sh und benutzte es
# als Entrypoint. Seit dem Umbau auf ein Distroless-Image ist das Skript weg,
# also bringt das Add-on sein eigenes Äquivalent mit. Aufgerufen wird es als
# uid 1001 aus /run.sh; alles kommt aus der Umgebung, damit extra_params nicht
# durch su hindurch neu gequotet werden muss.
set -e

# Collabora liefert https selbst aus, solange nicht bereits echte Zertifikate
# hinterlegt wurden (dann exportiert /run.sh DONT_GEN_SSL_CERT).
cert_params=""
if [ -z "${DONT_GEN_SSL_CERT:-}" ]; then
    SSL_DIR="/tmp/ssl"
    mkdir -p "${SSL_DIR}/certs/ca" "${SSL_DIR}/certs/servers/localhost" "${SSL_DIR}/certs/tmp"

    openssl genrsa -out "${SSL_DIR}/certs/ca/root.key.pem" 2048
    openssl req -x509 -new -nodes \
        -key "${SSL_DIR}/certs/ca/root.key.pem" -days 9131 \
        -out "${SSL_DIR}/certs/ca/root.crt.pem" \
        -subj "/C=DE/ST=BW/L=Stuttgart/O=Dummy Authority/CN=Dummy Authority"

    openssl genrsa -out "${SSL_DIR}/certs/servers/localhost/privkey.pem" 2048
    openssl req -new -sha256 \
        -key "${SSL_DIR}/certs/servers/localhost/privkey.pem" \
        -out "${SSL_DIR}/certs/tmp/localhost.csr.pem" \
        -subj "/C=DE/ST=BW/L=Stuttgart/O=Dummy Authority/CN=${cert_domain:-localhost}"
    openssl x509 -req -days 9131 \
        -in "${SSL_DIR}/certs/tmp/localhost.csr.pem" \
        -CA "${SSL_DIR}/certs/ca/root.crt.pem" \
        -CAkey "${SSL_DIR}/certs/ca/root.key.pem" -CAcreateserial \
        -out "${SSL_DIR}/certs/servers/localhost/cert.pem"

    cert_params="--o:ssl.cert_file_path=${SSL_DIR}/certs/servers/localhost/cert.pem \
        --o:ssl.key_file_path=${SSL_DIR}/certs/servers/localhost/privkey.pem \
        --o:ssl.ca_file_path=${SSL_DIR}/certs/ca/root.crt.pem"
fi

# Die Flags spiegeln den Entrypoint des offiziellen Images. extra_params kommt
# zuletzt, damit Add-on-Optionen und Nutzer-Overrides gewinnen.
# shellcheck disable=SC2086
exec /usr/bin/coolwsd \
    --version \
    --use-env-vars \
    ${cert_params} \
    --o:sys_template_path=/opt/cool/systemplate \
    --o:child_root_path=/opt/cool/child-roots \
    --o:file_server_root_path=/usr/share/coolwsd \
    --o:cache_files.path=/opt/cool/cache \
    --o:logging.color=false \
    --o:stop_on_config_change=true \
    ${extra_params:-}
