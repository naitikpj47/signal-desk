"""Paper-trading portfolio engine: cash, positions at average cost, trades.

Fills happen at the latest cached close for the ticker. No fees on paper
trades (the 10 bps cost model applies to backtests, per spec).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Account, Position, Trade

START_CASH = 100_000.0


class TradeError(ValueError):
    """Invalid paper trade (insufficient cash/shares, bad qty)."""


def get_account(session: Session) -> Account:
    acct = session.get(Account, 1)
    if acct is None:
        acct = Account(id=1, cash=START_CASH)
        session.add(acct)
        session.commit()
    return acct


def get_positions(session: Session) -> list[Position]:
    return list(session.execute(select(Position).order_by(Position.ticker)).scalars())


def get_trades(session: Session, limit: int = 200) -> list[Trade]:
    return list(
        session.execute(select(Trade).order_by(Trade.id.desc()).limit(limit)).scalars()
    )


def execute_trade(session: Session, ticker: str, side: str, qty: float, price: float) -> Trade:
    """Buy or sell at the given price, enforcing cash/share constraints."""
    if qty <= 0:
        raise TradeError("quantity must be positive")
    if price <= 0:
        raise TradeError(f"no valid price for {ticker}")
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise TradeError(f"side must be BUY or SELL, got {side!r}")

    acct = get_account(session)
    pos = session.get(Position, ticker)
    notional = qty * price

    if side == "BUY":
        if notional > acct.cash + 1e-9:
            raise TradeError(
                f"insufficient cash: need ${notional:,.2f}, have ${acct.cash:,.2f}"
            )
        acct.cash -= notional
        if pos is None:
            pos = Position(ticker=ticker, qty=qty, cost_basis=notional)
            session.add(pos)
        else:
            pos.qty += qty
            pos.cost_basis += notional
        trade = Trade(ticker=ticker, side="BUY", qty=qty, price=price, notional=notional)
    else:
        if pos is None or qty > pos.qty + 1e-9:
            held = pos.qty if pos else 0
            raise TradeError(f"insufficient shares: selling {qty}, hold {held}")
        avg_cost = pos.cost_basis / pos.qty
        realized = notional - avg_cost * qty
        acct.cash += notional
        remaining = pos.qty - qty
        if remaining <= 1e-9:
            session.delete(pos)
        else:
            # Reduce cost basis proportionally; average cost per share is unchanged.
            pos.cost_basis = avg_cost * remaining
            pos.qty = remaining
        trade = Trade(
            ticker=ticker, side="SELL", qty=qty, price=price,
            notional=notional, realized_pnl=realized,
        )

    session.add(trade)
    session.commit()
    return trade


def reset_account(session: Session) -> Account:
    """Wipe positions and trades, restore starting cash."""
    for pos in get_positions(session):
        session.delete(pos)
    for tr in session.execute(select(Trade)).scalars():
        session.delete(tr)
    acct = get_account(session)
    acct.cash = START_CASH
    session.commit()
    return acct
