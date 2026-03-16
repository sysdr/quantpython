#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "→ Running unit tests..."
python -m pytest tests/test_tick_store.py tests/test_ring_buffer.py -v
echo ""
echo "→ Running stress test..."
python tests/stress_test.py
