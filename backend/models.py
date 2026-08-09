"""SQLAlchemy ORM models.

Timestamps are timezone-aware and stored as UTC (see db.UTCDateTime).
Daily bars carry a calendar ``date`` (a trading day is a date, not an
instant); their fetch time is a proper UTC timestamp.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db import Base, UTCDateTime, utcnow


class TickerMeta(Base):
    """Display metadata + refresh bookkeeping for any ticker we've fetched."""
    __tablename__ = "ticker_meta"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    exchange: Mapped[str] = mapped_column(String(40), default="")
    currency: Mapped[str] = mapped_column(String(12), default="")
    last_refreshed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PriceBar(Base):
    """One daily OHLCV bar. Prices are split/dividend adjusted (yfinance auto_adjust)."""
    __tablename__ = "price_bars"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Account(Base):
    """Single paper-trading account (row id is always 1)."""
    __tablename__ = "account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    cash: Mapped[float] = mapped_column(Float, default=100_000.0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Position(Base):
    __tablename__ = "positions"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    qty: Mapped[float] = mapped_column(Float)
    cost_basis: Mapped[float] = mapped_column(Float)  # total dollars paid for current qty


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(4))  # "BUY" | "SELL"
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)      # execution price (latest close)
    notional: Mapped[float] = mapped_column(Float)   # qty * price
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)  # sells only
    executed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
