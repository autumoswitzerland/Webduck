#!/bin/bash
#
# WebDuck - Test Full API
#
# Usage:
#   ./bin/test_full_api.sh
#

set -e

# Project root directory (parent of bin/)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=== WebDuck Full API test ==="
echo "Project directory: $PROJECT_ROOT"
echo ""

# -----------------------------------------------------------------------------
# WARNING
# -----------------------------------------------------------------------------

echo "----------------------------------------------------------------------------"
echo "WARNING: TEST ENVIRONMENT ONLY"
echo "----------------------------------------------------------------------------"
echo ""
echo "This test is intended for test environments only."
echo ""
echo "The data/ directory must be empty before starting the test."
echo ""
echo "The only allowed file is:"
echo "  data/.users.json"
echo ""
echo "It must contain the default test user:"
echo "  Username: admin"
echo "  Password: admin"
echo ""
echo "If the data/ directory contains existing data, back it up first."
echo "The test may overwrite or delete existing data."
echo ""
echo "----------------------------------------------------------------------------"
echo ""

read -r -p "Type 'YES' to continue: " CONFIRMATION

if [ "$CONFIRMATION" != "YES" ]; then
    echo ""
    echo "Test cancelled."
    exit 1
fi

echo ""

# -----------------------------------------------------------------------------
# Check Python
# -----------------------------------------------------------------------------

if ! command -v python >/dev/null 2>&1; then
    echo "ERROR: Python not found"
    exit 1
fi

echo "Python:"
python --version
echo ""

# -----------------------------------------------------------------------------
# Check virtual environment
# -----------------------------------------------------------------------------

if [ ! -d ".venv" ]; then
    echo "ERROR: Virtual environment .venv not found"
    echo "Create it first with:"
    echo ""
    echo "    python -m venv .venv"
    echo ""
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

echo "Virtual environment:"
python --version
echo ""

# -----------------------------------------------------------------------------
# Check test dependencies
# -----------------------------------------------------------------------------

echo "Checking test dependencies..."

if ! python -c "import pytest" >/dev/null 2>&1; then
    echo "pytest is not installed. Installing..."
    python -m pip install pytest
fi

if ! python -c "import pytest_asyncio" >/dev/null 2>&1; then
    echo "pytest-asyncio is not installed. Installing..."
    python -m pip install pytest-asyncio
fi

echo ""
echo "Test dependencies are available."
echo ""

# -----------------------------------------------------------------------------
# Run full API test
# -----------------------------------------------------------------------------

echo "Starting Full API test..."
echo ""

python -m pytest \
    tests/test_full_api.py \
    -s \
    --interactive \
    --server-url http://localhost:8998
