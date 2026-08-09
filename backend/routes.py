"""All API routes."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

import market_data
import portfolio as pf
from backtest import InsufficientData, run_backtest
from db import get_session, utcnow
from models import PriceBar, TickerMeta, WatchlistItem
from schemas import (
    PortfolioOut, PositionOut, PricesOut, QuoteOut, SearchResult, SignalOut,
    TradeOut, TradeRequest, WatchlistAdd, WatchlistEntry,
)
from signal_config import get_backtest_settings, get_signal_config
from signals import bollinger, compute_signal, sma

router = APIRouter(prefix="/api")


def _norm(ticker: str) -> str:
    return ticker.strip().upper()


def _closes(bars: list[PriceBar]) -> list[float]:
    return [b.close for b in bars]


def _signal_for(bars: list[PriceBar], cfg):
    """Full-OHLCV signal for a bar history (stochastic + OBV need H/L/V)."""
    return compute_signal(
        [b.close for b in bars],
        cfg,
        highs=[b.high for b in bars],
        lows=[b.low for b in bars],
        volumes=[b.volume for b in bars],
    )


def _bars_or_404(session: Session, ticker: str) -> list[PriceBar]:
    try:
        return market_data.ensure_history(session, ticker)
    except market_data.TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _meta_name(session: Session, ticker: str) -> str:
    meta = session.get(TickerMeta, ticker)
    return meta.name if meta and meta.name else ""


# ---------------------------------------------------------------------------
# Health / config
# ---------------------------------------------------------------------------

@router.get("/health")
def health():
    return {"status": "ok", "time": utcnow().isoformat()}


@router.get("/config")
def config():
    """Current signal config (reflects live edits to signals.yaml)."""
    cfg = get_signal_config()
    return {**asdict(cfg), "backtest": get_backtest_settings()}


# ---------------------------------------------------------------------------
# Search / watchlist
# ---------------------------------------------------------------------------

@router.get("/search", response_model=list[SearchResult])
def search(q: str = Query(min_length=1)):
    return market_data.search_symbols(q)


@router.get("/watchlist", response_model=list[WatchlistEntry])
def watchlist(session: Session = Depends(get_session)):
    items = session.execute(
        select(WatchlistItem).order_by(WatchlistItem.added_at)
    ).scalars()
    return [
        WatchlistEntry(ticker=w.ticker, name=_meta_name(session, w.ticker), added_at=w.added_at)
        for w in items
    ]


@router.post("/watchlist", response_model=WatchlistEntry, status_code=201)
def watchlist_add(body: WatchlistAdd, session: Session = Depends(get_session)):
    ticker = _norm(body.ticker)
    # Validates the symbol against Yahoo (fetches history on first sight).
    try:
        market_data.ensure_history(session, ticker, name=body.name)
    except market_data.TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if body.name:  # keep the friendly name even if history was already cached
        meta = session.get(TickerMeta, ticker)
        if meta and not meta.name:
            meta.name = body.name
    if session.get(WatchlistItem, ticker) is None:
        session.add(WatchlistItem(ticker=ticker, added_at=utcnow()))
    session.commit()
    return WatchlistEntry(ticker=ticker, name=_meta_name(session, ticker))


@router.delete("/watchlist/{ticker}")
def watchlist_remove(ticker: str, session: Session = Depends(get_session)):
    item = session.get(WatchlistItem, _norm(ticker))
    if item is None:
        raise HTTPException(status_code=404, detail="not on watchlist")
    session.delete(item)
    session.commit()
    return {"removed": _norm(ticker)}


# ---------------------------------------------------------------------------
# Prices / signals / quotes
# ---------------------------------------------------------------------------

@router.get("/tickers/{ticker}/prices", response_model=PricesOut)
def prices(ticker: str, days: int = Query(default=365, ge=10, le=800),
           session: Session = Depends(get_session)):
    ticker = _norm(ticker)
    bars = _bars_or_404(session, ticker)
    cfg = get_signal_config()
    closes = _closes(bars)
    # Overlays are computed over the FULL history, then sliced — so they are
    # correct from the first visible bar instead of starting with a None gap.
    sf = sma(closes, cfg.sma_fast)
    sl = sma(closes, cfg.sma_slow)
    bb = bollinger(closes, cfg.bb_period, cfg.bb_std)
    k = max(0, len(bars) - days)
    return PricesOut(
        ticker=ticker,
        name=_meta_name(session, ticker),
        dates=[b.date.isoformat() for b in bars[k:]],
        open=[b.open for b in bars[k:]],
        high=[b.high for b in bars[k:]],
        low=[b.low for b in bars[k:]],
        close=[b.close for b in bars[k:]],
        volume=[b.volume for b in bars[k:]],
        sma_fast=sf[k:],
        sma_slow=sl[k:],
        bb_upper=bb.upper[k:],
        bb_lower=bb.lower[k:],
    )


@router.post("/tickers/{ticker}/refresh")
def refresh(ticker: str, session: Session = Depends(get_session)):
    ticker = _norm(ticker)
    try:
        return market_data.refresh_history(session, ticker)
    except market_data.TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/tickers/{ticker}/signal", response_model=SignalOut)
def signal(ticker: str, session: Session = Depends(get_session)):
    ticker = _norm(ticker)
    bars = _bars_or_404(session, ticker)
    cfg = get_signal_config()
    closes = _closes(bars)
    sig = _signal_for(bars, cfg)
    prev = closes[-2] if len(closes) >= 2 else None
    return SignalOut(
        ticker=ticker,
        asof=bars[-1].date.isoformat(),
        close=closes[-1],
        prev_close=prev,
        change_pct=((closes[-1] / prev - 1) * 100) if prev else None,
        action=sig.action,
        score=sig.score,
        confidence=sig.confidence,
        reasons=[asdict(r) for r in sig.reasons],
        rsi=sig.rsi,
        macd_hist=sig.macd_hist,
        sma_fast=sig.sma_fast,
        sma_slow=sig.sma_slow,
        momentum_pct=sig.momentum_pct,
        percent_b=sig.percent_b,
        stoch_k=sig.stoch_k,
        stoch_d=sig.stoch_d,
    )


@router.get("/quotes", response_model=list[QuoteOut])
def quotes(tickers: str = Query(min_length=1), session: Session = Depends(get_session)):
    """Batch snapshot (last price, day change, signal) for the strip/watchlist."""
    out: list[QuoteOut] = []
    seen: set[str] = set()
    for raw in tickers.split(","):
        t = _norm(raw)
        if not t or t in seen:
            continue
        seen.add(t)
        if len(seen) > 30:
            break
        try:
            bars = market_data.ensure_history(session, t)
        except market_data.TickerNotFound as exc:
            out.append(QuoteOut(ticker=t, last=0.0, action="HOLD", confidence=0.0, error=str(exc)))
            continue
        closes = _closes(bars)
        sig = _signal_for(bars, get_signal_config())
        prev = closes[-2] if len(closes) >= 2 else None
        out.append(QuoteOut(
            ticker=t,
            name=_meta_name(session, t),
            last=closes[-1],
            prev=prev,
            change_pct=((closes[-1] / prev - 1) * 100) if prev else None,
            action=sig.action,
            confidence=sig.confidence,
            rsi=sig.rsi,
        ))
    return out


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

@router.get("/tickers/{ticker}/backtest")
def backtest(ticker: str, session: Session = Depends(get_session)):
    ticker = _norm(ticker)
    bars = _bars_or_404(session, ticker)
    cfg = get_signal_config()
    bt = get_backtest_settings()
    try:
        result = run_backtest(
            dates=[b.date for b in bars],
            opens=[b.open for b in bars],
            closes=[b.close for b in bars],
            cfg=cfg,
            initial_cash=bt["initial_cash"],
            fee_bps=bt["fee_bps"],
            highs=[b.high for b in bars],
            lows=[b.low for b in bars],
            volumes=[b.volume for b in bars],
        )
    except InsufficientData as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # JSON-serializable form
    result["ticker"] = ticker
    result["start_date"] = result["start_date"].isoformat()
    result["end_date"] = result["end_date"].isoformat()
    result["trades"] = [
        {**asdict(t), "date": t.date.isoformat()} for t in result["trades"]
    ]
    result["equity_curve"] = [
        {**p, "date": p["date"].isoformat()} for p in result["equity_curve"]
    ]
    return result


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

def _latest_close(session: Session, ticker: str) -> float:
    bars = market_data.load_bars(session, ticker)
    return bars[-1].close if bars else 0.0


@router.get("/portfolio", response_model=PortfolioOut)
def portfolio(session: Session = Depends(get_session)):
    acct = pf.get_account(session)
    cfg = get_signal_config()
    positions: list[PositionOut] = []
    holdings = 0.0
    unrealized = 0.0
    for pos in pf.get_positions(session):
        bars = market_data.load_bars(session, pos.ticker)
        last = bars[-1].close if bars else 0.0
        mv = pos.qty * last
        pnl = mv - pos.cost_basis
        holdings += mv
        unrealized += pnl
        action = confidence = None
        if bars:
            sig = _signal_for(bars, cfg)
            action, confidence = sig.action, sig.confidence
        positions.append(PositionOut(
            ticker=pos.ticker,
            qty=pos.qty,
            avg_cost=pos.cost_basis / pos.qty if pos.qty else 0.0,
            cost_basis=pos.cost_basis,
            last=last,
            market_value=mv,
            unrealized_pnl=pnl,
            unrealized_pct=(pnl / pos.cost_basis * 100) if pos.cost_basis else 0.0,
            action=action,
            confidence=confidence,
        ))
    realized = sum(t.realized_pnl or 0.0 for t in pf.get_trades(session, limit=10_000))
    return PortfolioOut(
        cash=acct.cash,
        holdings_value=holdings,
        equity=acct.cash + holdings,
        unrealized_pnl=unrealized,
        realized_pnl=realized,
        positions=positions,
    )


@router.post("/portfolio/trade", response_model=TradeOut)
def trade(body: TradeRequest, session: Session = Depends(get_session)):
    ticker = _norm(body.ticker)
    _bars_or_404(session, ticker)  # make sure we have price data
    price = _latest_close(session, ticker)
    try:
        t = pf.execute_trade(session, ticker, body.side, body.qty, price)
    except pf.TradeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return TradeOut(
        id=t.id, ticker=t.ticker, side=t.side, qty=t.qty, price=t.price,
        notional=t.notional, realized_pnl=t.realized_pnl, executed_at=t.executed_at,
    )


@router.get("/portfolio/trades", response_model=list[TradeOut])
def trade_history(session: Session = Depends(get_session)):
    return [
        TradeOut(
            id=t.id, ticker=t.ticker, side=t.side, qty=t.qty, price=t.price,
            notional=t.notional, realized_pnl=t.realized_pnl, executed_at=t.executed_at,
        )
        for t in pf.get_trades(session)
    ]


@router.post("/portfolio/reset")
def portfolio_reset(session: Session = Depends(get_session)):
    acct = pf.reset_account(session)
    return {"cash": acct.cash, "positions": 0, "trades": 0}
