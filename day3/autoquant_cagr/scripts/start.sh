#!/usr/bin/env bash
set -euo pipefail
echo "==> Installing dependencies"
pip install -r requirements.txt
echo "==> Copying .env.example to .env (if not exists)"
[ -f .env ] || cp .env.example .env
echo "==> Done. Edit .env with your Alpaca credentials, then run:"
echo "    python -m src.demo"
