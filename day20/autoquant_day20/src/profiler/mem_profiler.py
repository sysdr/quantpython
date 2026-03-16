"""
mem_profiler.py — tracemalloc-backed memory profiler with GC pause tracking.

Design constraints:
- Profiler callbacks must be registered at startup, NOT in the tick hot path.
- GC pause recording uses a pre-allocated list to avoid triggering more GC.
- snapshots() compares against a baseline so delta allocations are visible.
"""

from __future__ import annotations

import gc
import os
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import List

import psutil


@dataclass(slots=True)
class AllocationStat:
    file:       str
    lineno:     int
    size_bytes: int
    count:      int


@dataclass(slots=True)
class GCPauseRecord:
    generation:  int
    duration_ns: int
    timestamp_ns: int


class MemoryProfiler:
    """
    Wraps tracemalloc and gc.callbacks for production-grade memory attribution.

    Usage:
        profiler = MemoryProfiler()
        profiler.start()
        # ... run engine ...
        stats = profiler.snapshot()
        pauses = profiler.gc_pauses_p99_ns()
        profiler.stop()
    """

    _MAX_PAUSES = 100_000  # Pre-allocated capacity for GC records

    def __init__(self, trace_depth: int = 25) -> None:
        self._trace_depth = trace_depth
        self._process = psutil.Process(os.getpid())
        self._baseline: tracemalloc.Snapshot | None = None
        self._running = False
        self._gc_pauses: list[GCPauseRecord] = []
        self._gc_start_ns: int = 0

    # ── Lifecycle ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        tracemalloc.start(self._trace_depth)
        gc.callbacks.append(self._gc_callback)
        self._baseline = tracemalloc.take_snapshot()
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        try:
            gc.callbacks.remove(self._gc_callback)
        except ValueError:
            pass
        tracemalloc.stop()
        self._running = False

    # ── GC callback (registered once at startup) ──────────────────────────
    def _gc_callback(self, phase: str, info: dict) -> None:
        if phase == "start":
            self._gc_start_ns = time.perf_counter_ns()
        elif phase == "stop":
            if len(self._gc_pauses) < self._MAX_PAUSES:
                self._gc_pauses.append(
                    GCPauseRecord(
                        generation=info.get("generation", -1),
                        duration_ns=time.perf_counter_ns() - self._gc_start_ns,
                        timestamp_ns=time.perf_counter_ns(),
                    )
                )

    # ── Snapshot ─────────────────────────────────────────────────────────
    def snapshot(self, top_n: int = 20) -> list[AllocationStat]:
        """Delta snapshot vs baseline — isolates new allocations."""
        if not self._running or self._baseline is None:
            return []
        current = tracemalloc.take_snapshot()
        stats = current.compare_to(self._baseline, "lineno")
        result: list[AllocationStat] = []
        for s in stats[:top_n]:
            tb = s.traceback[0]
            result.append(
                AllocationStat(
                    file=tb.filename.split(os.sep)[-1],
                    lineno=tb.lineno,
                    size_bytes=s.size,
                    count=s.count,
                )
            )
        return result

    # ── GC metrics ───────────────────────────────────────────────────────
    def gc_pauses_ns(self) -> list[int]:
        return [p.duration_ns for p in self._gc_pauses]

    def gc_count(self) -> int:
        return len(self._gc_pauses)

    # ── RSS ───────────────────────────────────────────────────────────────
    def rss_bytes(self) -> int:
        return self._process.memory_info().rss

    def reset_baseline(self) -> None:
        """Re-anchor baseline snapshot (e.g., after warmup period)."""
        if self._running:
            self._baseline = tracemalloc.take_snapshot()
