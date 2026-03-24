#!/usr/bin/env python3
"""
scripts/start.py — Simulate a delta-hedge session against Alpaca paper trading.
Runs a synthetic 5-minute session, firing hedges when |net delta| > threshold.
"""
import sys, os, time, random, logging
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from src.greeks.models import (
    OptionContract, OptionPosition, PortfolioGreeks, MarketState
)
from src.greeks.vol_surface import VolSurface
from src.execution.hedge_engine import DeltaHedgeEngine, HedgeConfig

vol_surface = VolSurface.build_synthetic(spot=500.0)
contracts_spec = [
    ("call", 500, 1/52, -50),
    ("put",  495, 1/52,  50),
    ("call", 505, 1/12,  20),
    ("put",  490, 1/12, -20),
]

positions = []
for opt_type, strike, expiry, qty in contracts_spec:
    iv = vol_surface.get_iv(K=strike, S=500.0, T=expiry)
    c = OptionContract(
        symbol="SPY", strike=strike, expiry_years=expiry,
        option_type=opt_type, implied_vol=iv,
    )
    positions.append(OptionPosition(contract=c, quantity=qty, entry_price=2.0))

portfolio = PortfolioGreeks(positions=positions)
config = HedgeConfig(
    underlying_symbol="SPY",
    delta_threshold=50.0,
    spread_cost_bps=2.0,
    min_hedge_interval_s=5.0,
)
engine = DeltaHedgeEngine(portfolio=portfolio, config=config)

spot = 500.0
r = 0.053
session_start = time.time()
print("Starting 5-minute delta hedge simulation session...")
print(f"  Positions: {len(positions)}")
print(f"  Delta threshold: ±{config.delta_threshold}")
print()

tick = 0
while time.time() - session_start < 300:
    spot += random.gauss(0, 0.30)
    spot = max(470.0, min(530.0, spot))
    mkt = MarketState(spot=spot, risk_free_rate=r, timestamp_ns=time.perf_counter_ns())

    result = engine.check_and_hedge(mkt)
    if result:
        print(f"  [HEDGE] order_id={result.order_id} "
              f"shares={result.shares_ordered} side={result.side} "
              f"delta_before={result.delta_before:+.2f}")

    if tick % 40 == 0:
        nd = portfolio.net_delta(mkt)
        ng = portfolio.net_gamma(mkt)
        hc = portfolio.total_hedge_cost
        print(f"  tick={tick:4d}  spot={spot:.2f}  "
              f"net_Δ={nd:+8.2f}  net_Γ={ng:+.4f}  hedge_cost=${hc:.2f}")
    tick += 1
    time.sleep(0.1)

print(f"\nSession complete. Total hedges: {len(engine.hedge_history)}")
print(f"Cumulative hedge cost: ${portfolio.total_hedge_cost:.4f}")
if engine.hedge_history:
    print(f"Last order_id: {engine.hedge_history[-1].order_id}")
