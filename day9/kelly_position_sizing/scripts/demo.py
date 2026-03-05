#!/usr/bin/env python3.11
"""scripts/demo.py — Launch the Rich live dashboard."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dashboard.cli import run_dashboard

if __name__ == "__main__":
    asyncio.run(run_dashboard(nav=100_000.0, refresh_interval=3.0))
