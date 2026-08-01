#!/bin/bash
#
# WebDuck - Run all tests, write protocol to text file
#
# Usage:
#   ./bin/all_tests.sh
#
# The test protocol is written to:
#   tests/last_test_protocol.txt
#

set -e

# Project root directory (parent of bin/)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=== WebDuck all tests ==="
echo "Project directory: $PROJECT_ROOT"
echo ""

if [ ! -x ".venv/bin/python" ]; then
    echo "ERROR: Virtual environment .venv not found"
    echo "Create it first with:"
    echo ""
    echo "    python -m venv .venv"
    echo ""
    exit 1
fi

echo "Running pytest (without ANSI colors)..."
echo ""

NO_COLOR=1 .venv/bin/python -m pytest --color=no tests/ > tests/last_test_protocol.txt 2>&1

echo "Done. Protocol written to: tests/last_test_protocol.txt"
