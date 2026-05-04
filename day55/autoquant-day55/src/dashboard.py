"""
dashboard.py — Rich CLI live dashboard for latency monitoring.

Layout:
  ┌─ Percentile Stats ─────────────┐  ┌─ Histogram ─────────────────────────┐
  │  p50 / p95 / p99 / min / max   │  │  ASCII bar chart of latency buckets  │
  └────────────────────────────────┘  └─────────────────────────────────────┘
  ┌─ Recent Samples ──────────────────────────────────────────────────────────┐
  │  order_id | side | symbol | latency_µs | latency_ms                      │
  └───────────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

from collections import deque

import numpy as np
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .match_engine import MatchResult
from .timer import LatencyRecorder

_SPARKLINE_BLOCKS = " ▁▂▃▄▅▆▇█"
_MAX_RECENT = 12


def _make_sparkline(counts: np.ndarray) -> str:
    if counts.size == 0:
        return "no data"
    peak = counts.max()
    if peak == 0:
        return _SPARKLINE_BLOCKS[0] * len(counts)
    normalized = (counts / peak * (len(_SPARKLINE_BLOCKS) - 1)).astype(int)
    return "".join(_SPARKLINE_BLOCKS[i] for i in normalized)


def _color_latency(val_us: float) -> str:
    """Traffic-light coloring for latency values."""
    if val_us < 100_000:
        return "green"
    if val_us < 300_000:
        return "yellow"
    return "red"


def build_layout(
    recorder: LatencyRecorder,
    recent: deque[MatchResult],
) -> Columns:
    stats = recorder.percentiles()
    edges, counts = recorder.histogram_bins(n_bins=12)

    # ── Percentile panel ───────────────────────────────────────────────────
    stat_table = Table.grid(padding=(0, 2))
    stat_table.add_column(justify="right", style="bold white")
    stat_table.add_column(justify="left")

    if stats:
        for key in ("p50", "p95", "p99", "min", "max"):
            val = stats[key]
            color = _color_latency(val)
            stat_table.add_row(
                f"[dim]{key}[/dim]",
                f"[{color}]{val:>12,.1f} µs[/{color}]   "
                f"[dim]{val / 1000:,.2f} ms[/dim]",
            )
        stat_table.add_row(
            "[dim]count[/dim]",
            f"[cyan]{int(stats['count']):>8,}[/cyan]  "
            f"[dim]({recorder.saturation:.1%} buffer)[/dim]",
        )
        if stats["negative"] > 0:
            stat_table.add_row(
                "[bold red]⚠ neg[/bold red]",
                f"[bold red]{int(stats['negative']):>8}  clock fault![/bold red]",
            )
    else:
        stat_table.add_row("[dim]waiting for samples...[/dim]", "")

    spark = _make_sparkline(counts) if counts.size > 0 else "no data"
    stat_panel = Panel(
        stat_table,
        title="[bold blue]Latency Percentiles[/bold blue]",
        subtitle=f"[dim]histogram: {spark}[/dim]",
        border_style="blue",
        width=52,
    )

    # ── Recent samples table ───────────────────────────────────────────────
    sample_table = Table(
        show_header=True,
        header_style="bold dim",
        border_style="dim",
        expand=True,
    )
    sample_table.add_column("Order ID", style="dim", width=10)
    sample_table.add_column("Side", width=5)
    sample_table.add_column("Symbol", width=6)
    sample_table.add_column("µs", justify="right", width=14)
    sample_table.add_column("ms", justify="right", width=10)

    for r in list(recent)[-_MAX_RECENT:]:
        s = r.latency_sample
        us = s.latency_us
        color = _color_latency(us)
        side_color = "green" if r.side == "BUY" else "red"
        sample_table.add_row(
            r.order_id[:8] + "…",
            f"[{side_color}]{r.side}[/{side_color}]",
            r.symbol,
            f"[{color}]{us:>12,.1f}[/{color}]",
            f"[dim]{us / 1000:>8,.2f}[/dim]",
        )

    sample_panel = Panel(
        sample_table,
        title="[bold green]Recent Matches[/bold green]",
        border_style="green",
        width=56,
    )

    return Columns([stat_panel, sample_panel])


class LiveDashboard:
    """Context manager wrapping Rich Live for the match engine loop."""

    def __init__(self, recorder: LatencyRecorder, refresh_rate: int = 4) -> None:
        self.recorder = recorder
        self._recent: deque[MatchResult] = deque(maxlen=_MAX_RECENT * 2)
        self._console = Console()
        self._live = Live(
            console=self._console,
            refresh_per_second=refresh_rate,
            screen=False,
        )

    def push(self, result: MatchResult) -> None:
        self._recent.append(result)
        self._live.update(build_layout(self.recorder, self._recent))

    def __enter__(self) -> "LiveDashboard":
        self._live.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self._live.__exit__(*args)
