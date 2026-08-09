"""API tests against a stubbed Yahoo fetch — fully offline.

The stub replaces market_data._fetch, so the real caching/upsert path in
ensure_history/refresh_history is exercised too.
"""
import math

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import market_data
from main import app


def fake_frame(n=120, base=100.0, seed=1):
    """Deterministic daily OHLCV frame shaped like yfinance history()."""
    idx = pd.date_range("2024-01-02", periods=n, freq="B", tz="America/New_York")
    closes = []
    v = base
    for i in range(n):
        v = max(v * (1 + math.sin((i + seed) * 12.9898) * 0.02), 1.0)
        closes.append(v)
    return pd.DataFrame(
        {
            "Open": [c * 0.995 for c in closes],
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
            "Volume": [1_000_000 + i for i in range(n)],
        },
        index=idx,
    )


@pytest.fixture(autouse=True)
def stub_yahoo(monkeypatch):
    monkeypatch.setattr(market_data, "_fetch", lambda ticker, start=None: fake_frame())
    monkeypatch.setattr(
        market_data, "search_symbols",
        lambda q, limit=10: [{"symbol": "FAKE", "name": "Fake Corp", "exchange": "TEST", "type": "EQUITY"}],
    )


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestHealthAndConfig:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        # timestamp must be timezone-aware UTC
        assert body["time"].endswith("+00:00")

    def test_config_reflects_yaml(self, client):
        r = client.get("/api/config")
        assert r.status_code == 200
        body = r.json()
        assert body["sma_fast"] == 20
        assert body["w_rsi"] == 1.5
        assert body["backtest"]["fee_bps"] == 10


class TestSearchAndWatchlist:
    def test_search(self, client):
        r = client.get("/api/search", params={"q": "fake"})
        assert r.status_code == 200
        assert r.json()[0]["symbol"] == "FAKE"

    def test_watchlist_roundtrip(self, client):
        r = client.post("/api/watchlist", json={"ticker": "wl1", "name": "Watch One"})
        assert r.status_code == 201
        assert r.json()["ticker"] == "WL1"  # normalized to uppercase

        tickers = [w["ticker"] for w in client.get("/api/watchlist").json()]
        assert "WL1" in tickers

        assert client.delete("/api/watchlist/WL1").status_code == 200
        tickers = [w["ticker"] for w in client.get("/api/watchlist").json()]
        assert "WL1" not in tickers

    def test_watchlist_remove_missing_404(self, client):
        assert client.delete("/api/watchlist/NOPE_X").status_code == 404

    def test_watchlist_add_is_idempotent(self, client):
        for _ in range(2):
            r = client.post("/api/watchlist", json={"ticker": "WL2"})
            assert r.status_code == 201
        tickers = [w["ticker"] for w in client.get("/api/watchlist").json()]
        assert tickers.count("WL2") == 1


class TestPricesAndSignals:
    def test_prices_shape(self, client):
        r = client.get("/api/tickers/PX1/prices", params={"days": 60})
        assert r.status_code == 200
        body = r.json()
        n = len(body["dates"])
        assert n == 60
        for key in ("open", "high", "low", "close", "volume", "sma_fast", "sma_slow",
                    "bb_upper", "bb_lower"):
            assert len(body[key]) == n
        # Overlays sliced from full history: no None gap at the window start
        assert body["sma_fast"][0] is not None
        assert body["sma_slow"][0] is not None
        assert body["bb_upper"][0] is not None
        assert body["bb_lower"][0] is not None

    def test_signal_shape(self, client):
        r = client.get("/api/tickers/SIG1/signal")
        assert r.status_code == 200
        body = r.json()
        assert body["action"] in ("BUY", "SELL", "HOLD")
        assert 0 <= body["confidence"] <= 1
        assert {x["key"] for x in body["reasons"]} == {
            "Trend", "RSI", "MACD", "Momentum", "Bollinger", "Stochastic", "OBV"
        }
        # Full OHLCV is passed server-side, so nothing should be unavailable.
        assert not any("unavailable" in x["detail"] for x in body["reasons"])

    def test_quotes_batch(self, client):
        r = client.get("/api/quotes", params={"tickers": "Q1,Q2,Q1"})
        assert r.status_code == 200
        body = r.json()
        assert [q["ticker"] for q in body] == ["Q1", "Q2"]  # dedup preserves order

    def test_refresh_up_to_date_and_incremental_modes(self, client):
        client.get("/api/tickers/RF1/prices")  # seed cache (bars end in the past)
        r = client.post("/api/tickers/RF1/refresh")
        assert r.status_code == 200
        # Fake data ends 2024 — refresh refetches from the last cached date.
        assert r.json()["mode"] in ("incremental", "up_to_date")

    def test_backtest_endpoint(self, client):
        r = client.get("/api/tickers/BT1/backtest")
        assert r.status_code == 200
        body = r.json()
        assert body["ticker"] == "BT1"
        for key in ("total_return_pct", "max_drawdown_pct", "win_rate_pct"):
            assert key in body["strategy"]
        assert "total_return_pct" in body["buy_hold"]
        assert len(body["equity_curve"]) == body["bars_tested"]


