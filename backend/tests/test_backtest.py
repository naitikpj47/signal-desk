"""Backtester tests: hand-computed accounting, cost model, and no-lookahead.

The accounting tests replace the scorer with a deterministic stub so every
dollar amount can be verified by hand. The no-lookahead test perturbs the
future and asserts the past doesn't change.
"""
import math
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import backtest as bt_mod
from backtest import InsufficientData, max_drawdown, run_backtest
from signals import SignalConfig


def approx(x, rel=1e-9, abs_=1e-9):
    return pytest.approx(x, rel=rel, abs=abs_)


def make_dates(n, start=date(2024, 1, 1)):
    return [start + timedelta(days=k) for k in range(n)]


# Tiny config => warmup_bars() = max(3-1, 2, 2, 3+2, 3-1, 2+2-2, 2-1) + 1 = 6
TINY = SignalConfig(sma_fast=2, sma_slow=3, rsi_period=2,
                    macd_fast=2, macd_slow=3, macd_signal=2, momentum_days=2,
                    bb_period=3, stoch_k=2, stoch_d=2, obv_sma=2)
I0 = TINY.warmup_bars()


def scripted_scorer(decisions: dict):
    """A score_at stub that returns scripted actions by bar index."""
    def fake(ind, i, cfg):
        return SimpleNamespace(action=decisions.get(i, "HOLD"))
    return fake


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------

class TestMaxDrawdown:
    def test_known_answer(self):
        # peak 120 -> trough 90: (120 - 90) / 120 = 25%
        assert max_drawdown([100, 120, 90, 130]) == approx(0.25)

    def test_monotonic_up_is_zero(self):
        assert max_drawdown([1, 2, 3, 4, 5]) == approx(0.0)

    def test_full_wipeout(self):
        assert max_drawdown([100, 0]) == approx(1.0)

    def test_later_deeper_trough_wins(self):
        # dd1 = (100-80)/100 = 20%; dd2 = (110-70)/110 = 36.36%
        assert max_drawdown([100, 80, 110, 70]) == approx(40 / 110)


# ---------------------------------------------------------------------------
# Hand-computed accounting (scripted signals)
# ---------------------------------------------------------------------------

