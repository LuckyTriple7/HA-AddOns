#!/usr/bin/env bash
# Erzeugt requirements.txt aus requirements.in mit pip-compile, und zwar im
# Base-Image des Add-ons (erste FROM-Zeile im Dockerfile). So passt die
# Auflösung zu Alpine/musl bzw. Debian und zur Python-Version im Image.
#
# Aufruf: lock-python-deps.sh [add-on ...]   (ohne Angabe: alle mit requirements.in)
# Braucht Docker. Läuft im Workflow lock-python-deps.yml.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

mapfile -t ALL < <(git ls-files '*requirements.in' | grep -v '/tests/')
if [ $# -gt 0 ]; then
    FILES=()
    for a in "$@"; do
        for f in "${ALL[@]}"; do [[ "$f" == "$a/"* ]] && FILES+=("$f"); done
    done
else
    FILES=("${ALL[@]}")
fi

PIP_COMPILE="pip-compile --quiet --strip-extras --no-emit-index-url --output-file=requirements.txt requirements.in"

for f in "${FILES[@]}"; do
    dir=$(dirname "$f")
    addon=${dir%%/*}
    image=$(grep -m1 -E '^FROM ' "$addon/Dockerfile" | awk '{print $2}')
    echo "::group::$dir ($image)"
    case "$image" in
        python:*)
            inner="pip install --quiet --root-user-action=ignore pip-tools && $PIP_COMPILE"
            ;;
        debian:*|ubuntu:*)
            inner="apt-get update -qq && apt-get install -y -qq --no-install-recommends python3-venv >/dev/null \
                && python3 -m venv /tmp/v && /tmp/v/bin/pip install --quiet pip-tools \
                && PATH=/tmp/v/bin:\$PATH $PIP_COMPILE"
            ;;
        *)
            echo "::error::$dir: Base-Image $image wird nicht unterstützt"
            exit 1
            ;;
    esac
    docker run --rm -v "$PWD/$dir:/w" -w /w "$image" sh -c "$inner && chown $(id -u):$(id -g) requirements.txt"
    echo "::endgroup::"
done
