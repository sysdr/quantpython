"""
Rich-powered CLI dashboard for real-time strategy monitoring.

Runs in a dedicated daemon thread so it has ZERO impact on the trading loop.
Polls strategy state via a callback at 10 Hz (100ms intervals).
The get_state callback acquires the StrategyState lock — we hold it only
as long as the dict copy takes (~1µs). The dashboard thread never holds
any lock shared with the trading path.
"""
from __future__ import annotations
import time
import threading
from typing import Callable

from rich.console    import Console
from rich.layout     import Layout
from rich.live       import Live
from rich.panel      import Panel
from rich.table      import Table
from rich.text       import Text
from rich            import box


class StrategyDashboard:
    REFRESH_HZ = 10

    def __init__(self, get_state: Callable[[], dict]) -> None:
        self._get_state = get_state
        self._console   = Console()
        self._running   = False
        self._thread:   threading.Thread | None = None
        self._sig_log:  list[dict] = []
        self._max_log   = 20

    def log_signal(self, signal_data: dict) -> None:
        """Thread-safe log append. Called from the execution layer."""
        self._sig_log.append(signal_data)
        if len(self._sig_log) > self._max_log:
            self._sig_log.pop(0)

    def _build(self) -> Layout:
        state  = self._get_state()
        layout = Layout()
        layout.split_column(
            Layout(name="header",  size=3),
            Layout(name="body"),
            Layout(name="footer",  size=3),
        )
        layout["body"].split_row(
            Layout(name="state",   ratio=1),
            Layout(name="signals", ratio=2),
        )

        # ── Header ────────────────────────────────────────────────────
        layout["header"].update(Panel(
            Text("⚡  AutoQuant-Alpha  ·  Day 8: on_tick() Engine", justify="center",
                 style="bold cyan"),
            style="cyan",
        ))

        # ── State panel ───────────────────────────────────────────────
        tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        tbl.add_column("Key",   style="dim")
        tbl.add_column("Value", style="bold")
        for k, v in state.items():
            if k == "position":
                color = "green" if v > 0 else ("red" if v < 0 else "white")
            elif k == "realized_pnl":
                color = "green" if v >= 0 else "red"
            else:
                color = "white"
            tbl.add_row(k, Text(str(v), style=color))
        layout["state"].update(Panel(tbl, title="Strategy State", border_style="blue"))

        # ── Signal log ────────────────────────────────────────────────
        sig = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        sig.add_column("Time",     style="dim",  width=10)
        sig.add_column("Dir",      width=6)
        sig.add_column("RefPrice", width=10)
        sig.add_column("Fill",     width=10)
        sig.add_column("Slip(bps)",width=10)
        sig.add_column("State",    width=10)
        for row in reversed(self._sig_log[-14:]):
            clr      = "green" if row.get("direction") == "LONG" else "red"
            slip     = row.get("slippage_bps")
            slip_str = f"{slip:.2f}" if slip is not None else "—"
            fill_str = f"{row.get('fill', 0.0):.4f}" if row.get("fill") else "—"
            sig.add_row(
                row.get("time", ""),
                Text(row.get("direction", ""), style=clr),
                f"{row.get('ref', 0.0):.4f}",
                fill_str,
                slip_str,
                row.get("state", ""),
            )
        layout["signals"].update(Panel(sig, title="Signal Log", border_style="green"))

        # ── Footer ────────────────────────────────────────────────────
        layout["footer"].update(Panel(
            Text(
                f"Buffer: {state.get('buffer_size', 0):>3}/100  │  "
                f"Fast EMA: {state.get('fast_ema', 0.0):>10.4f}  │  "
                f"Slow EMA: {state.get('slow_ema', 0.0):>10.4f}  │  "
                f"Cross: {state.get('prev_cross', 'none'):>5}",
                justify="center",
            ),
            style="dim",
        ))
        return layout

    def start(self) -> None:
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        with Live(
            self._build(),
            console=self._console,
            refresh_per_second=self.REFRESH_HZ,
            screen=True,
        ) as live:
            while self._running:
                live.update(self._build())
                time.sleep(1.0 / self.REFRESH_HZ)
