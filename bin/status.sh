#!/bin/bash
#
# WebDuck Status Script
#
# Shows the current status of the WebDuck server.
#
# Usage:
#   ./bin/status.sh
#

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PROJECT_ROOT"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "❌ .venv not found! Please run setup.sh first."
    exit 1
fi

echo "=== WebDuck Status ==="
echo ""

webduck status
