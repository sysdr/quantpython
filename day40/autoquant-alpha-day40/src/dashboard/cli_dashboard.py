from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from src.tracking.lifecycle_tracker import LifecycleTracker

STATE_COLORS: dict[str, str] = {
    "new":              "dim white",
    "pending_submit":   "yellow",
    "accepted":         "cyan",
    "partially_filled": "blue",
    "filled":           "green",
    "cancelled":        "red",
    "rejected":         "bright_red",
    "expired":          "orange3",
}


def _lat(val: float | None, warn_ms: float = 100, crit_ms: float = 300) -> str:
    if val is None:
        return "[grey70]—[/grey70]"
    if val < 0:
        return f"[bright_yellow]{val:,.1f}[/bright_yellow]"
    color = "green" if val < warn_ms else "yellow" if val < crit_ms else "red"
    return f"[bright_{color}]{val:,.1f}[/bright_{color}]"


def _ts(dt: datetime | None) -> str:
    """Render UTC timestamps as HH:MM:SS.mmm."""
    if dt is None:
        return "[grey70]—[/grey70]"
    s = dt.astimezone(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
    return f"[bright_white]{s}[/bright_white]"

def _missing(val: object) -> bool:
    return val is None or val == ""  # type: ignore[comparison-overlap]


def _fmt_px(val: float | None) -> str:
    if _missing(val) or not val:
        return "[grey70]—[/grey70]"
    return f"[bright_white]{val:,.4f}[/bright_white]"


def _net_ms(lc) -> float | None:
    """
    Net time in ms.
    - If we have a fill timestamp: (last_fill_at - submitted_at)
    - Else if submitted: elapsed since submitted
    - Else: None
    """
    now = datetime.now(timezone.utc)
    if lc.submitted_at is None:
        return None
    end = lc.last_fill_at or now
    return (end - lc.submitted_at).total_seconds() * 1_000.0


def build_order_table(tracker: "LifecycleTracker") -> Table:
    t = Table(
        title="Order Lifecycle Tracker — Day 40",
        box=box.SIMPLE_HEAVY,
        header_style="bold bright_white",
        border_style="grey50",
        expand=True,
        show_lines=False,
    )
    # Fixed widths keep headers fully readable (no "Sym…", "Sub…", etc.)
    # while still fitting typical 120-col terminals.
    # Keep the table within ~80 columns so headers don't truncate in typical terminals.
    cols = [
        # name,        style,          right, width
        ("Order ID",   "bright_cyan",  False, 10),
        ("Symbol",     "bold",         False, 6),
        ("Side",       "",             False, 4),
        ("State",      "",             False, 16),
        ("Filled Qty", "bright_white", True,  12),
        ("Fill Price", "bright_white", True,  10),
        ("Net (ms)",   "bright_white", True,  8),
    ]
    for name, style, right, width in cols:
        t.add_column(
            name,
            style=style,
            justify="right" if right else "left",
            no_wrap=True,
            overflow="ellipsis",
            width=width,
        )

    recent = list(tracker._orders.values())[-30:]
    for lc in reversed(recent):
        color = STATE_COLORS.get(lc.state.value, "white")
        side_str = "[green]buy[/green]" if lc.side == "buy" else "[red]sell[/red]"
        denom = str(int(lc.qty)) if float(lc.qty).is_integer() else f"{lc.qty:.2f}"
        # Show avg fill price for both filled and partially_filled orders (or any order with fills).
        fill_px = _fmt_px(lc.avg_fill_price if (lc.filled_qty > 0 or lc.state.value in ("filled", "partially_filled")) else None)
        t.add_row(
            lc.order_id[-12:],
            lc.symbol,
            side_str,
            f"[{color}]{lc.state.value}[/{color}]",
            f"{lc.filled_qty:.2f}/{denom}",
            fill_px,
            _lat(_net_ms(lc)),
        )
    return t


def build_stats_panel(tracker: "LifecycleTracker") -> Panel:
    s = tracker.stats
    header = Table.grid(expand=True)
    header.add_column(justify="left")
    header.add_column(justify="right")
    header.add_row(
        f"[grey70]Tracked[/grey70] [bright_white]{s['total_tracked']}[/bright_white]    "
        f"[grey70]Orphan fills[/grey70] [bright_white]{s['orphan_fills']}[/bright_white]    "
        f"[grey70]Evictions[/grey70] [bright_white]{s['evictions']}[/bright_white]",
        f"[grey70]{datetime.now(timezone.utc).strftime('%H:%M:%S.%f')[:-3]} UTC[/grey70]",
    )

    state_str = "  ".join(
        f"[{STATE_COLORS.get(k, 'white')}]{k}[/]={v}"
        for k, v in sorted(s["by_state"].items())
    )
    states_line = f"[grey70]{state_str}[/grey70]" if state_str else "[grey70]—[/grey70]"

    layout = Table.grid(expand=True)
    layout.add_row(header)
    layout.add_row(states_line)
    return Panel(layout, title="Tracker Stats", border_style="grey30", padding=(0, 1))


class LiveDashboard:
    """Rich live dashboard updating at `refresh_hz` Hz."""

    def __init__(self, tracker: "LifecycleTracker", refresh_hz: float = 4.0) -> None:
        self._tracker = tracker
        self._interval = 1.0 / max(refresh_hz, 0.5)
        self._console = Console()

    def _render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(build_stats_panel(self._tracker), name="stats", size=6),
            Layout(build_order_table(self._tracker),  name="table"),
        )
        return layout

    async def run(self) -> None:
        with Live(
            self._render(),
            console=self._console,
            refresh_per_second=int(1.0 / self._interval),
            screen=True,
        ) as live:
            while True:
                live.update(self._render())
                await asyncio.sleep(self._interval)
