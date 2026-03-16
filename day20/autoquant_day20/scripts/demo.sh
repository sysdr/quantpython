#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "→ Running headless memory comparison demo..."
python -c "
import sys
sys.path.insert(0, '.')
import time, random
from src.data_structures.tick_store import NaiveTickStore, NumpyTickStore, Tick

N = 100_000
rng = random.Random(42)
naive = NaiveTickStore()
numpy_store = NumpyTickStore(capacity=N)

t0 = time.perf_counter_ns()
for i in range(N):
    t = Tick('AAPL', 150.0 + rng.gauss(0, 1), rng.randint(100, 5000),
             time.perf_counter_ns(), 149.95, 150.05)
    naive.append(t)
    numpy_store.append(t)
elapsed_ms = (time.perf_counter_ns() - t0) / 1e6

print(f'Ticks: {N:,}')
print(f'Naive est:  {naive.memory_estimate_bytes() / 1e6:.1f} MB')
print(f'NumPy:      {numpy_store.memory_bytes / 1e6:.1f} MB')
print(f'Reduction:  {naive.memory_estimate_bytes() / numpy_store.memory_bytes:.1f}x')
print(f'Elapsed:    {elapsed_ms:.1f} ms')
print(f'VWAP:       \${numpy_store.vwap():.4f}')
"
