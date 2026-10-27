###############################################################################
# Anubis als Home-Assistant-Add-on.
#
# Das Original-Image (ghcr.io/techarohq/anubis) basiert auf
# cgr.dev/chainguard/static: keine Shell, kein Paketmanager, nur das statische
# Go-Binary. Für die Übersetzung von /data/options.json in die
# Environment-Variablen von Anubis braucht es aber eine Shell + jq — deshalb
# wird hier nur das Binary aus dem Original-Image kopiert und auf ein
# schlankes Alpine gesetzt, das run.sh als eigenen Entrypoint ausführt.
###############################################################################
# renovate: datasource=docker depName=ghcr.io/techarohq/anubis
ARG ANUBIS_VERSION=v1.28.1
FROM ghcr.io/techarohq/anubis:${ANUBIS_VERSION} AS anubis-bin

FROM alpine:3.24

LABEL org.opencontainers.image.title="Anubis for Home Assistant"
LABEL org.opencontainers.image.description="Anubis proof-of-work bot challenge (techarohq/anubis) as an auth-request backend for NPMplus"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache \
    bash=5.3.9-r1 \
    jq=1.8.2-r0 \
    tzdata=2026e-r0

# ko-build legt das fertige Binary unter /ko-app/<binary-name> ab.
COPY --from=anubis-bin /ko-app/anubis /usr/local/bin/anubis

COPY policy.default.yaml /policy.default.yaml
COPY policy.search-engines.yaml /policy.search-engines.yaml
COPY policy.monitoring.yaml /policy.monitoring.yaml
COPY policy.ai-aggressive.yaml /policy.ai-aggressive.yaml
COPY policy.ai-moderate.yaml /policy.ai-moderate.yaml
COPY policy.ai-permissive.yaml /policy.ai-permissive.yaml
COPY --chmod=755 run.sh /run.sh

EXPOSE 8923

ENTRYPOINT ["/run.sh"]
