# SIGNALDESK

Local-first, single-user algorithmic trading signal tool. Dark terminal
dashboard (React + Vite) over a FastAPI + SQLite backend with Yahoo Finance
daily data.

**Educational tool, not investment advice.**

```
signal-desk/
├── backend/          Python 3.11+ · FastAPI · SQLAlchemy/SQLite · yfinance
│   ├── signals.py    pure signal engine (SMA/RSI/MACD/momentum → weighted score)
│   ├── signals.yaml  tunable weights & thresholds (hot-reloaded, no restart)
│   ├── backtest.py   walk-forward backtester (no lookahead, 10 bps costs)
│   └── tests/        known-answer + causality + accounting tests
└── frontend/         React + Vite port of the signal-desk terminal UI
```

## Run it

Two terminals.

**Backend** (Python 3.11+):

```powershell
cd backend
python -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend** (Node 18+):

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` to the backend
on port 8000, so no CORS or env config is needed.

First use: type a ticker in the search box (any Yahoo Finance symbol — `AAPL`,
`D05.SI`, `BTC-USD`, `^GSPC`…), click a result. The backend pulls 2 years of
daily OHLCV into SQLite on first sight of a ticker; subsequent loads are served
from cache. `⟳ Refresh` pulls only the missing dates. `☆ Watch` persists the
ticker to your watchlist.

## Tests

```powershell
cd backend
python -m pytest
```

Covers:
- **Known-answer indicator tests** — RSI verified against a hand-computed
  Wilder series (arithmetic in the comments) plus a differential test against
  an independent reference implementation; EMA against the pandas
  `ewm(adjust=False)` convention; hand-computed MACD/SMA/momentum cases.
- **Causality tests** — every indicator value at bar *i* is proven identical
  when computed on the full series vs. only bars `0..i`. This is the property
  the backtester's no-lookahead claim rests on.
- **Backtest accounting** — a scripted-signal scenario with every dollar
  (fees, round-trip P&L, buy-and-hold benchmark, drawdown) verified by hand,
  plus a test that rewrites the future and asserts past trades don't change.
- **API tests** — full trade cycle, watchlist, refresh and backtest endpoints
  against a stubbed Yahoo fetch (suite runs offline, uses a throwaway DB).

## Tuning signals

Edit `backend/signals.yaml` — weights, RSI/momentum thresholds, BUY/SELL score
cutoffs, indicator periods, backtest costs. The file is hot-reloaded on the
next request (mtime check); no restart needed. Missing keys fall back to
built-in defaults.

Scoring rules (defaults):

| Component | Bullish | Bearish | Weight |
|---|---|---|---|
| Trend | SMA20 > SMA50 | SMA20 ≤ SMA50 | ±1.0 |
| RSI 14 | < 30 (oversold) | > 70 (overbought) | ±1.5 |
| MACD 12/26/9 | histogram flips + today | flips − today | ±1.5 (fresh cross) / ±0.5 (sign only) |
| Momentum 10d | > +4% | < −4% | ±0.5 |
| Bollinger 20/2σ | %B < 0.05 (at lower band) | %B > 0.95 (at upper band) | ±1.0 |
| Stochastic 14,3 | %D < 20 | %D > 80 | ±0.75 |
| OBV vs SMA20 | above (accumulation) | below (distribution) | ±0.5 |

Score ≥ 1.5 → **BUY** · score ≤ −1.5 → **SELL** · else **HOLD**.
Confidence = min(|score| / 4, 1). Max |score| with defaults is 6.75 — if you
add weight, consider raising `buy_score` / `sell_score` to keep signals rare.

Stochastic uses daily highs/lows and OBV uses volume; both sit out (neutral,
zero weight) if a series lacks that data.

## Backtest methodology

- Long-only, all-in/all-out; decisions on each close, **fills at the next
  day's open** (deciding and filling on the same close would be lookahead).
- Indicators are causal filters, precomputed once — prefix-stability is
  asserted by tests, so no future data leaks into any decision.
- 10 bps transaction cost per fill (configurable), applied to the buy-and-hold
  benchmark's entry too.
- Warmup: scoring starts once all indicators are reliable (50 bars with
  default periods — SMA50 dominates); both strategy and benchmark start from
  the same date with the same capital.
- Reports total return, max drawdown, win rate over closed round trips,
  fills, and equity curves vs. buy-and-hold.

## API quick reference

| Endpoint | Purpose |
|---|---|
| `GET /api/search?q=` | Yahoo symbol search |
| `GET/POST/DELETE /api/watchlist[…]` | persisted watchlist |
| `GET /api/tickers/{t}/prices?days=` | cached OHLCV + SMA overlays |
| `POST /api/tickers/{t}/refresh` | pull missing dates only |
| `GET /api/tickers/{t}/signal` | action, score, confidence, reasons |
| `GET /api/tickers/{t}/backtest` | strategy vs buy-and-hold report |
| `GET /api/quotes?tickers=A,B` | batch price/signal snapshots |
| `GET /api/portfolio` · `POST /api/portfolio/trade` | paper account |
| `GET /api/portfolio/trades` · `POST /api/portfolio/reset` | history / reset |
| `GET /api/config` | current signals.yaml values |

Interactive docs at http://localhost:8000/docs.

## Notes

- All timestamps are timezone-aware and stored as UTC ISO-8601 (naive
  datetimes are rejected at the storage layer). Daily bars are keyed by the
  exchange-local trading date, as is standard for EOD data.
- Prices are split/dividend-adjusted (yfinance `auto_adjust=True`).
- The SQLite file lives at `backend/signaldesk.db` (override with the
  `SIGNALDESK_DB` env var). Delete it to start fresh.
- Paper trades fill at the latest cached close with no fee; the 10 bps cost
  model applies to backtests.
