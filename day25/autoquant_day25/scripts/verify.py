#!/usr/bin/env python3
"""scripts/verify.py — Run full test suite."""
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
    cwd=ROOT
)
sys.exit(result.returncode)
