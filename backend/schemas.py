"""Pydantic response/request models for the API."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    symbol: str
    name: str = ""
    exchange: str = ""
    type: str = ""


class WatchlistEntry(BaseModel):
    ticker: str
    name: str = ""
    added_at: Optional[datetime] = None


class WatchlistAdd(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    name: str = ""


class ReasonOut(BaseModel):
    key: str
    detail: str
    direction: int


class SignalOut(BaseModel):
    ticker: str
    asof: str                    # ISO date of the bar the signal is computed on
    close: float
    prev_close: Optional[float] = None
    change_pct: Optional[float] = None
    action: str
    score: float
    confidence: float
    reasons: list[ReasonOut]
    rsi: Optional[float] = None
    macd_hist: Optional[float] = None
    sma_fast: Optional[float] = None
    sma_slow: Optional[float] = None
    momentum_pct: Optional[float] = None
    percent_b: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None


class PricesOut(BaseModel):
    ticker: str
    name: str = ""
    dates: list[str]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float]
    sma_fast: list[Optional[float]]
    sma_slow: list[Optional[float]]
    bb_upper: list[Optional[float]]
    bb_lower: list[Optional[float]]


class QuoteOut(BaseModel):
    ticker: str
    name: str = ""
    last: float
    prev: Optional[float] = None
    change_pct: Optional[float] = None
    action: str
    confidence: float
    rsi: Optional[float] = None
    error: Optional[str] = None


class TradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    side: str = Field(pattern="(?i)^(buy|sell)$")  # flag must be at position 0 (py3.12+)
    qty: float = Field(gt=0)


class TradeOut(BaseModel):
    id: int
    ticker: str
    side: str
    qty: float
    price: float
    notional: float
    realized_pnl: Optional[float] = None
    executed_at: datetime


class PositionOut(BaseModel):
    ticker: str
    qty: float
    avg_cost: float
    cost_basis: float
    last: float
    market_value: float
    unrealized_pnl: float
    unrealized_pct: float
    action: Optional[str] = None
    confidence: Optional[float] = None


class PortfolioOut(BaseModel):
    cash: float
    holdings_value: float
    equity: float
    unrealized_pnl: float
    realized_pnl: float
    positions: list[PositionOut]
