import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import { fmt, signClass } from "./theme.js";
import SearchBar from "./components/SearchBar.jsx";
import TickerStrip from "./components/TickerStrip.jsx";
import SignalPanel from "./components/SignalPanel.jsx";
import WatchlistTable from "./components/WatchlistTable.jsx";
import PortfolioTab from "./components/PortfolioTab.jsx";
import BacktestTab from "./components/BacktestTab.jsx";

export default function App() {
  const [watchlist, setWatchlist] = useState([]); // [{ticker, name}]
  const [selected, setSelected] = useState(null);
  const [quotes, setQuotes] = useState({}); // ticker -> quote
  const [prices, setPrices] = useState(null);
  const [signal, setSignal] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [trades, setTrades] = useState([]);
  const [tab, setTab] = useState("signals");
  const [qty, setQty] = useState(10);
  const [backtests, setBacktests] = useState({}); // ticker -> result
  const [btRunning, setBtRunning] = useState(false);
  const [btError, setBtError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [offline, setOffline] = useState(false);
  const selectedRef = useRef(null);
  selectedRef.current = selected;

  const watchTickers = useMemo(() => watchlist.map((w) => w.ticker), [watchlist]);
  const positionTickers = useMemo(
    () => (portfolio ? portfolio.positions.map((p) => p.ticker) : []),
    [portfolio]
  );
  const stripTickers = useMemo(() => {
    const set = [...watchTickers];
    for (const t of positionTickers) if (!set.includes(t)) set.push(t);
    if (selected && !set.includes(selected)) set.push(selected);
    return set;
  }, [watchTickers, positionTickers, selected]);

  const showError = useCallback((e) => {
    setError(String(e.message || e));
    setTimeout(() => setError(null), 6000);
  }, []);

  const loadPortfolio = useCallback(async () => {
    try {
      const [p, t] = await Promise.all([api.portfolio(), api.trades()]);
      setPortfolio(p);
      setTrades(t);
    } catch (e) {
      showError(e);
    }
  }, [showError]);

  const loadQuotes = useCallback(async (tickers) => {
    if (tickers.length === 0) return;
    try {
      const qs = await api.quotes(tickers);
      setQuotes((prev) => {
        const next = { ...prev };
        for (const q of qs) next[q.ticker] = q;
        return next;
      });
    } catch {
      /* quotes are cosmetic; selected-panel errors surface elsewhere */
    }
  }, []);

  const selectTicker = useCallback(
    async (ticker) => {
      setSelected(ticker);
      setTab("signals");
      setPrices(null);
      setSignal(null);
      try {
        const [p, s] = await Promise.all([api.prices(ticker), api.signal(ticker)]);
        // Ignore stale responses if the user clicked away mid-flight.
        if (selectedRef.current !== ticker) return;
        setPrices(p);
        setSignal(s);
        loadQuotes([ticker]);
      } catch (e) {
        if (selectedRef.current === ticker) showError(e);
      }
    },
    [loadQuotes, showError]
  );

  // Initial load
  useEffect(() => {
    (async () => {
      try {
        await api.health();
      } catch {
        setOffline(true);
        return;
      }
      try {
        const wl = await api.watchlist();
        setWatchlist(wl);
        loadPortfolio();
        const tickers = wl.map((w) => w.ticker);
        loadQuotes(tickers);
        if (tickers.length > 0) selectTicker(tickers[0]);
      } catch (e) {
        showError(e);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep quotes warm for position tickers that aren't watched.
  useEffect(() => {
    const missing = positionTickers.filter((t) => !quotes[t]);
    if (missing.length) loadQuotes(missing);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionTickers]);

  const toggleWatch = async () => {
    if (!selected) return;
    try {
      if (watchTickers.includes(selected)) {
        await api.watchlistRemove(selected);
      } else {
        await api.watchlistAdd(selected, prices?.name || "");
      }
      setWatchlist(await api.watchlist());
    } catch (e) {
      showError(e);
    }
  };

  const pickSearchResult = async (r) => {
    await selectTicker(r.symbol);
  };

  const doTrade = async (side, n) => {
    if (!selected || n <= 0) return;
    try {
      await api.trade(selected, side, n);
      await loadPortfolio();
    } catch (e) {
      showError(e);
    }
  };

  const doRefresh = async () => {
    if (!selected) return;
    setRefreshing(true);
    try {
      await api.refresh(selected);
      const [p, s] = await Promise.all([api.prices(selected), api.signal(selected)]);
      setPrices(p);
      setSignal(s);
      loadQuotes([selected]);
    } catch (e) {
      showError(e);
    } finally {
      setRefreshing(false);
    }
  };

  const runBacktest = async () => {
    if (!selected) return;
    setBtRunning(true);
    setBtError(null);
    try {
      const r = await api.backtest(selected);
      setBacktests((b) => ({ ...b, [selected]: r }));
    } catch (e) {
      setBtError(String(e.message || e));
    } finally {
      setBtRunning(false);
    }
  };

  const doReset = async () => {
    try {
      await api.reset();
      await loadPortfolio();
    } catch (e) {
      showError(e);
    }
  };

  const hasPosition = portfolio?.positions.some((p) => p.ticker === selected);
  const totalPnL = portfolio ? portfolio.unrealized_pnl : 0;

  const tabs = [
    ["signals", "Signals", null],
    ["portfolio", "Portfolio", portfolio ? portfolio.positions.length : 0],
    ["backtest", "Backtest", null],
  ];

  return (
    <div className="shell">
      {/* Header */}
      <header className="header">
        <div className="brand">
          <span className="brand-mark">◮</span>
          SIGNAL<em>DESK</em>
        </div>
        <div className="status">
          <span className={`status-dot${offline ? " err" : ""}`} />
          {offline ? "BACKEND OFFLINE" : "PAPER · YAHOO DAILY"}
        </div>
      </header>

      {offline ? (
        <div className="card">
          <div className="empty">
            Backend not reachable.
            <div className="hint">cd backend · uvicorn main:app --port 8000</div>
          </div>
        </div>
      ) : (
        <>
          {/* Account stats + search */}
          <div className="statbar">
            <div className="stat">
              <div className="stat-label">Cash</div>
              <div className="stat-value">${fmt(portfolio?.cash ?? 0)}</div>
            </div>
            <div className="stat">
              <div className="stat-label">Holdings</div>
              <div className="stat-value">${fmt(portfolio?.holdings_value ?? 0)}</div>
            </div>
            <div className="stat">
              <div className="stat-label">Open P&L</div>
              <div className={`stat-value ${signClass(totalPnL)}`}>
                {totalPnL >= 0 ? "+" : ""}${fmt(totalPnL)}
              </div>
            </div>
            <SearchBar onPick={pickSearchResult} />
          </div>

          {error && <div className="banner-error">{error}</div>}

          {/* Tabs */}
          <div className="tabs">
            {tabs.map(([k, label, count]) => (
              <button
                key={k}
                className={`tab${tab === k ? " active" : ""}`}
                onClick={() => setTab(k)}
              >
                {label}
                {count != null && count > 0 && <span className="count">{count}</span>}
              </button>
            ))}
          </div>

          {tab === "signals" && (
            <>
              <TickerStrip
                tickers={stripTickers}
                quotes={quotes}
                watchlist={watchTickers}
                selected={selected}
                onSelect={selectTicker}
              />
              {selected ? (
                <SignalPanel
                  prices={prices}
                  signal={signal}
                  watched={watchTickers.includes(selected)}
                  hasPosition={hasPosition}
                  qty={qty}
                  setQty={setQty}
                  onTrade={doTrade}
                  onToggleWatch={toggleWatch}
                  onRefresh={doRefresh}
                  refreshing={refreshing}
                />
              ) : (
                <div className="card">
                  <div className="empty">
                    Search for any Yahoo Finance ticker to get started.
                    <div className="hint">try AAPL · NVDA · D05.SI · BTC-USD</div>
                  </div>
                </div>
              )}
              <WatchlistTable watchlist={watchTickers} quotes={quotes} onSelect={selectTicker} />
            </>
          )}

          {tab === "portfolio" && (
            <PortfolioTab
              portfolio={portfolio}
              trades={trades}
              onSelect={selectTicker}
              onReset={doReset}
            />
          )}

          {tab === "backtest" && (
            <BacktestTab
              ticker={selected}
              result={selected ? backtests[selected] : null}
              running={btRunning}
              error={btError}
              onRun={runBacktest}
            />
          )}
        </>
      )}

      <div className="footnote">
        Signals blend SMA 20/50 trend, RSI 14, MACD 12/26/9, 10-day momentum, Bollinger %B,
        Stochastic 14·3 and OBV into a weighted score — tune weights in{" "}
        <code>backend/signals.yaml</code>. Educational tool, not investment advice.
      </div>
    </div>
  );
}
