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
ARG ANUBIS_VERSION=v1.27.0
FROM ghcr.io/techarohq/anubis:${ANUBIS_VERSION} AS anubis-bin

FROM alpine:3.20

LABEL org.opencontainers.image.title="Anubis for Home Assistant"
LABEL org.opencontainers.image.description="Anubis proof-of-work bot challenge (techarohq/anubis) as an auth-request backend for NPMplus"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache bash jq tzdata

# ko-build legt das fertige Binary unter /ko-app/<binary-name> ab.
COPY --from=anubis-bin /ko-app/anubis /usr/local/bin/anubis

COPY policy.default.yaml /policy.default.yaml
COPY policy.search-engines.yaml /policy.search-engines.yaml
COPY --chmod=755 run.sh /run.sh

EXPOSE 8923

ENTRYPOINT ["/run.sh"]
