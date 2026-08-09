"""yfinance data access + SQLite caching.

Policy:
- First request for a ticker pulls 2 years of daily OHLCV and caches it.
- Refresh re-fetches from the last cached date onward (inclusive, so a bar
  cached intraday gets corrected to its final values) and upserts only what
  came back — no full re-download.
- Bars use yfinance's auto_adjust=True (split/dividend-adjusted OHLC), which
  is what you want for indicator math across 2 years.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from db import utcnow
from models import PriceBar, TickerMeta

log = logging.getLogger("signaldesk.data")

HISTORY_PERIOD = "2y"


class TickerNotFound(Exception):
    """Raised when Yahoo returns no usable daily data for a symbol."""


def _bars_from_dataframe(ticker: str, df) -> list[dict]:
    """Normalize a yfinance history() frame into plain row dicts.

    yfinance daily indexes are timezone-aware midnights in the exchange's
    local zone; ``.date()`` on each stamp yields the exchange-local trading
    day, which is the calendar date we key bars by.
    """
    rows: list[dict] = []
    if df is None or df.empty:
        return rows
    for ts, row in df.iterrows():
        close = row.get("Close")
        if close is None or close != close:  # NaN check without importing numpy
            continue
        d = ts.date() if hasattr(ts, "date") else ts
        rows.append(
            {
                "ticker": ticker,
                "date": d,
                "open": float(row.get("Open", close)),
                "high": float(row.get("High", close)),
                "low": float(row.get("Low", close)),
                "close": float(close),
                "volume": float(row.get("Volume", 0) or 0),
                "fetched_at": utcnow(),
            }
        )
    return rows


def _fetch(ticker: str, start: date | None = None):
    t = yf.Ticker(ticker)
    if start is None:
        return t.history(period=HISTORY_PERIOD, interval="1d", auto_adjust=True)
    return t.history(start=start.isoformat(), interval="1d", auto_adjust=True)


def _upsert_bars(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = sqlite_insert(PriceBar).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[PriceBar.ticker, PriceBar.date],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )
    session.execute(stmt)
    return len(rows)


def _touch_meta(session: Session, ticker: str, name: str = "", exchange: str = "", currency: str = "") -> None:
    meta = session.get(TickerMeta, ticker)
    if meta is None:
        meta = TickerMeta(ticker=ticker)
        session.add(meta)
    if name:
        meta.name = name
    if exchange:
        meta.exchange = exchange
    if currency:
        meta.currency = currency
    meta.last_refreshed_at = utcnow()


def last_cached_date(session: Session, ticker: str) -> date | None:
    return session.execute(
        select(PriceBar.date).where(PriceBar.ticker == ticker).order_by(PriceBar.date.desc()).limit(1)
    ).scalar_one_or_none()


def load_bars(session: Session, ticker: str) -> list[PriceBar]:
    """All cached bars for a ticker, oldest first."""
    return list(
        session.execute(
            select(PriceBar).where(PriceBar.ticker == ticker).order_by(PriceBar.date.asc())
        ).scalars()
    )


def ensure_history(session: Session, ticker: str, name: str = "") -> list[PriceBar]:
    """Return cached bars, doing the initial 2-year fetch if the cache is empty."""
    bars = load_bars(session, ticker)
    if bars:
        return bars
    df = _fetch(ticker)
    rows = _bars_from_dataframe(ticker, df)
    if not rows:
        raise TickerNotFound(f"no daily price data returned for '{ticker}'")
    _upsert_bars(session, rows)
    _touch_meta(session, ticker, name=name)
    session.commit()
    log.info("initial fetch %s: %d bars", ticker, len(rows))
    return load_bars(session, ticker)


def refresh_history(session: Session, ticker: str) -> dict:
    """Pull only missing dates (plus a re-fetch of the last cached bar).

    Returns a summary dict for the API response.
    """
    last = last_cached_date(session, ticker)
    if last is None:
        bars = ensure_history(session, ticker)
        return {"ticker": ticker, "mode": "initial", "bars_upserted": len(bars),
                "last_date": bars[-1].date.isoformat() if bars else None}

    today = utcnow().date()
    if last >= today:
        # Cache already has today's bar; nothing new can exist yet.
        return {"ticker": ticker, "mode": "up_to_date", "bars_upserted": 0, "last_date": last.isoformat()}

    # Start at the last cached date so a bar cached mid-session gets finalized.
    df = _fetch(ticker, start=last)
    rows = _bars_from_dataframe(ticker, df)
    n = _upsert_bars(session, rows)
    _touch_meta(session, ticker)
    session.commit()
    new_last = last_cached_date(session, ticker)
    log.info("refresh %s: upserted %d bars (from %s)", ticker, n, last)
    return {"ticker": ticker, "mode": "incremental", "bars_upserted": n,
            "last_date": new_last.isoformat() if new_last else None}


def search_symbols(query: str, limit: int = 10) -> list[dict]:
    """Search Yahoo Finance for symbols matching the query."""
    query = query.strip()
    if not query:
        return []
    try:
        results = yf.Search(query, max_results=limit)
        quotes = results.quotes or []
    except Exception as exc:  # network / parsing issues -> empty result, logged
        log.warning("symbol search failed for %r: %s", query, exc)
        return []
    out = []
    for q in quotes:
        symbol = q.get("symbol")
        if not symbol:
            continue
        out.append(
            {
                "symbol": symbol,
                "name": q.get("shortname") or q.get("longname") or "",
                "exchange": q.get("exchDisp") or q.get("exchange") or "",
                "type": q.get("quoteType") or q.get("typeDisp") or "",
            }
        )
    return out[:limit]
