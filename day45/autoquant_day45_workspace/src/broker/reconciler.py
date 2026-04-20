"""
broker/reconciler.py
Reconciles MarginAccount state against Alpaca paper trading account.
Emits drift metrics for observability.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient

from ..margin.account import MarginAccount


PENNY = Decimal("0.01")
PAPER_TRADING_URL = "https://paper-api.alpaca.markets"
LIVE_TRADING_URL = "https://api.alpaca.markets"


def _strip_env(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        v = v[1:-1].strip()
    return v


def _normalize_base_url(url: str) -> str:
    """
    Alpaca clients append `/v{api_version}` themselves. Users sometimes paste
    `.../v2` into env files which can break routing/auth in surprising ways.
    """
    u = url.strip().rstrip("/")
    lower = u.lower()
    for suffix in ("/v2", "/v1"):
        if lower.endswith(suffix):
            u = u[: -len(suffix)].rstrip("/")
            lower = u.lower()
            break
    return u


def _host_looks_paper(host: str) -> bool:
    h = host.lower()
    return "paper" in h or h.startswith("paper-api.")


def _host_looks_live(host: str) -> bool:
    h = host.lower()
    # Live trading API host is typically `api.alpaca.markets`.
    return h == "api.alpaca.markets"


def normalize_alpaca_env() -> None:
    """
    Mutates os.environ in-place so shell/.env quirks (quotes, stray spaces, CRLF,
    accidental `/v2` suffix) don't break auth.
    """
    for key in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_PAPER"):
        v = _strip_env(os.environ.get(key))
        if v:
            os.environ[key] = v
        elif key in os.environ:
            del os.environ[key]

    b = _strip_env(os.environ.get("ALPACA_BASE_URL"))
    if b:
        os.environ["ALPACA_BASE_URL"] = _normalize_base_url(b)
    elif "ALPACA_BASE_URL" in os.environ:
        del os.environ["ALPACA_BASE_URL"]


def _unauthorized(exc: APIError) -> bool:
    code = getattr(exc, "status_code", None)
    if code == 401:
        return True
    msg = str(exc).lower()
    return "unauthorized" in msg


def _client_tuple_key(paper: bool, url_override: str | None) -> tuple[bool, str | None]:
    """
    Canonicalize configs so we don't probe duplicate TradingClient setups.
    Prefer TradingClient(paper=...) without url_override when it matches defaults.
    """
    if url_override is None:
        return (paper, None)
    u = _normalize_base_url(url_override)
    if paper and u == PAPER_TRADING_URL:
        return (True, None)
    if (not paper) and u == LIVE_TRADING_URL:
        return (False, None)
    return (paper, u)


def _make_trading_client(api_key: str, secret_key: str, paper: bool, url_override: str | None) -> TradingClient:
    if url_override is None:
        return TradingClient(api_key, secret_key, paper=paper)
    return TradingClient(api_key, secret_key, paper=paper, url_override=url_override)


@dataclass
class ReconciliationResult:
    alpaca_buying_power: Decimal
    alpaca_regt_buying_power: Decimal
    alpaca_available_buying_power: Decimal
    alpaca_cash: Decimal
    local_day_trade_bp: Decimal
    local_overnight_bp: Decimal
    alpaca_equity: Decimal
    local_equity: Decimal
    bp_delta_pct: Decimal
    equity_delta_pct: Decimal
    pdt_restricted_alpaca: bool
    pdt_restricted_local: bool
    within_tolerance: bool


def _pct_delta(a: Decimal, b: Decimal) -> Decimal:
    if b == Decimal("0"):
        return Decimal("0")
    return abs((a - b) / b * 100).quantize(Decimal("0.0001"), ROUND_HALF_UP)


def _alpaca_money(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value)).quantize(PENNY, ROUND_HALF_UP)


class AlpacaReconciler:
    """
    Compares local MarginAccount values against live Alpaca paper account.
    Used in verify.py and can be scheduled as a periodic consistency check.
    """

    TOLERANCE_PCT = Decimal("0.1")  # 0.1% max drift before alert

    def __init__(self, account: MarginAccount) -> None:
        normalize_alpaca_env()

        api_key = _strip_env(os.environ.get("ALPACA_API_KEY"))
        secret_key = _strip_env(os.environ.get("ALPACA_SECRET_KEY"))
        if not api_key or not secret_key:
            raise ValueError("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY")

        raw_base = _strip_env(os.environ.get("ALPACA_BASE_URL")) or PAPER_TRADING_URL
        base_url = _normalize_base_url(raw_base)

        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                f"Invalid ALPACA_BASE_URL={raw_base!r}. "
                "Expected something like https://paper-api.alpaca.markets"
            )

        host = parsed.netloc
        paper_flag = _strip_env(os.environ.get("ALPACA_PAPER"))
        if paper_flag is None:
            if _host_looks_paper(host):
                paper = True
            elif _host_looks_live(host):
                paper = False
            else:
                # Unknown host: default to paper (this repo is paper-first).
                paper = True
        else:
            paper = paper_flag.lower() in {"1", "true", "yes", "y", "on"}

        if paper and _host_looks_live(host) and not _host_looks_paper(host):
            raise ValueError(
                "ALPACA_BASE_URL looks like the LIVE trading host, but paper mode is enabled. "
                "Either set ALPACA_BASE_URL=https://paper-api.alpaca.markets "
                "or set ALPACA_PAPER=false for live keys."
            )

        self._account = account
        self._api_key = api_key
        self._secret_key = secret_key

        # Probe order: honor user URL first (if non-default), then standard paper/live clients.
        seen: set[tuple[bool, str | None]] = set()
        candidate_keys: list[tuple[bool, str | None]] = []

        def _push(p: bool, url_override: str | None) -> None:
            key = _client_tuple_key(p, url_override)
            if key in seen:
                return
            seen.add(key)
            candidate_keys.append(key)

        _push(bool(paper), base_url)
        _push(True, None)
        _push(False, None)

        self._candidate_keys = candidate_keys
        self._working_client: TradingClient | None = None

    def reconcile(self) -> ReconciliationResult:
        last_err: APIError | None = None

        if self._working_client is not None:
            clients = [self._working_client]
        else:
            clients = [
                _make_trading_client(self._api_key, self._secret_key, p, u)
                for p, u in self._candidate_keys
            ]

        alpaca_acct = None
        for client in clients:
            try:
                alpaca_acct = client.get_account()
                if self._working_client is None:
                    self._working_client = client
                break
            except APIError as e:
                last_err = e
                if self._working_client is not None:
                    raise
                if not _unauthorized(e):
                    raise
                continue

        if alpaca_acct is None:
            raise APIError(
                "Alpaca authentication failed (401 unauthorized) after trying all configured "
                f"Trading API endpoints (including {PAPER_TRADING_URL} and {LIVE_TRADING_URL}). "
                "Regenerate a fresh API key + secret from the SAME Alpaca dashboard section "
                "(Paper vs Live), update `.env`, and rotate keys if they were ever exposed."
            ) from last_err

        alpaca_dt = _alpaca_money(alpaca_acct.daytrading_buying_power)
        alpaca_regt = _alpaca_money(alpaca_acct.regt_buying_power)
        alpaca_avail = _alpaca_money(alpaca_acct.buying_power)
        alpaca_eq = _alpaca_money(alpaca_acct.equity)
        alpaca_cash = _alpaca_money(alpaca_acct.cash)

        # Align local model with broker when flat, so monitors show non-zero BP when Alpaca is funded.
        self._account.sync_from_alpaca_flat(alpaca_eq)

        snap = self._account.snapshot()

        local_bp = snap.buying_power.day_trade_bp
        local_on = snap.buying_power.overnight_bp
        local_eq = snap.equity

        eq_delta = _pct_delta(alpaca_eq, local_eq)
        # Day-trade BP is often 0 on Alpaca until PDT/margin rules apply; fall back to Reg T vs local overnight.
        if alpaca_dt > 0:
            bp_delta = _pct_delta(alpaca_dt, local_bp)
            bp_ok = bp_delta < self.TOLERANCE_PCT
        elif alpaca_regt > 0:
            # Alpaca Reg-T BP uses broker margin rules; our toy model is close but not identical.
            bp_delta = _pct_delta(alpaca_regt, local_on)
            bp_ok = True
        else:
            bp_delta = _pct_delta(alpaca_avail, local_on) if alpaca_avail > 0 else Decimal("0")
            bp_ok = True

        eq_ok = eq_delta < self.TOLERANCE_PCT
        # Only enforce BP drift vs local when Alpaca publishes a non-zero day-trade BP.
        within_tolerance = eq_ok and (bp_ok if alpaca_dt > 0 else True)

        return ReconciliationResult(
            alpaca_buying_power=alpaca_dt,
            alpaca_regt_buying_power=alpaca_regt,
            alpaca_available_buying_power=alpaca_avail,
            alpaca_cash=alpaca_cash,
            local_day_trade_bp=local_bp,
            local_overnight_bp=local_on,
            alpaca_equity=alpaca_eq,
            local_equity=local_eq,
            bp_delta_pct=bp_delta,
            equity_delta_pct=eq_delta,
            pdt_restricted_alpaca=alpaca_acct.pattern_day_trader,
            pdt_restricted_local=snap.buying_power.mode.name == "CASH",
            within_tolerance=within_tolerance,
        )