class TestAccounting:
    """One full round trip, every number verified by hand.

    warmup I0 = 6. Decision BUY on close[6] fills at open[7] = 50.
    Decision SELL on close[8] fills at open[9] = 60. fee = 10 bps.

      qty       = 10000 / (50 * 1.001)          = 199.8001998001998
      sell gross= qty * 60                       = 11988.011988011987
      proceeds  = gross * (1 - 0.001)            = 11976.023976023975
      round-trip P&L                             = 1976.023976...
      buy-hold: same entry, marked at close[-1]=55 -> 199.8002 * 55 = 10989.010989
    """

    OPENS = [10, 10, 10, 10, 10, 10, 10, 50, 55, 60, 58, 57]
    CLOSES = [10, 10, 10, 10, 10, 10, 10, 52, 56, 61, 59, 55]

    def run(self, monkeypatch, decisions, fee_bps=10.0):
        monkeypatch.setattr(bt_mod, "score_at", scripted_scorer(decisions))
        return run_backtest(
            make_dates(12), [float(x) for x in self.OPENS],
            [float(x) for x in self.CLOSES],
            cfg=TINY, initial_cash=10_000.0, fee_bps=fee_bps,
        )

    def test_round_trip_numbers(self, monkeypatch):
        res = self.run(monkeypatch, {6: "BUY", 8: "SELL"})
        qty = 10_000 / (50 * 1.001)
        proceeds = qty * 60 * 0.999

        assert res["strategy"]["num_fills"] == 2
        assert res["strategy"]["round_trips"] == 1
        assert res["strategy"]["win_rate_pct"] == approx(100.0)
        assert res["strategy"]["final_equity"] == approx(proceeds)
        assert res["strategy"]["total_return_pct"] == approx((proceeds / 10_000 - 1) * 100)
        assert res["strategy"]["position_open_at_end"] is False

        buy, sell = res["trades"]
        assert buy.side == "BUY" and sell.side == "SELL"
        # Fills happen at the NEXT day's OPEN, not the decision day's close.
        assert buy.date == make_dates(12)[7] and buy.price == approx(50.0)
        assert sell.date == make_dates(12)[9] and sell.price == approx(60.0)
        assert buy.qty == approx(qty)
        assert buy.fee == approx(qty * 50 * 0.001)
        assert sell.fee == approx(qty * 60 * 0.001)

    def test_buy_hold_benchmark(self, monkeypatch):
        res = self.run(monkeypatch, {6: "BUY", 8: "SELL"})
        bh_qty = 10_000 / (50 * 1.001)  # entry at open[I0+1] = 50, same fee
        assert res["buy_hold"]["final_equity"] == approx(bh_qty * 55)
        assert res["buy_hold"]["total_return_pct"] == approx((bh_qty * 55 / 10_000 - 1) * 100)
        # bh equity: [10000, *52, *56, *61, *59, *55]; peak at *61, end at *55
        assert res["buy_hold"]["max_drawdown_pct"] == approx((61 - 55) / 61 * 100)

    def test_excess_return(self, monkeypatch):
        res = self.run(monkeypatch, {6: "BUY", 8: "SELL"})
        qty = 10_000 / (50 * 1.001)
        expected = (qty * 60 * 0.999 - qty * 55) / 10_000 * 100
        assert res["excess_return_pct"] == approx(expected)

    def test_zero_fee(self, monkeypatch):
        res = self.run(monkeypatch, {6: "BUY", 8: "SELL"}, fee_bps=0.0)
        qty = 10_000 / 50
        assert res["strategy"]["final_equity"] == approx(qty * 60)

    def test_equity_curve_shape_and_anchor(self, monkeypatch):
        res = self.run(monkeypatch, {6: "BUY", 8: "SELL"})
        curve = res["equity_curve"]
        assert len(curve) == 12 - I0
        assert curve[0]["date"] == make_dates(12)[I0]
        assert curve[0]["strategy"] == approx(10_000.0)
        assert curve[0]["buy_hold"] == approx(10_000.0)
        # Day of the buy fill: equity marked at that day's close.
        qty = 10_000 / (50 * 1.001)
        assert curve[7 - I0]["strategy"] == approx(qty * 52)

    def test_no_drawdown_in_monotonic_scenario(self, monkeypatch):
        res = self.run(monkeypatch, {6: "BUY", 8: "SELL"})
        assert res["strategy"]["max_drawdown_pct"] == approx(0.0)

    def test_buy_while_long_ignored(self, monkeypatch):
        res = self.run(monkeypatch, {6: "BUY", 7: "BUY", 8: "BUY"})
        assert res["strategy"]["num_fills"] == 1
        assert res["strategy"]["position_open_at_end"] is True
        assert res["strategy"]["round_trips"] == 0
        assert res["strategy"]["win_rate_pct"] is None

    def test_sell_while_flat_ignored(self, monkeypatch):
        res = self.run(monkeypatch, {6: "SELL", 8: "SELL"})
        assert res["strategy"]["num_fills"] == 0
        assert res["strategy"]["final_equity"] == approx(10_000.0)

    def test_open_position_marked_to_market(self, monkeypatch):
        res = self.run(monkeypatch, {6: "BUY"})  # never sells
        qty = 10_000 / (50 * 1.001)
        assert res["strategy"]["position_open_at_end"] is True
        assert res["strategy"]["final_equity"] == approx(qty * 55)  # last close

    def test_decision_on_last_bar_cannot_fill(self, monkeypatch):
        # A signal on the final bar has no next open to trade at.
        res = self.run(monkeypatch, {11: "BUY"})
        assert res["strategy"]["num_fills"] == 0

    def test_losing_round_trip_win_rate_zero(self, monkeypatch):
        opens = [10.0] * 7 + [50.0, 45.0, 40.0, 39.0, 38.0]
        closes = [10.0] * 7 + [49.0, 44.0, 41.0, 39.0, 38.0]
        monkeypatch.setattr(bt_mod, "score_at", scripted_scorer({6: "BUY", 8: "SELL"}))
        res = run_backtest(make_dates(12), opens, closes, cfg=TINY,
                           initial_cash=10_000.0, fee_bps=10.0)
        assert res["strategy"]["round_trips"] == 1
        assert res["strategy"]["win_rate_pct"] == approx(0.0)


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

