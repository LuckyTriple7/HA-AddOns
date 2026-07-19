# collabora/code >= 26.04.2.2 hat ein Nix-basiertes Rootfs OHNE Shell/apt/su
# (Entrypoint ruft /usr/bin/coolwsd direkt auf, User ist fix nonroot/1001).
# Deshalb hier alle Werkzeuge statisch vorbauen und nur per COPY einbringen —
# RUN funktioniert im finalen Stage nicht mehr (kein /bin/sh vorhanden).
FROM debian:bookworm-slim AS tools

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /out \
    && curl -fL https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64 \
        -o /out/ttyd \
    && curl -fL https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox \
        -o /out/busybox \
    && curl -fL https://github.com/jqlang/jq/releases/latest/download/jq-linux-amd64 \
        -o /out/jq \
    && chmod +x /out/ttyd /out/busybox /out/jq

FROM collabora/code:latest

LABEL org.opencontainers.image.title="Collabora Online for Home Assistant"
LABEL org.opencontainers.image.description="Collabora Online office server for Nextcloud"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

ENV PATH="/usr/local/bin:/usr/bin:/bin"

# busybox ist ein Multi-Call-Binary (wählt Applet über argv[0]/Dateiname) —
# jede benötigte Coreutil braucht deshalb eine eigene Kopie unter ihrem Namen
# (kein Standalone-Shell-Modus vorausgesetzt, keine Symlinks möglich ohne Shell).
COPY --from=tools --chmod=755 /out/busybox /bin/sh
COPY --from=tools --chmod=755 /out/busybox /bin/busybox
COPY --from=tools --chmod=755 /out/busybox /bin/cp
COPY --from=tools --chmod=755 /out/busybox /bin/sed
COPY --from=tools --chmod=755 /out/busybox /bin/date
COPY --from=tools --chmod=755 /out/busybox /bin/kill
COPY --from=tools --chmod=755 /out/busybox /bin/sleep
COPY --from=tools --chmod=755 /out/ttyd /usr/local/bin/ttyd
COPY --from=tools --chmod=755 /out/jq /usr/local/bin/jq

COPY --chmod=755 run.sh /run.sh

ENTRYPOINT ["/bin/sh", "/run.sh"]
