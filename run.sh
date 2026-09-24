#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DATA_DIR="${1:-$SCRIPT_DIR/data}"
PORT="${2:-8000}"
DATABASE="$SCRIPT_DIR/.cache/viewer.sqlite3"

if [ -f "$DATABASE" ] && [ -t 0 ]; then
    printf 'An existing index was found. Rebuild it? [y/N] '
    read -r ANSWER
    case "$ANSWER" in
        y|Y|yes|YES|Yes)
            exec python3 "$SCRIPT_DIR/server.py" --data-dir "$DATA_DIR" --port "$PORT" --rebuild
            ;;
    esac
fi

exec python3 "$SCRIPT_DIR/server.py" --data-dir "$DATA_DIR" --port "$PORT"
