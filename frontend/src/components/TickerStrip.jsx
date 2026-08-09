import { fmt, signClass } from "../theme.js";

export default function TickerStrip({ tickers, quotes, watchlist, selected, onSelect }) {
  if (tickers.length === 0) return null;
  return (
    <div className="strip">
      {tickers.map((t) => {
        const q = quotes[t];
        const chg = q?.change_pct;
        return (
          <button
            key={t}
            onClick={() => onSelect(t)}
            className={`chip${selected === t ? " active" : ""}`}
          >
            <div className="chip-symbol">
              {t}
              {watchlist.includes(t) && <span className="chip-star">★</span>}
            </div>
            {q ? (
              q.error ? (
                <div className="chip-err" title={q.error}>no data</div>
              ) : (
                <div className={`chip-change ${signClass(chg ?? 0)}`}>
                  {chg == null ? fmt(q.last) : `${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%`}
                </div>
              )
            ) : (
              <div className="chip-change dim">…</div>
            )}
          </button>
        );
      })}
    </div>
  );
}
