#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
echo "Starting Rich Dashboard (polling mode)..."
cd "$PROJECT_ROOT"
python3 "$PROJECT_ROOT/src/dashboard.py"
