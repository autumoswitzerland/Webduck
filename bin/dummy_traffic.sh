#!/bin/bash
#
# WebDuck Dummy Traffic Script
#
# Generates dummy REST-API traffic against a running WebDuck server so the
# dashboard traffic monitor has something to display. Sends random SQL
# queries (with occasional short bursts) to the demo project's "webduck"
# database on localhost:8998.
#
# Prerequisite: run ./bin/setup_demo.sh first so the demo project and the
# "webduck" database with its tasks/departments tables exist. The WebDuck
# server must be running on localhost:8998.
#
# Usage:
#   ./bin/dummy_traffic.sh
#
# Stop with Ctrl+C.
#

URL="http://localhost:8998/db/projects/demo/databases/webduck/query"

SQLS=(
  "SELECT * FROM tasks LIMIT 10"
  "SELECT COUNT(*) FROM tasks"
  "SELECT * FROM departments ORDER BY RANDOM() LIMIT 5"
)

send_query() {
    SQL="${SQLS[$RANDOM % ${#SQLS[@]}]}"

    echo "$(date '+%H:%M:%S') -> $SQL"

    curl -s -X POST "$URL" \
        -H "Content-Type: application/json" \
        -d "{\"sql\": \"$SQL\"}" \
        > /dev/null
}

while true; do
    send_query

    # manchmal kurzer Burst: zweite Anfrage nach 0-2 Sekunden
    if (( RANDOM % 3 == 0 )); then
        sleep_time=$((RANDOM % 3))
        sleep "$sleep_time"
        send_query
    fi

    # normale Pause zwischen Bursts: 1-8 Sekunden
    sleep_time=$((RANDOM % 8 + 1))
    sleep "$sleep_time"
done
