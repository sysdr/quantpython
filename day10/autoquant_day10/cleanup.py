#!/usr/bin/env python3
"""cleanup.py — Remove generated data files (preserves source)."""

import shutil
from pathlib import Path

REMOVE = ["data/cache", "data/raw", "__pycache__", "src/__pycache__",
          "tests/__pycache__", ".pytest_cache"]

for path in REMOVE:
    p = Path(path)
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
        print(f"Removed: {path}")

print("Cleanup complete.")
