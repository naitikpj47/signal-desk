import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

// Debounced Yahoo Finance symbol search with a results dropdown.
export default function SearchBar({ onPick }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const boxRef = useRef(null);

  useEffect(() => {
    if (q.trim().length < 1) {
      setResults([]);
      setOpen(false);
      return;
    }
    setSearching(true);
    const id = setTimeout(async () => {
      try {
        const r = await api.search(q.trim());
        setResults(r);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => clearTimeout(id);
  }, [q]);

  useEffect(() => {
    const close = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (r) => {
    setQ("");
    setOpen(false);
    setResults([]);
    onPick(r);
  };

  return (
    <div ref={boxRef} className="search">
      <span className="search-icon">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2.4" strokeLinecap="round">
          <circle cx="11" cy="11" r="7" />
          <line x1="21" y1="21" x2="16.5" y2="16.5" />
        </svg>
      </span>
      <input
        className="search-input"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => results.length && setOpen(true)}
        placeholder={searching ? "searching…" : "Search any ticker — AAPL, D05.SI, BTC-USD"}
      />
      {open && results.length > 0 && (
        <div className="search-results">
          {results.map((r) => (
            <div key={r.symbol} className="search-item" onClick={() => pick(r)}>
              <span className="search-item-symbol">{r.symbol}</span>
              <span className="search-item-name">
                {r.name}
                {r.exchange ? ` · ${r.exchange}` : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
