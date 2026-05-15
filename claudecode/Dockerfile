ARG BUILD_FROM
FROM ${BUILD_FROM}

# Labels
LABEL maintainer="Robson Felix"
LABEL org.opencontainers.image.title="Claude Code for Home Assistant"
LABEL org.opencontainers.image.description="Claude Code CLI with web terminal and HA integration"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

# Environment setup
ENV \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TERM=xterm-256color \
    DISABLE_AUTOUPDATER=1

# Install system dependencies (ttyd installed separately as static binary)
RUN apk add --no-cache \
    bash \
    curl \
    git \
    github-cli \
    jq \
    nodejs \
    npm \
    openssh-client \
    libstdc++ \
    ncurses \
    vim \
    nano \
    tmux \
    coreutils \
    findutils \
    grep \
    sed \
    gawk \
    ca-certificates \
    openssl \
    ripgrep \
    p7zip \
    socat \
    docker-cli \
    && update-ca-certificates

# Install ttyd static binary (avoids libwebsockets issues)
ARG BUILD_ARCH
RUN case "${BUILD_ARCH}" in \
        amd64) TTYD_ARCH="x86_64" ;; \
        aarch64) TTYD_ARCH="aarch64" ;; \
        armv7|armhf) TTYD_ARCH="armhf" ;; \
        i386) TTYD_ARCH="i686" ;; \
        *) TTYD_ARCH="x86_64" ;; \
    esac && \
    curl -fsSL "https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.${TTYD_ARCH}" -o /usr/bin/ttyd && \
    chmod +x /usr/bin/ttyd

# Provide a passthrough sudo so Claude Code's postinstall script doesn't fail
# (container runs as root so sudo is unnecessary, but HA's security profile blocks the real binary)
RUN printf '#!/bin/sh\nexec "$@"\n' > /usr/local/bin/sudo && chmod +x /usr/local/bin/sudo

# Install Claude Code via npm
# BUILD_VERSION is passed automatically by HA and busts the Docker cache on every version bump
ARG BUILD_VERSION=dev
RUN echo "Building add-on ${BUILD_VERSION} - installing latest Claude Code..." && \
    npm install -g @anthropic-ai/claude-code@latest --no-fund --no-audit 2>&1 && \
    echo "[INFO] Installed $(claude --version 2>/dev/null)"

# Install hass-mcp for Home Assistant integration and pymodbus for Modbus operations
RUN pip3 install --no-cache-dir --break-system-packages hass-mcp pymodbus pyserial

# Install mbpoll (Modbus command line tool) from source
RUN apk add --no-cache --virtual .build-deps \
    build-base \
    cmake \
    libmodbus-dev \
    && git clone https://github.com/epsilonrt/mbpoll.git /tmp/mbpoll \
    && cd /tmp/mbpoll \
    && mkdir build && cd build \
    && cmake .. \
    && make \
    && make install \
    && cd / \
    && rm -rf /tmp/mbpoll \
    && apk del .build-deps \
    && apk add --no-cache libmodbus

# Pre-cache Playwright MCP server (npx cache avoids /usr/local/bin/mcp conflict with hass-mcp)
ENV NPM_CONFIG_CACHE=/root/.npm
RUN npx @playwright/mcp --version || true

# Install Home Assistant CLI (ha command)
RUN case "${BUILD_ARCH}" in \
        amd64) HA_ARCH="amd64" ;; \
        aarch64) HA_ARCH="aarch64" ;; \
        armv7|armhf) HA_ARCH="armhf" ;; \
        i386) HA_ARCH="i386" ;; \
        *) HA_ARCH="amd64" ;; \
    esac && \
    curl -fsSL "https://github.com/home-assistant/cli/releases/latest/download/ha_${HA_ARCH}" -o /usr/local/bin/ha && \
    chmod +x /usr/local/bin/ha

# Create necessary directories (NOT /root/.claude - will be symlinked at runtime)
RUN mkdir -p \
    /homeassistant \
    /root/.config \
    /root/.local/bin

# Configure tmux with large scrollback buffer and scroll support
RUN cat > /root/.tmux.conf << 'EOF'
set -g history-limit 20000
# Use primary screen (not alternate) so xterm.js owns the scrollback buffer
set -ga terminal-overrides ',xterm*:smcup@:rmcup@'
# Mouse off: browser/xterm.js handles scrolling and copy/paste natively
# This fixes touch scrolling on iPad and standard copy/paste on all devices
set -g mouse off
EOF

# Configure bash with aliases and prompt
RUN cat > /root/.bashrc << 'EOF'
export TERM=xterm-256color
export LANG=C.UTF-8
export COLUMNS=220
export PATH="/homeassistant/.claudecode/npm-global/bin:/root/.local/bin:$PATH"
PS1='\[\033[1;36m\]claude-code\[\033[0m\]:\[\033[1;34m\]\w\[\033[0m\]\$ '

# Function to update MCP token before starting Claude
update_mcp_token() {
  local SETTINGS_FILE=/root/.claude/settings.json
  if [ -f "$SETTINGS_FILE" ] && [ -n "$SUPERVISOR_TOKEN" ]; then
    jq ".mcpServers.homeassistant.env.HASS_TOKEN = \"$SUPERVISOR_TOKEN\"" "$SETTINGS_FILE" > /tmp/settings.tmp 2>/dev/null && mv /tmp/settings.tmp "$SETTINGS_FILE"
  fi
}

# Wrapper: set PTY width before Claude launches so auth URLs render as single lines
# tmux resets PTY width via SIGWINCH on client attach; this re-applies immediately before exec
claude() {
    stty cols 220 2>/dev/null
    command claude "$@"
}

# Aliases
alias ll='ls -la'
alias c='update_mcp_token && claude'
alias cc='update_mcp_token && claude --continue'
alias ha-config='cd /homeassistant'
alias ha-logs='cat /homeassistant/home-assistant.log 2>/dev/null || echo "Log not found"'
alias claude-update='echo "Updating Claude Code..." && npm install -g @anthropic-ai/claude-code@latest --prefix /homeassistant/.claudecode/npm-global --no-fund --no-audit 2>&1; hash -r 2>/dev/null; echo "Done: $(command claude --version 2>/dev/null)"'
EOF

# Create update notification script and wire into .bashrc
RUN echo '[ -f /homeassistant/.claudecode/.update_notice ] && echo -e "\033[1;33m[UPDATE AVAILABLE]\033[0m Claude Code $(cat /homeassistant/.claudecode/.update_notice) available - restart the add-on or run: claude-update"' > /root/.claude-notify.sh
RUN echo 'source /root/.claude-notify.sh' >> /root/.bashrc
# Set PTY width so Node.js apps (like Claude Code) read 220 cols via ioctl, not just the COLUMNS shell var
RUN echo 'stty cols 220 rows 50 2>/dev/null || true' >> /root/.bashrc

# Ensure .bashrc is sourced for login shells too
RUN echo 'source ~/.bashrc' > /root/.profile

# Copy startup script to a path AppArmor allows execution from
COPY run.sh /usr/local/bin/start-addon.sh
RUN chmod +x /usr/local/bin/start-addon.sh

# Set up PATH
ENV PATH="/root/.local/bin:${PATH}"

# Set working directory
WORKDIR /homeassistant

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:7681/ || exit 1

ENTRYPOINT []
CMD ["/usr/local/bin/start-addon.sh"]

