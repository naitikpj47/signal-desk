"""Walk-forward backtest of the signal rules. Pure — no I/O, no DB.

Anti-lookahead design
---------------------
1. The decision for day *t* uses ``score_at(indicators, t)`` — indicator values
   at index *t* depend only on closes ``<= t`` (causal filters; asserted by the
   test suite), so precomputing full indicator arrays introduces no leakage.
2. A decision made on close *t* executes at the **next day's open** (*t+1*).
   Filling at the very close you just observed would itself be lookahead.
3. Scoring goes through the exact same ``score_at`` function as the live
   /signal endpoint, so backtest and dashboard can never disagree on rules.

Strategy: long-only, all-in/all-out. BUY signal while flat -> invest all cash;
SELL signal while holding -> liquidate. Transaction cost (default 10 bps) is
charged on notional for every fill, including the buy-and-hold benchmark's
single entry.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from signals import SignalConfig, compute_indicators, score_at


class InsufficientData(ValueError):
    """Not enough bars to run a meaningful backtest."""


@dataclass(frozen=True)
class BacktestTrade:
    date: date
    side: str          # "BUY" | "SELL"
    price: float       # fill price (next day's open)
    qty: float
    fee: float
    equity_after: float


def max_drawdown(equity: list[float]) -> float:
    """Largest peak-to-trough decline, as a fraction (0.25 == -25%)."""
    peak = float("-inf")
    worst = 0.0
    for e in equity:
        peak = max(peak, e)
        if peak > 0:
            worst = max(worst, (peak - e) / peak)
    return worst


def run_backtest(
    dates: list[date],
    opens: list[float],
    closes: list[float],
    cfg: Optional[SignalConfig] = None,
    initial_cash: float = 10_000.0,
    fee_bps: float = 10.0,
    highs: Optional[list[float]] = None,
    lows: Optional[list[float]] = None,
    volumes: Optional[list[float]] = None,
) -> dict:
    cfg = cfg or SignalConfig()
    n = len(closes)
    if not (len(dates) == len(opens) == n):
        raise ValueError("dates, opens and closes must be the same length")

    i0 = cfg.warmup_bars()
    # Need at least one decision bar (i0) plus one execution bar (i0 + 1).
    if n < i0 + 2:
        raise InsufficientData(
            f"need at least {i0 + 2} bars for this config (warmup {i0}), got {n}"
        )

    fee_rate = fee_bps / 10_000.0
    ind = compute_indicators(closes, cfg, highs=highs, lows=lows, volumes=volumes)

    cash = initial_cash
    qty = 0.0
    entry_cost: float = 0.0          # cash spent on the open round trip (incl. fee)
    pending: Optional[str] = None    # decision from yesterday, fills at today's open

    trades: list[BacktestTrade] = []
    round_trip_pnls: list[float] = []
    equity: list[float] = []

    # Buy-and-hold benchmark: single entry at the first possible fill
    # (open of bar i0 + 1), same fee, marked to market at each close.
    bh_entry_price = opens[i0 + 1]
    bh_qty = initial_cash / (bh_entry_price * (1 + fee_rate)) if bh_entry_price > 0 else 0.0
    bh_equity: list[float] = []

    for j in range(i0, n):
        # 1) Fill yesterday's decision at today's open.
        if pending == "BUY" and qty == 0.0 and cash > 0.0:
            px = opens[j]
            if px > 0:
                qty = cash / (px * (1 + fee_rate))
                fee = qty * px * fee_rate
                entry_cost = cash
                cash = 0.0
                trades.append(BacktestTrade(dates[j], "BUY", px, qty, fee, qty * closes[j]))
        elif pending == "SELL" and qty > 0.0:
            px = opens[j]
            gross = qty * px
            fee = gross * fee_rate
            proceeds = gross - fee
            round_trip_pnls.append(proceeds - entry_cost)
            trades.append(BacktestTrade(dates[j], "SELL", px, qty, fee, proceeds))
            cash = proceeds
            qty = 0.0
            entry_cost = 0.0
        pending = None

        # 2) Decide on today's close (no bar after the last one to fill on).
        if j < n - 1:
            sig = score_at(ind, j, cfg)
            if sig.action == "BUY" and qty == 0.0:
                pending = "BUY"
            elif sig.action == "SELL" and qty > 0.0:
                pending = "SELL"

        # 3) Mark to market at today's close.
        equity.append(cash + qty * closes[j])
        bh_equity.append(initial_cash if j == i0 else bh_qty * closes[j])

    final_equity = equity[-1]
    bh_final = bh_equity[-1]
    wins = sum(1 for p in round_trip_pnls if p > 0)

    return {
        "start_date": dates[i0],
        "end_date": dates[-1],
        "bars_tested": n - i0,
        "warmup_bars": i0,
        "initial_cash": initial_cash,
        "fee_bps": fee_bps,
        "strategy": {
            "final_equity": final_equity,
            "total_return_pct": (final_equity / initial_cash - 1) * 100,
            "max_drawdown_pct": max_drawdown(equity) * 100,
            "num_fills": len(trades),
            "round_trips": len(round_trip_pnls),
            "win_rate_pct": (wins / len(round_trip_pnls) * 100) if round_trip_pnls else None,
            "position_open_at_end": qty > 0.0,
        },
        "buy_hold": {
            "final_equity": bh_final,
            "total_return_pct": (bh_final / initial_cash - 1) * 100,
            "max_drawdown_pct": max_drawdown(bh_equity) * 100,
        },
        "excess_return_pct": (final_equity - bh_final) / initial_cash * 100,
        "trades": trades,
        "equity_curve": [
            {"date": dates[i0 + k], "strategy": equity[k], "buy_hold": bh_equity[k]}
            for k in range(len(equity))
        ],
    }
