###############################################################################
# NPMplus als Home-Assistant-Add-on.
#
# Das Upstream-Image ist ein selbstgebauter nginx (aws-lc, HTTP/3, Lua) auf
# Alpine — nachbauen dauert Stunden. Es wird deshalb unverändert als Basis
# benutzt; das Add-on legt nur einen eigenen Entrypoint davor, der
# /data/options.json in die Environment-Variablen übersetzt, die NPMplus
# erwartet, und danach an das Original-Init übergibt.
#
# Bewusst ohne RUN-Layer: dadurch ist der Build reines Metadaten-Kopieren und
# läuft für amd64 und aarch64 ohne QEMU-Emulation.
###############################################################################
ARG NPMPLUS_VERSION=2026-07-24-r1
FROM docker.io/zoeyvid/npmplus:${NPMPLUS_VERSION}

LABEL org.opencontainers.image.title="NPMplus for Home Assistant"
LABEL org.opencontainers.image.description="NPMplus reverse proxy (nginx-proxy-manager fork) as a Home Assistant add-on"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="AGPL-3.0-or-later"

COPY --chmod=755 run.sh /run.sh
COPY --chmod=755 selftest.sh /selftest.sh

ENTRYPOINT ["/run.sh"]
