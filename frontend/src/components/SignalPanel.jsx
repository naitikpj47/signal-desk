import { useState } from "react";
import Chart from "./Chart.jsx";
import SignalChip from "./SignalChip.jsx";
import { chart, fmt, signClass } from "../theme.js";

export default function SignalPanel({
  prices,
  signal,
  watched,
  hasPosition,
  qty,
  setQty,
  onTrade,
  onToggleWatch,
  onRefresh,
  refreshing,
}) {
  const [trading, setTrading] = useState(false);
  if (!prices || !signal) {
    return (
      <div className="card">
        <div className="loading-panel">loading price data…</div>
      </div>
    );
  }

  const up = prices.close[prices.close.length - 1] >= prices.close[0];
  const priceColor = up ? chart.green : chart.red;
  const trade = async (side) => {
    setTrading(true);
    try {
      await onTrade(side, qty);
    } finally {
      setTrading(false);
    }
  };

  return (
    <div className="card">
      {/* head */}
      <div className="symbol-head">
        <div className="symbol-title">
          <span className="symbol-ticker">{signal.ticker}</span>
          <span className="symbol-name">{prices.name}</span>
        </div>
        <div className="price-block">
          <span className="price-big">${fmt(signal.close)}</span>
          {signal.change_pct != null && (
            <span className={`delta ${signClass(signal.change_pct)}`}>
              {signal.change_pct >= 0 ? "+" : ""}
              {signal.change_pct.toFixed(2)}%
            </span>
          )}
          <SignalChip action={signal.action} confidence={signal.confidence} />
        </div>
      </div>

      {/* chart */}
      <div className="chart-wrap">
        <Chart
          series={[
            { data: prices.bb_upper ?? [], color: chart.dim, width: 0.8, dash: "3 4", opacity: 0.55 },
            { data: prices.bb_lower ?? [], color: chart.dim, width: 0.8, dash: "3 4", opacity: 0.55 },
            { data: prices.sma_slow, color: chart.blue, width: 1.1, opacity: 0.85 },
            { data: prices.sma_fast, color: chart.amber, width: 1.1, opacity: 0.9 },
            { data: prices.close, color: priceColor, width: 1.8, area: true },
          ]}
        />
      </div>
      <div className="chart-meta">
        <div className="legend">
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: priceColor }} /> Price
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: "var(--amber)" }} /> SMA 20
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: "var(--blue)" }} /> SMA 50
          </span>
          <span className="legend-item" style={{ color: "var(--text-3)" }}>
            <span className="legend-swatch dashed" /> Bollinger 20·2σ
          </span>
        </div>
        <span className="chart-range">
          {prices.dates[0]} → {signal.asof}
        </span>
      </div>

      {/* reasons */}
      <div className="reasons">
        {signal.reasons.map((r, i) => (
          <div key={i} className="reason">
            <span className={`reason-ind ${r.direction > 0 ? "up" : r.direction < 0 ? "down" : "flat"}`}>
              {r.direction > 0 ? "▲" : r.direction < 0 ? "▼" : "—"}
            </span>
            <span className="reason-key">{r.key}</span>
            <span className="reason-text" title={r.detail}>{r.detail}</span>
          </div>
        ))}
        <div className="score-line">
          composite score {signal.score >= 0 ? "+" : ""}
          {signal.score.toFixed(2)} · as of {signal.asof}
        </div>
      </div>

      {/* trade bar */}
      <div className="trade-bar">
        <input
          type="number"
          min="1"
          className="qty-input"
          value={qty}
          onChange={(e) => setQty(parseInt(e.target.value) || 0)}
        />
        <button className="btn btn-buy" disabled={trading} onClick={() => trade("buy")}>
          Buy
        </button>
        <button
          className="btn btn-sell"
          disabled={!hasPosition || trading}
          onClick={() => trade("sell")}
        >
          Sell
        </button>
        <button
          className={`btn btn-ghost${watched ? " watching" : ""}`}
          onClick={onToggleWatch}
        >
          {watched ? "★ Watching" : "☆ Watch"}
        </button>
        <button className="btn btn-ghost" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "⟳ Refresh"}
        </button>
        <span className="est">≈ ${fmt(signal.close * qty)}</span>
      </div>
    </div>
  );
}
