#!/bin/bash
#
# WebDuck Demo Setup Script
#
# Creates a demo project with sample databases for screenshots.
# Only affects the data/demo/ directory — other projects are untouched.
# If data/demo/ already exists, it will be overwritten.
#
# Usage:
#   ./bin/setup_demo.sh
#

set -e

# Project root directory (parent of bin/)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=== WebDuck Demo Setup ==="
echo "Project directory: $PROJECT_ROOT"
echo ""

# ── Check dependencies ───────────────────────────────────
if ! command -v duckdb &> /dev/null; then
    echo "❌ Error: duckdb is not installed."
    echo "   Install it: https://duckdb.org/docs/installation/"
    exit 1
fi

# ── Warning if demo project exists ───────────────────────
DEMO_DIR="data/demo"
if [ -d "$DEMO_DIR" ]; then
    echo "⚠️  The demo project already exists at data/demo/"
    echo "   This will OVERWRITE it (other projects are untouched)."
    echo ""
    read -p "Continue? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    rm -rf "$DEMO_DIR"
else
    mkdir -p data
fi

# ── Create demo project ──────────────────────────────────
mkdir -p "$DEMO_DIR"

# ── Create main database ─────────────────────────────────
echo "Creating webduck.duckdb..."
duckdb "$DEMO_DIR/webduck.duckdb" < scripts/demo_setup.sql

# ── Create analytics database ────────────────────────────
echo "Creating analytics.duckdb..."
duckdb "$DEMO_DIR/analytics.duckdb" < scripts/demo_analytics.sql

# ── Update project order (add demo if not present) ───────
PROJECTS_FILE="data/.projects.json"
if [ -f "$PROJECTS_FILE" ]; then
    if ! grep -q '"demo"' "$PROJECTS_FILE"; then
        # Add demo at the beginning (top of list)
        python3 -c "
import json
with open('$PROJECTS_FILE') as f:
    data = json.load(f)
data['projects'] = ['demo'] + [p for p in data['projects'] if p != 'demo']
with open('$PROJECTS_FILE', 'w') as f:
    json.dump(data, f, indent=2)
"
        echo "✓ Added 'demo' to project order"
    else
        echo "✓ 'demo' already in project order"
    fi
else
    echo '{"projects": ["demo"]}' > "$PROJECTS_FILE"
    echo "✓ Created project order"
fi

echo ""
echo "=== Demo setup complete! ==="
echo ""
echo "Databases:"
echo "  data/demo/webduck.duckdb    — Employees, Projects, Tasks, Views, Macros"
echo "  data/demo/analytics.duckdb  — Sales data"
echo ""
echo "Start the server:"
echo "  webduck start"
echo ""
