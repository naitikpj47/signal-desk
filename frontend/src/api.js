// Thin API client. In dev, Vite proxies /api to the FastAPI backend.
const BASE = import.meta.env.VITE_API_BASE || "";

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res.json();
}

const get = (path) => request(path);
const post = (path, body) => request(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
const del = (path) => request(path, { method: "DELETE" });

export const api = {
  health: () => get("/api/health"),
  config: () => get("/api/config"),
  search: (q) => get(`/api/search?q=${encodeURIComponent(q)}`),
  watchlist: () => get("/api/watchlist"),
  watchlistAdd: (ticker, name = "") => post("/api/watchlist", { ticker, name }),
  watchlistRemove: (ticker) => del(`/api/watchlist/${encodeURIComponent(ticker)}`),
  prices: (ticker, days = 240) => get(`/api/tickers/${encodeURIComponent(ticker)}/prices?days=${days}`),
  refresh: (ticker) => post(`/api/tickers/${encodeURIComponent(ticker)}/refresh`),
  signal: (ticker) => get(`/api/tickers/${encodeURIComponent(ticker)}/signal`),
  quotes: (tickers) => get(`/api/quotes?tickers=${encodeURIComponent(tickers.join(","))}`),
  backtest: (ticker) => get(`/api/tickers/${encodeURIComponent(ticker)}/backtest`),
  portfolio: () => get("/api/portfolio"),
  trades: () => get("/api/portfolio/trades"),
  trade: (ticker, side, qty) => post("/api/portfolio/trade", { ticker, side, qty }),
  reset: () => post("/api/portfolio/reset"),
};
