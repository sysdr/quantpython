"""
Demo mode: synthetic sine-wave price feed + live Rich dashboard.
No Alpaca credentials required.

Run: python scripts/demo.py
Stop: Ctrl+C
"""
from __future__ import annotations
import sys, os, time, random, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.types import MarketSnapshot, SignalState
from src.strategies.momentum_scalp import MomentumScalp
from src.dashboard.cli_dashboard import StrategyDashboard


def sine_price(t: float, base: float = 150.0, amp: float = 3.0, freq: float = 0.08) -> float:
    return base + amp * math.sin(2 * math.pi * freq * t) + random.gauss(0, 0.04)


def main() -> None:
    strategy  = MomentumScalp(symbol="DEMO", max_position=500)
    dashboard = StrategyDashboard(get_state=strategy.get_state_snapshot)
    dashboard.start()

    t = 0.0
    try:
        while True:
            price  = sine_price(t)
            spread = random.uniform(0.005, 0.06)
            snap   = MarketSnapshot(
                symbol="DEMO",
                bid=price - spread / 2,
                ask=price + spread / 2,
                last=price,
                volume=random.randint(100, 2_000),
                timestamp_ns=time.time_ns(),
            )

            signal = strategy.on_tick(snap)

            if signal is not None:
                # Simulate realistic fill with 0–3 bps slippage
                signal.fill_price = signal.reference_price * (
                    1 + random.uniform(0.0, 0.0003)
                )
                signal.state    = SignalState.FILLED
                signal.order_id = f"DEMO-{time.time_ns()}"

                dashboard.log_signal({
                    "time":        time.strftime("%H:%M:%S"),
                    "direction":   signal.direction.name,
                    "ref":         signal.reference_price,
                    "fill":        signal.fill_price,
                    "slippage_bps": signal.slippage_bps,
                    "state":       signal.state.name,
                })

            t  += 0.08
            time.sleep(0.04)   # ~25 ticks/sec

    except KeyboardInterrupt:
        dashboard.stop()
        print("\n[Demo] Session ended.")


if __name__ == "__main__":
    main()
