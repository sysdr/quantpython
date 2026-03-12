#!/usr/bin/env bash
set -euo pipefail
echo "=== AutoQuant-Alpha D15: Trade Queues ==="
echo ""
echo "--- Unit Tests ---"
python -m pytest tests/test_trade_queue.py -v
echo ""
echo "--- Stress Test ---"
python -m tests.stress_test
echo ""
echo "--- Live Demo (requires .env) ---"
python scripts/demo.py
