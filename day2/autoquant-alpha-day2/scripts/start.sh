#!/usr/bin/env bash
set -e
echo "[start] Installing dependencies..."
pip install -r requirements.txt -q
echo "[start] Running tests..."
python -m pytest tests/test_bond_math.py -v
echo "[start] Launching dashboard..."
python scripts/demo.py
