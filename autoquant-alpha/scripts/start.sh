#!/usr/bin/env bash
set -euo pipefail
echo "→ Building AutoQuant-Alpha Day 1 container..."
docker build -t autoquant-alpha:day1 .
echo "→ Starting container with .env..."
if [ -t 0 ]; then
  docker run --rm -it --env-file .env -v "$(pwd)":/workspace autoquant-alpha:day1 bash
else
  docker run --rm -i --env-file .env -v "$(pwd)":/workspace autoquant-alpha:day1 bash
fi
