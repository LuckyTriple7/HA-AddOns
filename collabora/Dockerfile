###############################################################################
# 1) Upstream-Image nur noch als Payload-Quelle, nicht mehr als Base.
#
# collabora/code ist seit 26.04.2.2 (2026-07-18) ein Nix-basiertes Distroless-
# Image: /bin und /sbin sind leer, es gibt weder Shell noch apt noch su. Als
# Base des Add-ons ist es damit unbrauchbar. Statt darauf zu bauen wird hier
# nur die Collabora-Nutzlast herauskopiert und auf ein Debian-Runtime gelegt.
#
# Bewusst der arch-spezifische Tag (latest-amd64) statt des Multi-Arch-Tags:
# der Build läuft ohne --platform auf einem amd64-Runner, mit dem Multi-Arch-
# Tag entschiede allein die Runner-Architektur, welche Binaries im Image
# landen. Bei einem Mismatch wäre das Image still voller Fremd-Arch-Binaries.
###############################################################################
FROM collabora/code:latest-amd64 AS collabora

###############################################################################
# 2) Laufzeit-Image: Debian 13 (trixie), gleiche Basis wie hassio-addons/
#    debian-base:9.3.0.
###############################################################################
FROM debian:13-slim

LABEL org.opencontainers.image.title="Collabora Online for Home Assistant"
LABEL org.opencontainers.image.description="Collabora Online office server for Nextcloud"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8

# coolwsd selbst braucht nur glibc/libstdc++; die Office-Engine bringt cairo,
# fontconfig, curl, icu und Fonts unter /opt/collaboraoffice/program selbst mit.
# openssl erzeugt das Self-Signed-Zertifikat, cpio/findutils braucht das
# Jail-Setup, libcap2-bin liefert setcap/getcap, jq liest /data/options.json.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        cpio \
        curl \
        findutils \
        fontconfig \
        jq \
        libcap2-bin \
        libstdc++6 \
        openssl \
        passwd \
        tzdata \
        util-linux \
    && rm -rf /var/lib/apt/lists/*

# ttyd für Web-Terminal (Ingress)
RUN curl -L https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64 \
    -o /usr/local/bin/ttyd && chmod +x /usr/local/bin/ttyd

###############################################################################
# 3) Collabora-Nutzlast aus dem offiziellen Image übernehmen.
#
# Nur das, was zu Collabora gehört. /etc und /nix bewusst NICHT: dort sind
# resolv.conf, hosts, passwd, group und nsswitch.conf Symlinks in den Nix-Store
# — mitkopiert killt das die DNS-Auflösung und löscht die Base-User.
###############################################################################
COPY --from=collabora /usr/bin/coolwsd /usr/bin/coolforkit-caps /usr/bin/coolforkit-ns /usr/bin/coolmount /usr/bin/
COPY --from=collabora /usr/share/coolwsd /usr/share/coolwsd
COPY --from=collabora /etc/coolwsd /etc/coolwsd
COPY --from=collabora /opt/collaboraoffice /opt/collaboraoffice
COPY --from=collabora /opt/cool /opt/cool

# Runtime-User (uid/gid 1001) und Container-State nachbauen, die das offizielle
# Image in seiner eigenen finalen Stage anlegt.
RUN groupadd --gid 1001 cool \
    && useradd --uid 1001 --gid 1001 --no-create-home --home-dir /opt/cool --shell /usr/sbin/nologin cool \
    && mkdir -p /opt/cool/child-roots /opt/cool/cache \
    && chown -R 1001:1001 /opt/cool /etc/coolwsd \
    && chmod 640 /etc/coolwsd/coolwsd.xml \
    # Unberührte Referenz-Config aufheben: run.sh erkennt daran, ob das Image
    # eine neue coolwsd.xml mitbringt, und rotiert dann die nach /config
    # persistierte Kopie, statt eine veraltete Config weiterzubenutzen.
    && cp /etc/coolwsd/coolwsd.xml /etc/coolwsd/coolwsd.xml.dist \
    && touch /var/log/coolwsd.log \
    && chown 1001:1001 /var/log/coolwsd.log \
    # WOPI-Proof-Key muss pro Container einzigartig sein, nicht im Image liegen
    && rm -rf /etc/coolwsd/proof_key* \
    && (fc-cache /opt/collaboraoffice/share/fonts/truetype > /dev/null 2>&1 || true)

###############################################################################
# 4) File-Capabilities wiederherstellen.
#
# Das offizielle Image trägt sie als Extended Attributes auf zwei Binaries:
#   coolforkit-caps  cap_chown,cap_fowner,cap_sys_chroot=ep
#   coolmount        cap_sys_admin=ep
# COPY --from überträgt keine xattrs, beide kommen also entschärft an. Das
# fällt beim Build nicht auf: coolwsd startet und liefert die Admin-Konsole,
# aber JEDES Dokument scheitert, weil kein Kit-Prozess chrooten kann
# ("type detection failed"). Also neu setzen und verifizieren — ein Builder
# ohne xattr-Support soll hier failen statt ein scheinbar heiles Image zu
# veröffentlichen.
#
# cap_sys_admin auf coolmount greift nur mit SYS_ADMIN im Container; HA-Add-ons
# bekommen das nicht. Ohne kopiert Collabora seine Child-Roots statt sie zu
# bind-mounten — langsamer, funktioniert aber.
###############################################################################
RUN setcap "cap_chown,cap_fowner,cap_sys_chroot=ep" /usr/bin/coolforkit-caps \
    && setcap "cap_sys_admin=ep" /usr/bin/coolmount \
    && caps="$(getcap /usr/bin/coolforkit-caps /usr/bin/coolmount)" \
    && case "$caps" in \
       *cap_sys_chroot*) ;; \
       *) echo "coolforkit-caps hat seine Capabilities verloren: ${caps}"; exit 1 ;; \
       esac \
    && case "$caps" in \
       *cap_sys_admin*) ;; \
       *) echo "coolmount hat seine Capabilities verloren: ${caps}"; exit 1 ;; \
       esac

###############################################################################
# 5) Build failen lassen statt ein Image mit unaufgelösten Abhängigkeiten
#    auszuliefern. Die Nutzlast wurde gegen die Libs des Distroless-Images
#    gelinkt, also jede Binary gegen das Debian-Runtime prüfen.
#
# coolwsd selbst lässt sich nicht als Smoke-Test starten: es verweigert den
# Root-Betrieb (exit 78) und --version beendet sich nicht, weil das an den
# langlaufenden Server durchgereicht wird. Der Linkage-Check beweist dasselbe
# und terminiert.
###############################################################################
RUN for binary in \
        /usr/bin/coolwsd \
        /usr/bin/coolforkit-caps \
        /usr/bin/coolforkit-ns \
        /usr/bin/coolmount \
        /opt/collaboraoffice/program/soffice.bin \
        /opt/collaboraoffice/program/libmergedlo.so; do \
        libs="$(ldd "$binary" 2>&1)"; \
        case "$libs" in \
        *"not found"*) echo "Unaufgelöste Libraries in ${binary}:"; echo "$libs"; exit 1 ;; \
        esac; \
    done \
    && command -v openssl > /dev/null \
    && command -v su > /dev/null

###############################################################################
# 6) Entrypoint
###############################################################################
COPY run.sh /run.sh
COPY collabora-run.sh /usr/local/bin/collabora-run.sh
RUN chmod +x /run.sh /usr/local/bin/collabora-run.sh

EXPOSE 9980 7682

ENTRYPOINT ["/run.sh"]
