#!/bin/sh
set -e

DATA_DIR="${WEBDUCK_DATA_DIR:-/data}"
USERS_FILE="$DATA_DIR/.users.json"

# Auto-initialize if no admin users exist
if [ ! -f "$USERS_FILE" ] || [ ! -s "$USERS_FILE" ]; then
    echo "No admin users found — running webduck init..."
    ADMIN_USER="${WEBDUCK_ADMIN_USER:-admin}"
    ADMIN_PASS="${WEBDUCK_ADMIN_PASS:-}"
    if [ -z "$ADMIN_PASS" ]; then
        echo "Error: Set WEBDUCK_ADMIN_PASS environment variable"
        exit 1
    fi
    webduck init --username "$ADMIN_USER" --password "$ADMIN_PASS"
fi

exec "$@"
