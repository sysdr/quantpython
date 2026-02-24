#!/usr/bin/env python3
"""Launch the Rich CLI dashboard."""
import sys
sys.path.insert(0, ".")
from src.dashboard import run_dashboard

if __name__ == "__main__":
    run_dashboard(duration_seconds=60)
