#!/usr/bin/env python3
"""
Stress test: Simulate equity crashing through all FSM thresholds.
Verifies alert ordering, hysteresis, and rate limiting under load.
"""

from __future__ import annotations

import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from decimal import Decimal
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich import box

from margin_monitor import (
    AlertLevel,
    AccountSnapshot,
    MarginFSM,
    MarginAlert,
    AlertDispatcher,
    EquityCalculator,
    LEVEL_ORDER,
)

console = Console()


def make_snapshot(equity: float, last_equity: float = 100_000.0) -> AccountSnapshot:
    return AccountSnapshot(
        equity             = Decimal(str(equity)),
        last_equity        = Decimal(str(last_equity)),
        buying_power       = Decimal(str(equity * 2)),
        maintenance_margin = Decimal(str(equity * 0.25)),
        initial_margin     = Decimal(str(equity * 0.50)),
        portfolio_value    = Decimal(str(equity * 4)),
    )


def run_crash_scenario() -> None:
    console.rule("[bold red]Stress Test: Equity Crash Scenario[/bold red]")
    fsm        = MarginFSM()
    dispatcher = AlertDispatcher()
    calc       = EquityCalculator()

    # Force rate limiter to allow immediate firing
    fsm._alert_rate_limit_seconds = 0.0

    # Simulate equity cascading downward
    equity_levels = [
        100_000, 93_000, 88_000, 84_000,
        78_000, 74_000, 67_000, 61_000, 55_000
    ]

    results = []
    for equity in equity_levels:
        snap  = make_snapshot(equity)
        ratio = calc.compute_equity_ratio(snap.equity, snap.last_equity)
        new_state = fsm.update(ratio)
        if new_state and fsm.should_fire(new_state):
            alert = MarginAlert(level=new_state, ratio=ratio, snapshot=snap)
            dispatcher.dispatch(alert)
        results.append((equity, ratio, fsm.state.name, new_state.name if new_state else "—"))

    t = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    t.add_column("Equity",    justify="right")
    t.add_column("Ratio",     justify="right")
    t.add_column("FSM State", justify="center")
    t.add_column("Transition")

    for equity, ratio, state, trans in results:
        style = "green" if state == "SAFE" else "yellow" if state == "WARN" else "red"
        t.add_row(f"${equity:,.0f}", f"{ratio:.4f}", f"[{style}]{state}[/{style}]", trans)

    console.print(t)
    console.print(f"\n[bold]Total alerts fired:[/bold] {len(dispatcher.history)}")

    # Verify order is sane
    fired_levels = [a.level for a in dispatcher.history]
    expected = [AlertLevel.WARN, AlertLevel.CRITICAL, AlertLevel.MARGIN_CALL, AlertLevel.LIQUIDATION]
    assert fired_levels == expected, f"Expected {expected}, got {fired_levels}"
    console.print("[bold green]✅ Alert ordering verified[/bold green]")


def run_recovery_scenario() -> None:
    console.rule("[bold green]Stress Test: Recovery with Hysteresis[/bold green]")
    fsm  = MarginFSM()
    calc = EquityCalculator()
    fsm._alert_rate_limit_seconds = 0.0

    # Drop into WARN
    fsm.update(0.88)
    assert fsm.state == AlertLevel.WARN

    # Try to recover with ratio BELOW exit threshold (0.92)
    result = fsm.update(0.91)
    assert result is None, "Should NOT transition: below exit threshold"
    assert fsm.state == AlertLevel.WARN, "Must stay in WARN"

    # Now actually recover above exit threshold
    result = fsm.update(0.93)
    assert result == AlertLevel.SAFE
    assert fsm.state == AlertLevel.SAFE

    console.print("[bold green]✅ Hysteresis recovery verified[/bold green]")


def run_rate_limit_scenario() -> None:
    console.rule("[bold yellow]Stress Test: Alert Rate Limiting[/bold yellow]")
    fsm        = MarginFSM()
    dispatcher = AlertDispatcher()
    # Default 60s rate limit
    fsm._alert_rate_limit_seconds = 60.0

    # Trigger WARN
    fsm.update(0.88)
    if fsm.should_fire(AlertLevel.WARN):
        dispatcher.dispatch(MarginAlert(
            level=AlertLevel.WARN, ratio=0.88,
            snapshot=make_snapshot(88_000)
        ))

    # Immediately try to fire again — should be suppressed
    fired = fsm.should_fire(AlertLevel.WARN)
    assert not fired, "Second fire within 60s should be suppressed"

    assert len(dispatcher.history) == 1, f"Expected 1 alert, got {len(dispatcher.history)}"
    console.print("[bold green]✅ Rate limiting verified[/bold green]")


if __name__ == "__main__":
    run_crash_scenario()
    run_recovery_scenario()
    run_rate_limit_scenario()
    console.print("\n[bold green]All stress tests passed.[/bold green]")