class TestGuards:
    def test_insufficient_data_raises(self):
        n = SignalConfig().warmup_bars() + 1  # one short of the minimum
        with pytest.raises(InsufficientData):
            run_backtest(make_dates(n), [100.0] * n, [100.0] * n)

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError):
            run_backtest(make_dates(50), [100.0] * 50, [100.0] * 49)


# ---------------------------------------------------------------------------
# No-lookahead: changing the future must not change the past
# ---------------------------------------------------------------------------

def oscillating_series(n=220):
    """Deterministic oscillation that reliably triggers BUY and SELL signals."""
    closes = [100 + 20 * math.sin(i / 8.0) for i in range(n)]
    opens = [closes[0]] + closes[:-1]  # open ~ previous close
    return opens, closes


class TestNoLookahead:
    CUT = 120  # bars up to and including this index are identical in both runs

    def _run_pair(self):
        opens_a, closes_a = oscillating_series()
        opens_b = list(opens_a)
        closes_b = list(closes_a)
        # Violently rewrite the future: crash to near-zero after CUT.
        for k in range(self.CUT + 1, len(closes_b)):
            closes_b[k] = 1.0 + 0.01 * k
            opens_b[k] = 1.0 + 0.01 * k
        dates = make_dates(len(closes_a))
        res_a = run_backtest(dates, opens_a, closes_a)
        res_b = run_backtest(dates, opens_b, closes_b)
        return dates, res_a, res_b

    def test_prefix_trades_identical(self):
        dates, res_a, res_b = self._run_pair()
        cut_date = dates[self.CUT]
        pre_a = [t for t in res_a["trades"] if t.date <= cut_date]
        pre_b = [t for t in res_b["trades"] if t.date <= cut_date]
        # The scenario must actually trade before the cut, or this test is vacuous.
        assert len(pre_a) >= 2, "oscillating series should trade in the prefix"
        assert len(pre_a) == len(pre_b)
        for ta, tb in zip(pre_a, pre_b):
            assert ta.date == tb.date
            assert ta.side == tb.side
            assert ta.price == approx(tb.price)
            assert ta.qty == approx(tb.qty)

    def test_prefix_equity_identical(self):
        dates, res_a, res_b = self._run_pair()
        cut_date = dates[self.CUT]
        eq_a = [p for p in res_a["equity_curve"] if p["date"] <= cut_date]
        eq_b = [p for p in res_b["equity_curve"] if p["date"] <= cut_date]
        assert len(eq_a) == len(eq_b) > 0
        for pa, pb in zip(eq_a, eq_b):
            assert pa["strategy"] == approx(pb["strategy"])


# ---------------------------------------------------------------------------
# Integration: real scorer over a synthetic walk
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_end_to_end_structure(self):
        opens, closes = oscillating_series(300)
        res = run_backtest(make_dates(300), opens, closes,
                           initial_cash=10_000.0, fee_bps=10.0)
        s = res["strategy"]
        assert res["bars_tested"] == 300 - res["warmup_bars"]
        assert len(res["equity_curve"]) == res["bars_tested"]
        assert s["final_equity"] > 0
        assert 0 <= s["max_drawdown_pct"] <= 100
        assert 0 <= res["buy_hold"]["max_drawdown_pct"] <= 100
        if s["win_rate_pct"] is not None:
            assert 0 <= s["win_rate_pct"] <= 100
        # Fills alternate BUY/SELL starting with BUY (long-only, all-in/out).
        sides = [t.side for t in res["trades"]]
        assert sides == (["BUY", "SELL"] * 150)[: len(sides)]
        # excess return consistency
        assert res["excess_return_pct"] == approx(
            (s["final_equity"] - res["buy_hold"]["final_equity"]) / 10_000 * 100
        )
