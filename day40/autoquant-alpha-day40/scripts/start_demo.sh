#!/usr/bin/env bash
# Start Day 40 demo from any cwd (workspace root = parent of scripts/).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO="$ROOT/scripts/demo.py"
if [ ! -f "$DEMO" ]; then
    echo "[error] missing $DEMO" >&2
    exit 1
fi
cd "$ROOT"
exec python3 "$DEMO" "$@"
