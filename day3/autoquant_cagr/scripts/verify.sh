#!/usr/bin/env bash
set -euo pipefail
SYMBOL=${1:-SPY}
TENOR=${2:-1Y}
python -m src.verify --symbol "$SYMBOL" --tenor "$TENOR"
