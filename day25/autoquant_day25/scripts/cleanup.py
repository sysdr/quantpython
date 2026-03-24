#!/usr/bin/env python3
"""scripts/cleanup.py — Remove generated artifacts."""
import shutil
from pathlib import Path
targets = ["__pycache__", ".pytest_cache", "data/output"]
for t in targets:
    p = Path(t)
    if p.exists():
        shutil.rmtree(p)
        print(f"Removed {p}")
for p in Path(".").rglob("__pycache__"):
    shutil.rmtree(p)
    print(f"Removed {p}")
print("Cleanup complete.")
