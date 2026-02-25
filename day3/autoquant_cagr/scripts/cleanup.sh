#!/usr/bin/env bash
set -euo pipefail
rm -rf logs/ __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache
echo "==> Cleaned build artifacts and logs"
