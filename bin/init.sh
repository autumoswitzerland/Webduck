#!/bin/bash
#
# WebDuck Initialization Script
#
# Usage:
#   ./bin/init.sh
#

set -e

# Project root directory (parent of bin/)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PROJECT_ROOT"

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "❌ .venv not found! Please run setup.sh first."
    exit 1
fi

echo "🚀 Initialize WebDuck..."

# Initialize WebDuck
webduck init
