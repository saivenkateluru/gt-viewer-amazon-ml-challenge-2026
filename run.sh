#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DATA_DIR="${1:-$SCRIPT_DIR/data}"
PORT="${2:-8000}"
exec python3 "$SCRIPT_DIR/server.py" --data-dir "$DATA_DIR" --port "$PORT"
