#!/bin/sh
# Override jlesage's default 08-clear-tmp-dir.sh.
# In HA containers, /tmp/run/cid is a mounted device and cannot be removed.
# We clean /tmp selectively to avoid a crash loop.
find /tmp -mindepth 1 -maxdepth 1 ! -name 'run' -exec rm -rf {} + 2>/dev/null || true
find /tmp/run -mindepth 1 ! -name 'cid' -delete 2>/dev/null || true
