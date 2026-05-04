#!/usr/bin/env bash
# Day 55 — run live dashboard demo from project root (PYTHONPATH set).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
cd "$ROOT"
exec python3 scripts/demo.py "$@"
