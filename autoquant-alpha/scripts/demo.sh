#!/usr/bin/env bash
set -euo pipefail
RUN_ENV="--env-file .env -e PYTHONPATH=/workspace"
echo "→ Running health check..."
docker run --rm $RUN_ENV autoquant-alpha:day1 python src/health_check.py
echo "→ Launching Rich dashboard (Ctrl+C to exit)..."
if [ -t 0 ]; then
  docker run --rm -it $RUN_ENV autoquant-alpha:day1 python src/dashboard.py
else
  docker run --rm -i $RUN_ENV autoquant-alpha:day1 python src/dashboard.py
fi
