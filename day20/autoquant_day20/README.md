# AutoQuant-Alpha | Day 20: Memory Profiling

## Quick Start

```bash
pip install -r requirements.txt
bash scripts/start.sh    # Live Rich dashboard
bash scripts/demo.sh     # Headless comparison
bash scripts/verify.sh   # Tests + stress test
bash scripts/cleanup.sh  # Teardown
```

## Architecture

```
src/
  data_structures/
    tick_store.py     NaiveTickStore, NumpyTickStore, Tick
    ring_buffer.py    Float32RingBuffer (array.array + memoryview)
  profiler/
    mem_profiler.py   tracemalloc wrapper + GC pause tracking
  dashboard/
    cli.py            Rich live dashboard
tests/
  test_tick_store.py  Financial math unit tests
  test_ring_buffer.py Ring buffer correctness
  stress_test.py      Production stress test (p99 latency + memory budget)
```

## Pass Criterion

`bash scripts/verify.sh` must output:
```
✓ ALL CHECKS PASSED — Day 20 criteria met
```
