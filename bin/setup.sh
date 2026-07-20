#!/bin/bash
#
# WebDuck Setup Script
#
# Creates a fresh Python virtual environment and installs
# the WebDuck project with all dependencies defined in pyproject.toml.
#
# Usage:
#   ./bin/setup.sh
#
# After setup (run from project root):
#   source .venv/bin/activate
#   webduck init
#   webduck start
#

set -e

# Project root directory (parent of bin/)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=== WebDuck Setup ==="
echo "Project directory: $PROJECT_ROOT"

# Check Python
if ! command -v python >/dev/null 2>&1; then
    echo "ERROR: Python not found"
    exit 1
fi

echo "Python:"
python --version

# Remove existing virtual environment
if [ -d ".venv" ]; then
    echo "Removing existing virtual environment..."
    rm -rf .venv
fi

# Create virtual environment
echo "Creating virtual environment..."
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Upgrade packaging tools
echo "Updating pip..."
python -m pip install --upgrade pip setuptools wheel

# Install project and dependencies
echo "Installing WebDuck..."
pip install -e .

echo
echo "=== Setup complete ==="
echo
echo "Project directory:"
echo "  cd $PROJECT_ROOT"
echo
echo "Activate environment:"
echo "  source .venv/bin/activate"
echo
echo "Initialize:"
echo "  webduck init"
echo
echo "Start:"
echo "  webduck start"
echo
