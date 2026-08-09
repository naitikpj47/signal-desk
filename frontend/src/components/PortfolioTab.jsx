import SignalChip from "./SignalChip.jsx";
import { fmt, signClass } from "../theme.js";

export default function PortfolioTab({ portfolio, trades, onSelect, onReset }) {
  if (!portfolio) return null;
  const { positions } = portfolio;

  return (
    <>
      <div className="card">
        <div className="section-title">Open positions</div>
        {positions.length === 0 && (
          <div className="empty">
            No positions yet.
            <div className="hint">buy from the Signals tab to build your book</div>
          </div>
        )}
        {positions.map((p) => (
          <div key={p.ticker} className="row" onClick={() => onSelect(p.ticker)}>
            <div className="row-main">
              <span className="row-ticker">{p.ticker}</span>
              <span className="row-sub">
                {fmt(p.qty, p.qty % 1 === 0 ? 0 : 4)} @ ${fmt(p.avg_cost)}
              </span>
            </div>
            <div className="row-side">
              <span className="num">${fmt(p.market_value)}</span>
              <span className={`num ${signClass(p.unrealized_pnl)}`}>
                {p.unrealized_pnl >= 0 ? "+" : ""}${fmt(p.unrealized_pnl)}
                {" "}({p.unrealized_pct >= 0 ? "+" : ""}{p.unrealized_pct.toFixed(2)}%)
              </span>
              {p.action && <SignalChip action={p.action} confidence={p.confidence} />}
            </div>
          </div>
        ))}
        {positions.length > 0 && (
          <div className="summary-line">
            <span>
              Total equity <span style={{ color: "var(--text)" }}>${fmt(portfolio.equity)}</span>
            </span>
            <span>
              Realized P&L{" "}
              <span className={signClass(portfolio.realized_pnl)}>
                {portfolio.realized_pnl >= 0 ? "+" : ""}${fmt(portfolio.realized_pnl)}
              </span>
            </span>
          </div>
        )}
      </div>

      <div className="card">
        <div className="section-title">Trade history</div>
        {trades.length === 0 && <div className="empty">No trades yet.</div>}
        {trades.length > 0 && (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Time (UTC)</th>
                  <th>Side</th>
                  <th>Ticker</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>Notional</th>
                  <th>Realized</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr key={t.id}>
                    <td className="dim">{t.executed_at.slice(0, 16).replace("T", " ")}</td>
                    <td>
                      <span className={`side-tag ${t.side === "BUY" ? "pos" : "neg"}`}>{t.side}</span>
                    </td>
                    <td style={{ fontWeight: 700 }}>{t.ticker}</td>
                    <td>{fmt(t.qty, t.qty % 1 === 0 ? 0 : 4)}</td>
                    <td>${fmt(t.price)}</td>
                    <td>${fmt(t.notional)}</td>
                    <td className={t.realized_pnl == null ? "dim" : signClass(t.realized_pnl)}>
                      {t.realized_pnl == null
                        ? "—"
                        : `${t.realized_pnl >= 0 ? "+" : ""}$${fmt(t.realized_pnl)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {trades.length > 0 && (
          <button className="btn btn-danger-ghost" style={{ marginTop: 14 }} onClick={onReset}>
            Reset account
          </button>
        )}
      </div>
    </>
  );
}
