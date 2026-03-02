#!/usr/bin/env python3
"""Remove generated logs and caches. Leaves source intact."""
import shutil
from pathlib import Path

for target in [Path("logs"), Path("logs/stress")]:
    if target.exists():
        shutil.rmtree(target)
        print(f"[REMOVED] {target}")

for p in Path(".").rglob("__pycache__"):
    shutil.rmtree(p)
for p in Path(".").rglob("*.pyc"):
    p.unlink()

print("[DONE] Workspace cleaned.")
