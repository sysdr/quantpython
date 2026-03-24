#!/usr/bin/env python3
"""scripts/stress_test.py — Run vectorized engine benchmark."""
import sys
from pathlib import Path
import runpy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
runpy.run_path(str(ROOT / "tests" / "stress_test.py"), run_name="__main__")
