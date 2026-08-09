import SignalChip from "./SignalChip.jsx";
import { fmt } from "../theme.js";

export default function WatchlistTable({ watchlist, quotes, onSelect }) {
  return (
    <div className="card">
      <div className="section-title">Watchlist</div>
      {watchlist.length === 0 && (
        <div className="empty">
          Star a symbol to track its signal here.
          <div className="hint">search above · then ☆ Watch</div>
        </div>
      )}
      {watchlist.map((t) => {
        const q = quotes[t];
        return (
          <div key={t} className="row" onClick={() => onSelect(t)}>
            <div className="row-main">
              <span className="row-ticker">{t}</span>
              {q ? (
                q.error ? (
                  <span className="row-sub neg" title={q.error}>data unavailable</span>
                ) : (
                  <>
                    <span className="row-sub">${fmt(q.last)}</span>
                    {q.rsi != null && <span className="row-sub">RSI {q.rsi.toFixed(0)}</span>}
                  </>
                )
              ) : (
                <span className="row-sub">…</span>
              )}
            </div>
            {q && !q.error && <SignalChip action={q.action} confidence={q.confidence} />}
          </div>
        );
      })}
    </div>
  );
}