class TestPortfolio:
    def test_full_trade_cycle(self, client):
        assert client.post("/api/portfolio/reset").status_code == 200

        last = client.get("/api/tickers/PT1/signal").json()["close"]

        r = client.post("/api/portfolio/trade", json={"ticker": "PT1", "side": "buy", "qty": 10})
        assert r.status_code == 200
        trade = r.json()
        assert trade["side"] == "BUY"
        assert trade["price"] == pytest.approx(last)
        assert trade["notional"] == pytest.approx(10 * last)

        p = client.get("/api/portfolio").json()
        assert p["cash"] == pytest.approx(100_000 - 10 * last)
        pos = next(x for x in p["positions"] if x["ticker"] == "PT1")
        assert pos["qty"] == 10
        assert pos["avg_cost"] == pytest.approx(last)
        assert pos["unrealized_pnl"] == pytest.approx(0.0, abs=1e-6)
        assert p["equity"] == pytest.approx(100_000)

        r = client.post("/api/portfolio/trade", json={"ticker": "PT1", "side": "sell", "qty": 4})
        assert r.status_code == 200
        assert r.json()["realized_pnl"] == pytest.approx(0.0, abs=1e-6)

        p = client.get("/api/portfolio").json()
        pos = next(x for x in p["positions"] if x["ticker"] == "PT1")
        assert pos["qty"] == 6

        history = client.get("/api/portfolio/trades").json()
        assert history[0]["side"] == "SELL"   # newest first
        assert history[1]["side"] == "BUY"
        assert history[0]["executed_at"].endswith("+00:00") or "Z" in history[0]["executed_at"]

    def test_oversell_rejected(self, client):
        client.post("/api/portfolio/reset")
        client.post("/api/portfolio/trade", json={"ticker": "PT2", "side": "buy", "qty": 1})
        r = client.post("/api/portfolio/trade", json={"ticker": "PT2", "side": "sell", "qty": 5})
        assert r.status_code == 400
        assert "insufficient shares" in r.json()["detail"]

    def test_overspend_rejected(self, client):
        client.post("/api/portfolio/reset")
        r = client.post("/api/portfolio/trade", json={"ticker": "PT3", "side": "buy", "qty": 10_000_000})
        assert r.status_code == 400
        assert "insufficient cash" in r.json()["detail"]

    def test_bad_qty_rejected_by_validation(self, client):
        r = client.post("/api/portfolio/trade", json={"ticker": "PT4", "side": "buy", "qty": -5})
        assert r.status_code == 422

    def test_reset(self, client):
        client.post("/api/portfolio/trade", json={"ticker": "PT5", "side": "buy", "qty": 1})
        r = client.post("/api/portfolio/reset")
        assert r.json()["cash"] == 100_000
        p = client.get("/api/portfolio").json()
        assert p["positions"] == []
        assert client.get("/api/portfolio/trades").json() == []
