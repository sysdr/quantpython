"""
Live mode: connects to Alpaca Paper Trading WebSocket feed.

Requires .env with ALPACA_API_KEY and ALPACA_API_SECRET.
Run: python scripts/start.py
"""
from __future__ import annotations
import asyncio, logging, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)

from alpaca.trading.client import TradingClient
from src.strategies.momentum_scalp import MomentumScalp
from src.execution.order_manager   import OrderManager
from src.execution.alpaca_bridge   import AlpacaDataBridge
from src.dashboard.cli_dashboard   import StrategyDashboard

SYMBOLS = ["AAPL", "TSLA"]

async def main() -> None:
    api_key    = os.environ["ALPACA_API_KEY"]
    api_secret = os.environ["ALPACA_API_SECRET"]

    trading    = TradingClient(api_key, api_secret, paper=True)
    strategy   = MomentumScalp(symbol=SYMBOLS[0])
    dashboard  = StrategyDashboard(get_state=strategy.get_state_snapshot)
    manager    = OrderManager(
        alpaca_client=trading,
        on_fill=lambda sig, res: dashboard.log_signal({
            "time":        __import__("time").strftime("%H:%M:%S"),
            "direction":   sig.direction.name,
            "ref":         sig.reference_price,
            "fill":        res.fill_price,
            "slippage_bps": sig.slippage_bps,
            "state":       sig.state.name,
        }),
    )
    bridge = AlpacaDataBridge(
        api_key, api_secret, SYMBOLS, strategy,
        on_signal=manager.submit,
    )

    dashboard.start()
    consumer_task = asyncio.create_task(manager.run())

    try:
        await bridge.start()
    finally:
        manager.stop()
        await consumer_task
        dashboard.stop()

if __name__ == "__main__":
    asyncio.run(main())
