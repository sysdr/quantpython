#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
cd "$ROOT"

REQUIRED=(
  __init__.py requirements.txt
  src/__init__.py src/margin/__init__.py src/margin/account.py src/margin/monitor.py
  src/broker/__init__.py src/broker/mock_broker.py src/broker/reconciler.py
  src/dashboard/__init__.py src/dashboard/cli.py
  tests/__init__.py tests/test_margin.py tests/stress_test.py
  scripts/demo.py scripts/verify.py scripts/start.py scripts/start.sh scripts/verify.sh scripts/cleanup.sh
  data/.gitkeep
)
missing=0
for f in "${REQUIRED[@]}"; do
  if [[ ! -e "$ROOT/$f" ]]; then
    echo "Missing required file: $f" >&2
    missing=1
  fi
done
if [[ "$missing" -ne 0 ]]; then
  exit 1
fi

echo "AutoQuant Day 45 — verify.sh (workspace: $ROOT)"
python3 scripts/verify.py
