import Chart from "./Chart.jsx";
import { chart, fmt, signClass } from "../theme.js";

function Metric({ label, value, cls }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${cls ?? ""}`}>{value}</div>
    </div>
  );
}

const pct = (v, signed = true) =>
  v == null ? "—" : `${signed && v >= 0 ? "+" : ""}${v.toFixed(2)}%`;

export default function BacktestTab({ ticker, result, running, error, onRun }) {
  return (
    <div className="card">
      <div className="symbol-head" style={{ marginBottom: result || error ? 16 : 8 }}>
        <div className="section-title" style={{ margin: 0, alignSelf: "center" }}>
          Backtest {ticker ? `· ${ticker}` : ""}
        </div>
        <button className="btn btn-primary" onClick={onRun} disabled={!ticker || running}>
          {running ? "Running…" : "Run backtest"}
        </button>
      </div>

      {error && <div className="banner-error">{error}</div>}

      {!result && !error && (
        <div className="empty">
          Replays the signal rules over the cached 2-year history.
          <div className="hint">
            decisions on each close · fills at next open · 10 bps per fill · vs buy-and-hold
          </div>
        </div>
      )}

      {result && (
        <>
          <div className="metrics">
            <Metric label="Strategy" value={pct(result.strategy.total_return_pct)}
              cls={signClass(result.strategy.total_return_pct)} />
            <Metric label="Buy & hold" value={pct(result.buy_hold.total_return_pct)}
              cls={signClass(result.buy_hold.total_return_pct)} />
            <Metric label="Excess" value={pct(result.excess_return_pct)}
              cls={signClass(result.excess_return_pct)} />
            <Metric label="Max drawdown" value={pct(-result.strategy.max_drawdown_pct, false)} cls="neg" />
            <Metric label="Win rate"
              value={result.strategy.win_rate_pct == null ? "—" : `${result.strategy.win_rate_pct.toFixed(0)}%`} />
            <Metric label="Fills" value={result.strategy.num_fills} />
            <Metric label="Final equity" value={`$${fmt(result.strategy.final_equity)}`} />
          </div>

          <div className="chart-wrap">
            <Chart
              height={180}
              series={[
                { data: result.equity_curve.map((p) => p.buy_hold), color: chart.blue, width: 1.2, opacity: 0.75 },
                { data: result.equity_curve.map((p) => p.strategy), color: chart.amber, width: 1.8, area: true },
              ]}
            />
          </div>
          <div className="chart-meta">
            <div className="legend">
              <span className="legend-item">
                <span className="legend-swatch" style={{ background: "var(--amber)" }} /> Strategy
              </span>
              <span className="legend-item">
                <span className="legend-swatch" style={{ background: "var(--blue)" }} /> Buy & hold
              </span>
            </div>
            <span className="chart-range">
              {result.start_date} → {result.end_date} · {result.bars_tested} bars · {result.fee_bps} bps/fill
            </span>
          </div>

          <div className="summary-line">
            <span>
              {result.strategy.round_trips} closed round trip{result.strategy.round_trips === 1 ? "" : "s"}
            </span>
            {result.strategy.position_open_at_end && <span>position open at end (marked to market)</span>}
            <span>buy&hold max drawdown {pct(-result.buy_hold.max_drawdown_pct, false)}</span>
          </div>

          {result.trades.length > 0 && (
            <div className="table-wrap" style={{ marginTop: 14, maxHeight: 230, overflowY: "auto" }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Side</th>
                    <th>Price</th>
                    <th>Qty</th>
                    <th>Fee</th>
                    <th>Equity after</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={i}>
                      <td className="dim">{t.date}</td>
                      <td>
                        <span className={`side-tag ${t.side === "BUY" ? "pos" : "neg"}`}>{t.side}</span>
                      </td>
                      <td>${fmt(t.price)}</td>
                      <td>{fmt(t.qty, 4)}</td>
                      <td className="dim">${fmt(t.fee)}</td>
                      <td>${fmt(t.equity_after)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
