# Stage 1: Firefox-Laufzeit-Abhängigkeiten aus sauberem Debian holen.
# jlesage's Debian-Base hat keine GUI-Pakete in seinen Repos — deswegen
# schlägt apt-get install libgtk-3-0 etc. dort fehl.
FROM debian:bookworm-slim AS deps
# firefox-esr installieren damit apt alle transitiven Abhängigkeiten auflöst
# (GTK3, ALSA, dbus, fontconfig, etc.) — Binary wird nicht gebraucht.
RUN apt-get update && apt-get install -y --no-install-recommends \
    firefox-esr \
    locales \
    && locale-gen de_DE.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Hauptimage auf jlesage-Basis (v4.12.1 behebt noVNC isAndroid-Bug)
FROM jlesage/baseimage-gui:debian-12-v4.13.2

ENV APP_NAME="Firefox DE" \
    LANG=C.UTF-8 \
    KEEP_APP_RUNNING=1 \
    DISPLAY_WIDTH=1280 \
    DISPLAY_HEIGHT=720 \
    USER_ID=0 \
    GROUP_ID=0

# Favicon und Web-App-Icons aus dem Add-on-Icon erzeugen; ohne das zeigt der
# Browser-Tab das generische Icon des Basis-Images. Muss VOR dem Kopieren der
# Firefox-Laufzeit-Libs laufen: install_app_icon.sh installiert ImageMagick
# temporär und entfernt es danach wieder, was gemeinsam genutzte Bibliotheken
# aus Stage 1 mit löschen könnte.
COPY icon.png /opt/master_icon.png
RUN install_app_icon.sh /opt/master_icon.png

# Firefox-Laufzeit-Libs, Fonts und Fontconfig-Config aus Stage 1 übernehmen
COPY --from=deps /usr/lib/x86_64-linux-gnu /usr/lib/x86_64-linux-gnu
COPY --from=deps /etc/fonts /etc/fonts
COPY --from=deps /usr/share/fonts /usr/share/fonts
COPY --from=deps /usr/share/fontconfig /usr/share/fontconfig
COPY --from=deps /usr/lib/locale /usr/lib/locale
COPY --from=deps /usr/share/locale /usr/share/locale
RUN ldconfig

# Kleine Utilities aus jlesage's konfigurierten Repos
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    jq \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

ARG FIREFOX_VERSION=140.10.2esr
RUN curl -sL --fail \
    "https://releases.mozilla.org/pub/firefox/releases/${FIREFOX_VERSION}/linux-x86_64/de/firefox-${FIREFOX_VERSION}.tar.xz" \
    -o /tmp/firefox.tar.xz \
    && tar -xJ -C /opt -f /tmp/firefox.tar.xz \
    && ln -sf /opt/firefox/firefox /usr/local/bin/firefox \
    && rm /tmp/firefox.tar.xz


COPY rootfs/ /
RUN chmod +x /startapp.sh \
    /etc/cont-init.d/08-clear-tmp-dir.sh \
    /etc/cont-env.d/DISPLAY_WIDTH \
    /etc/cont-env.d/DISPLAY_HEIGHT \
    /etc/cont-env.d/DARK_MODE \
    /etc/cont-env.d/VNC_PASSWORD \
    /etc/cont-env.d/KEEP_APP_RUNNING \
    /etc/cont-env.d/TZ

# "Sync with Host Clipboard" bei jedem Verbindungsaufbau wieder einschalten.
# Die Web-UI merkt sich die Einstellung in localStorage und schreibt dort ein
# hartes "false", sobald der Browser den Clipboard-Zugriff einmal ablehnt (z. B.
# wenn der Tab beim Sperren des Rechners den Fokus verliert). Nach dem Reload
# blieb die Option deshalb dauerhaft aus. Wir überschreiben den gespeicherten
# Wert beim Start der Oberfläche wieder mit dem Standard "an".
RUN grep -q "UI.initSetting('host_clipboard_sync', true);" /opt/noVNC/app/ui.js \
    && sed -i "s|UI.initSetting('host_clipboard_sync', true);|UI.initSetting('host_clipboard_sync', true); WebUtil.setSetting('host_clipboard_sync', true); UI.updateSetting('host_clipboard_sync');|" /opt/noVNC/app/ui.js \
    && sed -i 's|?v=\([A-Za-z0-9._-]*\)"|?v=\1-hcs1"|g' /opt/noVNC/index.html
