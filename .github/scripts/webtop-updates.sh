#!/usr/bin/env bash
# Prüft die Webtop-Pakete auf neue Versionen und trägt sie ins Add-on ein.
#
# Liegt bewusst als Skript im Repo und nicht in der Workflow-Datei: zeitgesteuerte
# Läufe nehmen die Workflow-Datei von main, ausgecheckt wird aber dev. Das Skript
# kommt aus dem dev-Checkout, Abfragelogik und Dockerfile passen so immer zusammen.
set -eu

DOCKERFILE=ubuntu-webtop/Dockerfile
CONFIG=ubuntu-webtop/config.yaml
CHANGELOG=ubuntu-webtop/CHANGELOG.md
OUT="${GITHUB_OUTPUT:-/dev/stdout}"
CHANGES=""

AUTH=()
if [ -n "${GH_TOKEN:-}" ]; then AUTH=(-H "Authorization: Bearer ${GH_TOKEN}"); fi

gh_latest() {
  curl -s "${AUTH[@]}" "https://api.github.com/repos/$1/releases/latest" | jq -r '.tag_name' | sed 's/^v//'
}

require() { # Name, Version
  if [ -z "$2" ] || [ "$2" = "null" ]; then
    echo "::error::Konnte Version für $1 nicht ermitteln — API-Fehler oder Rate-Limit?"
    exit 1
  fi
  if ! printf '%s' "$2" | grep -Eq '^[0-9][0-9A-Za-z.+_-]*$'; then
    echo "::error::Unerwartete Versionsangabe für $1: $2"
    exit 1
  fi
}

consider() { # Name, Schlüssel der Tracking-Datei, Dockerfile-ARG (leer = keins), neueste Version
  local name="$1" file=".webtop-$2-version" arg="$3" latest="$4" tracked
  require "$name" "$latest"
  tracked=$(tr -d '\r' < "$file" 2>/dev/null || echo unknown)
  echo "${name}: ${tracked} → ${latest}"
  if [ "$latest" = "$tracked" ]; then return 0; fi
  # Nie zurückstufen: eine ältere Version heißt, dass die Quelle nicht mehr stimmt
  if [ "$tracked" != unknown ] && [ "$(printf '%s\n%s\n' "$latest" "$tracked" | sort -V | tail -n1)" = "$tracked" ]; then
    echo "::warning::${name}: ${latest} ist älter als ${tracked} — übersprungen, Versionsquelle prüfen."
    return 0
  fi
  if [ -n "$arg" ]; then
    sed -i "s/^ARG ${arg}=.*/ARG ${arg}=${latest}/" "$DOCKERFILE"
    if ! grep -qxF "ARG ${arg}=${latest}" "$DOCKERFILE"; then
      echo "::error::ARG ${arg} fehlt im Dockerfile"
      exit 1
    fi
  fi
  echo "$latest" > "$file"
  CHANGES="${CHANGES}- ${name}: ${tracked} → ${latest}"$'\n'
}

BW=$(curl -s "${AUTH[@]}" "https://api.github.com/repos/bitwarden/clients/releases" \
  | jq -r '[.[] | select(.tag_name | startswith("desktop-v")) | select(.prerelease==false)][0].tag_name' \
  | sed 's/desktop-v//')
FIREFOX=$(curl -s "https://product-details.mozilla.org/1.0/firefox_versions.json" | jq -r '.LATEST_FIREFOX_VERSION')
THUNDERBIRD=$(curl -s "https://product-details.mozilla.org/1.0/thunderbird_versions.json" | jq -r '.LATEST_THUNDERBIRD_VERSION')
TAILSCALE=$(curl -s "https://pkgs.tailscale.com/stable/?mode=json" | jq -r '.TarballsVersion')

# OpenCode 2: die GitHub-Releases führen nur Version 1, maßgeblich ist das npm-Paket.
# Die Downloads auf opencode.ai können nachhinken — erst übernehmen, wenn alle da sind.
OPENCODE=$(curl -s "https://registry.npmjs.org/@opencode/cli/latest" | jq -r '.version')
require "OpenCode" "$OPENCODE"
for f in opencode-linux-x64.tar.gz opencode-linux-arm64.tar.gz \
         opencode-desktop-linux-amd64.deb opencode-desktop-linux-arm64.deb; do
  if ! curl -fsIL -o /dev/null "https://opencode.ai/files/bin/${OPENCODE}/${f}"; then
    echo "::warning::OpenCode ${OPENCODE}: ${f} fehlt auf opencode.ai — übersprungen."
    OPENCODE=$(tr -d '\r' < .webtop-opencode-version)
    break
  fi
done

consider "Bitwarden"        bitwarden      BITWARDEN_VERSION   "$BW"
consider "Angry IP Scanner" ipscan         IPSCAN_VERSION      "$(gh_latest angryip/ipscan)"
consider "VS Code"          vscode         VSCODE_VERSION      "$(gh_latest microsoft/vscode)"
consider "GitHub CLI"       ghcli          GH_CLI_VERSION      "$(gh_latest cli/cli)"
consider "Firefox"          firefox        FIREFOX_VERSION     "$FIREFOX"
consider "Thunderbird"      thunderbird    THUNDERBIRD_VERSION "$THUNDERBIRD"
consider "rclone"           rclone         RCLONE_VERSION      "$(gh_latest rclone/rclone)"
# Claude Desktop kommt aus dem apt-Repo, die Tracking-Datei löst nur den Neuaufbau aus
consider "Claude Desktop"   claude-desktop ""                  "$(gh_latest aaddrick/claude-desktop-debian)"
consider "OpenCode"         opencode       OPENCODE_VERSION    "$OPENCODE"
consider "Tailscale"        tailscale      TAILSCALE_VERSION   "$TAILSCALE"

if [ -z "$CHANGES" ]; then
  echo "Alle Webtop-Pakete aktuell — nichts zu tun."
  echo "changed=false" >> "$OUT"
  exit 0
fi

# Add-on Version bumpen
ADDON_VER=$(grep '^version:' "$CONFIG" | tr -d '\r' | sed 's/version: *"\(.*\)"/\1/')
NEW_ADDON_VER="$(echo "$ADDON_VER" | cut -d. -f1-2).$(( $(echo "$ADDON_VER" | cut -d. -f3) + 1 ))"
sed -i "s/^version: \"${ADDON_VER}\"/version: \"${NEW_ADDON_VER}\"/" "$CONFIG"

DATE=$(date +%Y-%m-%d)
{
  printf '## [%s] - %s\n\n### Aktualisiert\n\n%s\n' "$NEW_ADDON_VER" "$DATE" "$CHANGES"
  cat "$CHANGELOG"
} > "${CHANGELOG}.new"
mv "${CHANGELOG}.new" "$CHANGELOG"

{
  echo "changed=true"
  echo "new_version=${NEW_ADDON_VER}"
  echo "date=${DATE}"
  echo "changes<<WEBTOP_EOF"
  printf '%s' "$CHANGES"
  echo "WEBTOP_EOF"
} >> "$OUT"
