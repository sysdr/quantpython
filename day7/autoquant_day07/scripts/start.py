#!/usr/bin/env python3
"""Validate environment and initialize log directory."""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"]
missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
if missing:
    print(f"[ERROR] Missing env vars: {missing}")
    print("  Copy .env.example → .env and fill in your Alpaca paper credentials.")
    sys.exit(1)

log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
(log_dir / ".gitkeep").touch()
print(f"[OK] Log directory: {log_dir.resolve()}")
print("[OK] Environment validated. Run: python scripts/demo.py")
