#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
echo "Starting MarginMonitor..."
cd "$PROJECT_ROOT"
python3 "$PROJECT_ROOT/src/margin_monitor.py"
