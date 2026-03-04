"""
OnTickInterface: The enforced contract for all tick-driven strategies.

This ABC defines the ONLY public API that the execution engine calls.
Concrete strategies implement this interface and nothing else is exposed
to the outside world. This means:

1. The execution engine is strategy-agnostic.
2. Strategies can be hot-swapped without modifying execution code.
3. on_tick() behaviour is testable in complete isolation.

CRITICAL CONTRACT (enforced by code review, not Python):
─────────────────────────────────────────────────────────
on_tick() MUST:
  ✓ Be a pure computational function.
  ✓ Complete in < 1ms on commodity hardware (verified by stress test).
  ✓ Never raise an exception (catch and return None internally).

on_tick() MUST NOT:
  ✗ Perform any network I/O.
  ✗ Write to disk or database.
  ✗ Call time.sleep() or any blocking operation.
  ✗ Acquire external locks.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
from .types import MarketSnapshot, Signal


class OnTickInterface(ABC):

    @abstractmethod
    def on_tick(self, snapshot: MarketSnapshot) -> Optional[Signal]:
        """
        Process a single market tick. Hot path.

        Args:
            snapshot: Frozen, immutable point-in-time market state.

        Returns:
            Signal if entry/exit conditions are met. None otherwise.
            A None return is the normal case (~95%+ of ticks).
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """
        Clear all internal state.
        Called after a WebSocket reconnection to prevent stale
        indicator values from generating spurious signals.
        """
        ...

    @abstractmethod
    def get_state_snapshot(self) -> dict:
        """
        Return a serializable dict of current strategy state.
        Called by the dashboard at ~10 Hz. Must be thread-safe.
        """
        ...
