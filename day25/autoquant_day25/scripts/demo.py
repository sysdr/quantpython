#!/usr/bin/env python3
"""scripts/demo.py — Launch live Greeks CLI dashboard."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.dashboard.visualizer import run_live_dashboard
print("Launching AutoQuant-Alpha Greeks Dashboard (60s)...")
print("Press Ctrl+C to exit early.\n")
try:
    run_live_dashboard(duration_s=60)
except KeyboardInterrupt:
    print("\nDashboard stopped.")
