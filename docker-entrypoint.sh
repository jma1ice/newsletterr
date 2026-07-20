#!/bin/sh
# Rootless-friendly entrypoint (NEWS-7).
#
# Two supported run styles:
#   1. linuxserver.io convention: start the container as root with PUID/PGID
#      set. We chown the mounted volumes to that uid/gid, then drop privileges
#      with gosu and exec the app as the target user.
#   2. Rootless: start with `--user` (or rely on the image's baked-in non-root
#      USER). We are already unprivileged, so we skip the chown/drop and exec
#      the app as-is. This is the path Podman rootless and hardened Docker use.
set -e

APP_UID="${PUID:-}"
APP_GID="${PGID:-}"

# Runtime dirs that live on volumes; ownership must match the runtime user or
# SQLite writes and uploads fail.
RUNTIME_DIRS="/app/database /app/env /app/static/uploads"

if [ "$(id -u)" = "0" ] && [ -n "$APP_UID" ] && [ -n "$APP_GID" ]; then
    # Reconcile the baked-in `app` account to the requested uid/gid so files
    # created inside match ownership the host expects.
    if [ "$(id -u app 2>/dev/null)" != "$APP_UID" ]; then
        usermod -o -u "$APP_UID" app 2>/dev/null || true
    fi
    if [ "$(getent group app | cut -d: -f3)" != "$APP_GID" ]; then
        groupmod -o -g "$APP_GID" app 2>/dev/null || true
    fi

    for dir in $RUNTIME_DIRS; do
        mkdir -p "$dir"
        chown -R "$APP_UID:$APP_GID" "$dir" 2>/dev/null || true
    done

    echo "Starting newsletterr as uid=$APP_UID gid=$APP_GID (dropped from root)"
    exec gosu "$APP_UID:$APP_GID" "$@"
fi

# Already unprivileged (rootless / --user), or root without PUID: run as-is.
# Best-effort dir creation; a read-only or pre-chowned volume is fine.
for dir in $RUNTIME_DIRS; do
    mkdir -p "$dir" 2>/dev/null || true
done

exec "$@"
