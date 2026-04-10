#!/usr/bin/env python3
"""Remove generated log files."""
import shutil
from pathlib import Path

log_dir = Path(__file__).parents[1] / "data" / "logs"
if log_dir.exists():
    for f in log_dir.glob("*.jsonl"):
        f.unlink()
        print(f"Removed: {f}")
print("Cleanup complete.")
