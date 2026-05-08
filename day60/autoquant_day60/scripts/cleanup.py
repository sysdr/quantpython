#!/usr/bin/env python3.11
"""Remove generated data files."""
import shutil
from pathlib import Path

data_dir = Path("data")
if data_dir.exists():
    for f in data_dir.glob("*.jsonl"):
        f.unlink()
        print(f"Removed {f}")
print("Cleanup complete.")
