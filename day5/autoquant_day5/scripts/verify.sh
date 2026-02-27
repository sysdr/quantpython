#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
echo "Running unit tests + stress tests..."
cd "$PROJECT_ROOT"
python3 -m pytest "$PROJECT_ROOT/tests/test_margin_fsm.py" -v
python3 "$PROJECT_ROOT/tests/stress_test.py"
echo "All verification checks passed."
