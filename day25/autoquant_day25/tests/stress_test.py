"""
tests/stress_test.py
Stress test: vectorized BSM for 1M contracts must complete < 3 seconds.
"""
import time
import numpy as np
from src.greeks.engine import bsm_greeks_vectorized

N = 1_000_000
print(f"Stress test: computing Greeks for {N:,} option contracts...")

np.random.seed(0)
S     = 500.0
K     = np.random.uniform(400, 600, N)
T     = np.random.uniform(0.01, 2.0, N)
sigma = np.random.uniform(0.05, 0.80, N)
r     = 0.05
is_call = np.random.randint(0, 2, N).astype(bool)

start_ns = time.perf_counter_ns()
delta, gamma = bsm_greeks_vectorized(S, K, r, T, sigma, is_call)
elapsed_ms = (time.perf_counter_ns() - start_ns) / 1e6

print(f"Computed {N:,} contracts in {elapsed_ms:.1f} ms")
print(f"  Mean delta : {delta.mean():.6f}")
print(f"  Mean gamma : {gamma.mean():.8f}")
print(f"  Delta range: [{delta.min():.4f}, {delta.max():.4f}]")

assert elapsed_ms < 3000, f"FAIL: {elapsed_ms:.0f}ms exceeds 3000ms target"
print(f"\n[PASS] Vectorized engine processed {N:,} contracts in {elapsed_ms:.1f}ms < 3000ms")
