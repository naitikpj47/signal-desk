"""Known-answer and property tests for the pure signal engine.

Every expected value here is either derived by hand (arithmetic shown in
comments) or follows from a mathematical property of the indicator.
"""
import math

import pytest

from signals import (
    IndicatorSet,
    SignalConfig,
    bollinger,
    compute_indicators,
    compute_signal,
    ema,
    macd,
    momentum,
    obv,
    rolling_std,
    rsi,
    score_at,
    sma,
    stochastic,
)


def approx(x, rel=1e-12, abs_=1e-12):
    return pytest.approx(x, rel=rel, abs=abs_)


# ---------------------------------------------------------------------------
# SMA
# ---------------------------------------------------------------------------

class TestSMA:
    def test_known_answer(self):
        # windows of 3 over 1..5: (1+2+3)/3=2, (2+3+4)/3=3, (3+4+5)/3=4
        assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]

    def test_window_of_one_is_identity(self):
        vals = [3.5, 1.25, 7.0]
        assert sma(vals, 1) == vals

    def test_shorter_series_than_window_all_none(self):
        assert sma([10.0, 11.0], 5) == [None, None]

    def test_constant_series(self):
        assert sma([7.0] * 6, 4) == [None, None, None, 7.0, 7.0, 7.0]

    def test_invalid_period(self):
        with pytest.raises(ValueError):
            sma([1.0], 0)


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------

class TestEMA:
    def test_known_answer_hand_computed(self):
        # n=3 -> k = 2/(3+1) = 0.5, seeded with the first value.
        # e0 = 1
        # e1 = 2*0.5 + 1*0.5    = 1.5
        # e2 = 3*0.5 + 1.5*0.5  = 2.25
        # e3 = 4*0.5 + 2.25*0.5 = 3.125
        # e4 = 5*0.5 + 3.125*0.5= 4.0625
        assert ema([1, 2, 3, 4, 5], 3) == approx([1.0, 1.5, 2.25, 3.125, 4.0625])

    def test_constant_series_stays_constant(self):
        assert ema([42.0] * 10, 5) == approx([42.0] * 10)

    def test_empty(self):
        assert ema([], 5) == []

    def test_converges_toward_latest_value(self):
        # After a long run of 100s following a 0 start, EMA must approach 100.
        out = ema([0.0] + [100.0] * 200, 10)
        assert out[-1] == pytest.approx(100.0, abs=1e-6)

    def test_matches_pandas_ewm_convention(self):
        # Cross-check against pandas ewm(span=n, adjust=False) on a fixed series.
        pd = pytest.importorskip("pandas")
        vals = [3.1, 4.1, 5.9, 2.6, 5.3, 5.8, 9.7, 9.3, 2.3, 8.4]
        expected = pd.Series(vals).ewm(span=4, adjust=False).mean().tolist()
        assert ema(vals, 4) == approx(expected, rel=1e-12)


# ---------------------------------------------------------------------------
# RSI (Wilder)
# ---------------------------------------------------------------------------

class TestRSI:
    def test_known_answer_hand_computed(self):
        # prices:  10, 11, 10.5, 11.5, 12, 11
        # changes:    +1, -0.5,  +1, +0.5, -1
        # n=3, first window = changes 1..3: gains (1, 0, 1), losses (0, 0.5, 0)
        #   avg_gain = 2/3, avg_loss = 1/6 -> RS = 4 -> RSI = 100 - 100/5 = 80
        # i=4 (change +0.5):
        #   avg_gain = (2/3 * 2 + 0.5)/3 = 11/18
        #   avg_loss = (1/6 * 2 + 0)/3   = 1/9
        #   RS = (11/18)/(1/9) = 5.5 -> RSI = 100 - 100/6.5 = 84.6153846...
        # i=5 (change -1):
        #   avg_gain = (11/18 * 2 + 0)/3 = 11/27
        #   avg_loss = (1/9 * 2 + 1)/3   = 11/27
        #   RS = 1 -> RSI = 50
        out = rsi([10, 11, 10.5, 11.5, 12, 11], n=3)
        assert out[:3] == [None, None, None]
        assert out[3] == approx(80.0)
        assert out[4] == approx(100 - 100 / 6.5)   # 84.615384...
        assert out[5] == approx(50.0)

    def test_all_gains_is_100(self):
        out = rsi(list(range(1, 21)), n=14)
        assert out[-1] == approx(100.0)

    def test_all_losses_approaches_zero(self):
        out = rsi(list(range(100, 60, -2)), n=14)
        assert out[-1] == approx(0.0)

    def test_flat_series_is_neutral_50(self):
        out = rsi([50.0] * 20, n=14)
        assert out[-1] == approx(50.0)

    def test_bounded_0_100(self):
        # Deterministic pseudo-random walk (no RNG import needed).
        vals = [100.0]
        for i in range(300):
            vals.append(vals[-1] * (1 + math.sin(i * 12.9898) * 0.02))
        for v in rsi(vals, 14):
            if v is not None:
                assert 0.0 <= v <= 100.0

    def test_undefined_before_period(self):
        out = rsi([1.0] * 30, n=14)
        assert all(v is None for v in out[:14])
        assert all(v is not None for v in out[14:])

    def test_differential_against_reference_implementation(self):
        """Compare the production RSI to an independent, literal transcription
        of Wilder's definition, on a fixed non-trivial series."""
        vals = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
                45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00,
                46.03, 46.41, 46.22, 45.64, 46.21, 46.25, 45.71, 46.45,
                45.78, 45.35, 44.03, 44.18, 44.22, 44.57, 43.42, 42.66, 43.13]
        n = 14

        # Reference implementation: straight from the textbook definition.
        deltas = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
        gains = [max(d, 0.0) for d in deltas]
        losses = [max(-d, 0.0) for d in deltas]
        avg_g = sum(gains[:n]) / n
        avg_l = sum(losses[:n]) / n
        expected = [None] * n + [100 - 100 / (1 + avg_g / avg_l)]
        for i in range(n, len(deltas)):
            avg_g = (avg_g * (n - 1) + gains[i]) / n
            avg_l = (avg_l * (n - 1) + losses[i]) / n
            expected.append(100 - 100 / (1 + avg_g / avg_l))

        got = rsi(vals, n)
        assert got[:n] == [None] * n
        for g, e in zip(got[n:], expected[n:]):
            assert g == approx(e)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

class TestMACD:
    def test_constant_series_all_zero(self):
        m = macd([50.0] * 60)
        assert all(v == approx(0.0) for v in m.line)
        assert all(v == approx(0.0) for v in m.signal)
        assert all(v == approx(0.0) for v in m.hist)

    def test_line_is_fast_minus_slow_ema(self):
        vals = [float(v) for v in [10, 12, 11, 13, 15, 14, 16, 18, 17, 19]]
        m = macd(vals, fast=3, slow=6, signal=4)
        e3, e6 = ema(vals, 3), ema(vals, 6)
        for got, f, s in zip(m.line, e3, e6):
            assert got == approx(f - s)

    def test_hist_is_line_minus_signal(self):
        vals = [float(v) for v in range(1, 40)]
        m = macd(vals)
        sig = ema(m.line, 9)
        for h, l, s in zip(m.hist, m.line, sig):
            assert h == approx(l - s)

    def test_hand_computed_tiny_case(self):
        # fast=1 => EMA is the series itself. slow=2 => k = 2/3.
        # values [2, 4, 6]: e2 = [2, 2 + 2/3*(4-2) = 10/3, 10/3 + 2/3*(6-10/3) = 46/9]
        # line = [0, 4 - 10/3 = 2/3, 6 - 46/9 = 8/9]
        # signal n=2 (k=2/3): [0, 0 + 2/3*(2/3) = 4/9, 4/9 + 2/3*(8/9 - 4/9) = 20/27]
        # hist = [0, 2/3 - 4/9 = 2/9, 8/9 - 20/27 = 4/27]
        m = macd([2.0, 4.0, 6.0], fast=1, slow=2, signal=2)
        assert m.line == approx([0.0, 2 / 3, 8 / 9])
        assert m.signal == approx([0.0, 4 / 9, 20 / 27])
        assert m.hist == approx([0.0, 2 / 9, 4 / 27])

    def test_uptrend_gives_positive_macd(self):
        vals = [100 * 1.01 ** i for i in range(80)]
        m = macd(vals)
        assert m.line[-1] > 0
        assert m.hist[-1] >= 0


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------

class TestMomentum:
    def test_known_answer(self):
        # 110 / 100 - 1 = +10%
        vals = [100.0] * 10 + [110.0]
        out = momentum(vals, 10)
        assert out[:10] == [None] * 10
        assert out[10] == approx(10.0)

    def test_negative(self):
        vals = [200.0] * 5 + [150.0]
        assert momentum(vals, 5)[5] == approx(-25.0)

    def test_flat_is_zero(self):
        assert momentum([50.0] * 15, 10)[-1] == approx(0.0)


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

class TestBollinger:
    def test_rolling_std_known_answer(self):
        # Every 3-window of consecutive integers {k, k+1, k+2}:
        # mean = k+1, var = ((-1)^2 + 0 + 1^2)/3 = 2/3 (population, ddof=0)
        out = rolling_std([1, 2, 3, 4, 5], 3)
        assert out[:2] == [None, None]
        for v in out[2:]:
            assert v == approx(math.sqrt(2 / 3))

    def test_rolling_std_flat_is_zero(self):
        assert rolling_std([7.0] * 5, 3)[-1] == approx(0.0)

    def test_bands_hand_computed(self):
        # i=2 over [1,2,3]: mid=2, sd=sqrt(2/3)
        # upper = 2 + 2*sd, lower = 2 - 2*sd, width = 4*sd
        # %B = (close - lower)/width = (3 - (2 - 2*sd)) / (4*sd) = (1 + 2*sd)/(4*sd)
        sd = math.sqrt(2 / 3)
        bb = bollinger([1.0, 2.0, 3.0, 4.0, 5.0], n=3, k=2.0)
        assert bb.upper[2] == approx(2 + 2 * sd)
        assert bb.lower[2] == approx(2 - 2 * sd)
        assert bb.middle[2] == approx(2.0)
        assert bb.percent_b[2] == approx((1 + 2 * sd) / (4 * sd))

    def test_warmup_is_none(self):
        bb = bollinger([1.0] * 25, n=20)
        assert bb.upper[:19] == [None] * 19
        assert bb.upper[19] is not None

    def test_flat_series_percent_b_is_neutral(self):
        # Bands collapse onto the price; %B defined as 0.5 rather than 0/0.
        bb = bollinger([50.0] * 10, n=3)
        assert bb.percent_b[-1] == approx(0.5)

    def test_price_below_lower_band_gives_negative_percent_b(self):
        # Long flat stretch then a crash: last price far below the band.
        vals = [100.0] * 30 + [70.0]
        bb = bollinger(vals, n=20, k=2.0)
        assert bb.percent_b[-1] < 0


# ---------------------------------------------------------------------------
# Stochastic oscillator
# ---------------------------------------------------------------------------

class TestStochastic:
    def test_known_answer_hand_computed(self):
        # k_period=3, d_period=2
        # i=2: HH = max(10,11,12) = 12, LL = min(8,9,10) = 8
        #   %K = (11 - 8) / (12 - 8) * 100 = 75
        # i=3: HH = max(11,12,13) = 13, LL = min(9,10,11) = 9
        #   %K = (12 - 9) / (13 - 9) * 100 = 75
        # %D = SMA2 of %K: defined from the second %K onward = (75+75)/2 = 75
        st = stochastic([10, 11, 12, 13], [8, 9, 10, 11], [9, 10, 11, 12],
                        k_period=3, d_period=2)
        assert st.k[:2] == [None, None]
        assert st.k[2] == approx(75.0)
        assert st.k[3] == approx(75.0)
        assert st.d[2] is None
        assert st.d[3] == approx(75.0)

    def test_close_at_range_high_is_100(self):
        st = stochastic([2, 3, 4], [1, 1, 1], [2, 3, 4], k_period=3, d_period=1)
        assert st.k[2] == approx(100.0)

    def test_close_at_range_low_is_0(self):
        st = stochastic([5, 5, 5], [4, 3, 2], [4, 3, 2], k_period=3, d_period=1)
        assert st.k[2] == approx(0.0)

    def test_flat_range_is_neutral_50(self):
        st = stochastic([5.0] * 6, [5.0] * 6, [5.0] * 6, k_period=3, d_period=2)
        assert st.k[-1] == approx(50.0)
        assert st.d[-1] == approx(50.0)

    def test_bounded_0_100(self):
        closes = [100 + 10 * math.sin(i / 3) for i in range(60)]
        highs = [c * 1.02 for c in closes]
        lows = [c * 0.98 for c in closes]
        st = stochastic(highs, lows, closes, 14, 3)
        for v in st.k + st.d:
            if v is not None:
                assert 0.0 <= v <= 100.0

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError):
            stochastic([1, 2], [1], [1, 2])


# ---------------------------------------------------------------------------
# On-balance volume
# ---------------------------------------------------------------------------

class TestOBV:
    def test_known_answer_hand_computed(self):
        # closes: 10 -> 11 (up, +200) -> 11 (flat, +0) -> 10 (down, -400) -> 12 (up, +500)
        # obv:     0     200             200              -200              300
        out = obv([10, 11, 11, 10, 12], [100, 200, 300, 400, 500])
        assert out == approx([0.0, 200.0, 200.0, -200.0, 300.0])

    def test_flat_closes_stay_zero(self):
        assert obv([5.0] * 4, [10, 20, 30, 40]) == approx([0.0, 0.0, 0.0, 0.0])

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError):
            obv([1, 2, 3], [1, 2])


# ---------------------------------------------------------------------------
# Causality — the property the backtester's no-lookahead claim rests on
# ---------------------------------------------------------------------------

def _walk(n=140, seed=7):
    """Deterministic pseudo-random price walk (no RNG state, reproducible)."""
    vals = [100.0]
    for i in range(n - 1):
        vals.append(max(vals[-1] * (1 + math.sin((i + seed) * 78.233) * 0.025), 1.0))
    return vals


def _walk_ohlcv(n=140, seed=7):
    closes = _walk(n, seed)
    highs = [c * 1.012 for c in closes]
    lows = [c * 0.99 for c in closes]
    volumes = [1e6 * (1.5 + math.sin(i * 3.7)) for i in range(n)]
    return closes, highs, lows, volumes


class TestCausality:
    """indicator(prefix)[i] must equal indicator(full)[i] for every i.

    This proves that reading precomputed indicator arrays inside a
    walk-forward loop uses no future information.
    """

    @pytest.mark.parametrize("i", [30, 60, 100, 139])
    def test_all_indicators_prefix_stable(self, i):
        closes, highs, lows, volumes = _walk_ohlcv()
        cfg = SignalConfig()
        ind_full = compute_indicators(closes, cfg, highs, lows, volumes)
        ind_prefix = compute_indicators(
            closes[: i + 1], cfg, highs[: i + 1], lows[: i + 1], volumes[: i + 1]
        )
        assert ind_full.sma_fast[i] == approx(ind_prefix.sma_fast[i])
        assert ind_full.sma_slow[i] == approx(ind_prefix.sma_slow[i])
        assert ind_full.rsi[i] == approx(ind_prefix.rsi[i])
        assert ind_full.macd_hist[i] == approx(ind_prefix.macd_hist[i])
        assert ind_full.momentum[i] == approx(ind_prefix.momentum[i])
        assert ind_full.bb_percent[i] == approx(ind_prefix.bb_percent[i])
        assert ind_full.stoch_k[i] == approx(ind_prefix.stoch_k[i])
        assert ind_full.stoch_d[i] == approx(ind_prefix.stoch_d[i])
        assert ind_full.obv[i] == approx(ind_prefix.obv[i])
        assert ind_full.obv_avg[i] == approx(ind_prefix.obv_avg[i])

    @pytest.mark.parametrize("i", [60, 100, 139])
    def test_score_prefix_stable(self, i):
        """The full SignalResult at bar i is identical whether or not the
        future exists — changing bars after i cannot change the decision."""
        closes, highs, lows, volumes = _walk_ohlcv()
        cfg = SignalConfig()
        sig_full = score_at(compute_indicators(closes, cfg, highs, lows, volumes), i, cfg)
        sig_prefix = compute_signal(
            closes[: i + 1], cfg,
            highs=highs[: i + 1], lows=lows[: i + 1], volumes=volumes[: i + 1],
        )
        assert sig_full.action == sig_prefix.action
        assert sig_full.score == approx(sig_prefix.score)
        assert sig_full.confidence == approx(sig_prefix.confidence)


# ---------------------------------------------------------------------------
# Scoring / compute_signal
# ---------------------------------------------------------------------------

def _ind_from(closes, cfg=None):
    return compute_indicators(closes, cfg or SignalConfig())


def make_ind(sf, sl, rv, hist_prev, hist, mom, close=100.0,
             pb=None, sk=None, sd=None, obv_val=None, obv_avg_val=None):
    """Synthetic two-bar IndicatorSet with exact indicator values at index 1,
    so scoring arithmetic can be asserted precisely. New-indicator values
    default to unavailable (contributing 0 with a neutral reason)."""
    return IndicatorSet(
        closes=[close, close],
        sma_fast=[None, sf],
        sma_slow=[None, sl],
        rsi=[None, rv],
        macd_line=[0.0, 0.0],
        macd_signal=[0.0, 0.0],
        macd_hist=[hist_prev, hist],
        momentum=[None, mom],
        bb_percent=[None, pb],
        stoch_k=[None, sk],
        stoch_d=[None, sd],
        obv=[0.0, obv_val] if obv_val is not None else None,
        obv_avg=[None, obv_avg_val] if obv_avg_val is not None else None,
    )


class TestScoringExactArithmetic:
    """Known-answer tests of the weighted score on synthetic indicator values.

    Default weights: trend 1.0, rsi 1.5, macd_cross 1.5, macd_hist 0.5,
    momentum 0.5, bollinger 1.0, stochastic 0.75, obv 0.5;
    buy >= 1.5, sell <= -1.5, confidence = |score| / 4 (capped).
    Reason order: Trend, RSI, MACD, Momentum, Bollinger, Stochastic, OBV.
    """

    def test_max_bullish_score_classic_components(self):
        # +1 (trend) + 1.5 (oversold) + 1.5 (bullish cross) + 0.5 (momentum) = 4.5
        # (new components unavailable -> neutral 0)
        ind = make_ind(sf=105, sl=100, rv=25, hist_prev=-0.1, hist=0.1, mom=5.0)
        sig = score_at(ind, 1, SignalConfig())
        assert sig.score == approx(4.5)
        assert sig.action == "BUY"
        assert sig.confidence == approx(1.0)  # 4.5 / 4 capped at 1
        assert [r.direction for r in sig.reasons] == [1, 1, 1, 1, 0, 0, 0]

    def test_max_bearish_score_classic_components(self):
        # -1 (trend) - 1.5 (overbought) - 1.5 (bearish cross) - 0.5 (momentum) = -4.5
        ind = make_ind(sf=95, sl=100, rv=75, hist_prev=0.1, hist=-0.1, mom=-5.0)
        sig = score_at(ind, 1, SignalConfig())
        assert sig.score == approx(-4.5)
        assert sig.action == "SELL"
        assert sig.confidence == approx(1.0)
        assert [r.direction for r in sig.reasons] == [-1, -1, -1, -1, 0, 0, 0]

    def test_full_house_bullish_all_seven_components(self):
        # 1 + 1.5 + 1.5 + 0.5 + 1.0 (bollinger) + 0.75 (stoch) + 0.5 (obv) = 6.75
        ind = make_ind(sf=105, sl=100, rv=25, hist_prev=-0.1, hist=0.1, mom=5.0,
                       pb=0.02, sk=10.0, sd=15.0, obv_val=100.0, obv_avg_val=50.0)
        sig = score_at(ind, 1, SignalConfig())
        assert sig.score == approx(6.75)
        assert sig.action == "BUY"
        assert sig.confidence == approx(1.0)
        assert [r.direction for r in sig.reasons] == [1, 1, 1, 1, 1, 1, 1]

    def test_full_house_bearish_all_seven_components(self):
        ind = make_ind(sf=95, sl=100, rv=75, hist_prev=0.1, hist=-0.1, mom=-5.0,
                       pb=0.98, sk=90.0, sd=85.0, obv_val=50.0, obv_avg_val=100.0)
        sig = score_at(ind, 1, SignalConfig())
        assert sig.score == approx(-6.75)
        assert sig.action == "SELL"
        assert [r.direction for r in sig.reasons] == [-1, -1, -1, -1, -1, -1, -1]

    def test_bollinger_thresholds_are_strict(self):
        cfg = SignalConfig()
        base = dict(sf=None, sl=None, rv=50, hist_prev=0.1, hist=0.1, mom=0.0)  # +0.5 from hist
        at_lower = score_at(make_ind(**base, pb=0.05), 1, cfg)
        below = score_at(make_ind(**base, pb=0.049), 1, cfg)
        at_upper = score_at(make_ind(**base, pb=0.95), 1, cfg)
        above = score_at(make_ind(**base, pb=0.951), 1, cfg)
        assert at_lower.score == approx(0.5)          # %B == threshold: neutral
        assert below.score == approx(1.5)             # +1.0 bollinger
        assert at_upper.score == approx(0.5)
        assert above.score == approx(-0.5)            # -1.0 bollinger

    def test_stochastic_thresholds_are_strict(self):
        cfg = SignalConfig()
        base = dict(sf=None, sl=None, rv=50, hist_prev=0.1, hist=0.1, mom=0.0)
        assert score_at(make_ind(**base, sd=20.0), 1, cfg).score == approx(0.5)
        assert score_at(make_ind(**base, sd=19.9), 1, cfg).score == approx(1.25)   # +0.75
        assert score_at(make_ind(**base, sd=80.0), 1, cfg).score == approx(0.5)
        assert score_at(make_ind(**base, sd=80.1), 1, cfg).score == approx(-0.25)  # -0.75

    def test_obv_direction(self):
        cfg = SignalConfig()
        base = dict(sf=None, sl=None, rv=50, hist_prev=0.1, hist=0.1, mom=0.0)
        up = score_at(make_ind(**base, obv_val=100.0, obv_avg_val=50.0), 1, cfg)
        down = score_at(make_ind(**base, obv_val=50.0, obv_avg_val=100.0), 1, cfg)
        flat = score_at(make_ind(**base, obv_val=75.0, obv_avg_val=75.0), 1, cfg)
        assert up.score == approx(1.0)     # +0.5 obv
        assert down.score == approx(0.0)   # -0.5 obv
        assert flat.score == approx(0.5)   # neutral

    def test_hold_zone(self):
        # -1 (trend) + 0 (RSI neutral) + 0.5 (hist positive, no cross) + 0 = -0.5
        ind = make_ind(sf=95, sl=100, rv=50, hist_prev=0.2, hist=0.1, mom=0.0)
        sig = score_at(ind, 1, SignalConfig())
        assert sig.score == approx(-0.5)
        assert sig.action == "HOLD"
        assert sig.confidence == approx(0.125)  # 0.5 / 4

    def test_bearish_cross_alone_triggers_sell(self):
        # Trend/RSI/momentum unavailable or neutral; hist flips + -> -  => -1.5
        ind = make_ind(sf=None, sl=None, rv=50, hist_prev=0.05, hist=-0.05, mom=0.0)
        sig = score_at(ind, 1, SignalConfig())
        assert sig.score == approx(-1.5)
        assert sig.action == "SELL"
        macd_reason = next(r for r in sig.reasons if r.key == "MACD")
        assert "bearish crossover" in macd_reason.detail

    def test_buy_threshold_from_config(self):
        ind = make_ind(sf=105, sl=100, rv=25, hist_prev=-0.1, hist=0.1, mom=5.0)
        assert score_at(ind, 1, SignalConfig()).action == "BUY"
        assert score_at(ind, 1, SignalConfig(buy_score=99.0)).action == "HOLD"

    def test_rsi_thresholds_are_strict_inequalities(self):
        cfg = SignalConfig()
        at_oversold = make_ind(sf=None, sl=None, rv=30.0, hist_prev=0.1, hist=0.1, mom=0.0)
        below = make_ind(sf=None, sl=None, rv=29.99, hist_prev=0.1, hist=0.1, mom=0.0)
        # rv == 30 is neutral; rv < 30 scores +1.5
        assert score_at(at_oversold, 1, cfg).score == approx(0.5)   # hist only
        assert score_at(below, 1, cfg).score == approx(2.0)         # 1.5 + 0.5

    def test_momentum_threshold_is_strict(self):
        cfg = SignalConfig()
        at_thr = make_ind(sf=None, sl=None, rv=50, hist_prev=0.1, hist=0.1, mom=4.0)
        over = make_ind(sf=None, sl=None, rv=50, hist_prev=0.1, hist=0.1, mom=4.01)
        assert score_at(at_thr, 1, cfg).score == approx(0.5)
        assert score_at(over, 1, cfg).score == approx(1.0)

    def test_custom_weights_change_score(self):
        ind = make_ind(sf=105, sl=100, rv=25, hist_prev=-0.1, hist=0.1, mom=5.0)
        cfg = SignalConfig(w_trend=10.0)
        # 10 + 1.5 + 1.5 + 0.5
        assert score_at(ind, 1, cfg).score == approx(13.5)


class TestScoring:
    def test_strong_uptrend_scores_bullish_trend_component(self):
        vals = [100 * 1.004 ** i for i in range(120)]
        sig = compute_signal(vals)
        trend = next(r for r in sig.reasons if r.key == "Trend")
        assert trend.direction == 1
        assert sig.sma_fast > sig.sma_slow

    def test_monotonic_downtrend_components(self):
        # A persistent downtrend is NOT a slam-dunk SELL under these rules:
        # trend (-1) and momentum (-0.5) are bearish, but two mean-reversion /
        # convergence effects push the other way:
        #  - RSI pinned near 0 is oversold => bullish (+1.5)
        #  - on a steady geometric decay the MACD line ~ c*price (c<0) rises
        #    toward zero, so its lagging signal line sits BELOW it and the
        #    histogram is slightly positive (+0.5)
        # Net: +0.5 -> HOLD. Assert components, not a guessed total.
        vals = [100 * 0.99 ** i for i in range(120)]
        sig = compute_signal(vals)
        by_key = {r.key: r.direction for r in sig.reasons}
        assert by_key["Trend"] == -1
        assert by_key["MACD"] == 1   # histogram positive: line converging to 0 from below
        assert by_key["Momentum"] == -1
        assert by_key["RSI"] == 1    # oversold => bullish component
        # Steady decay rides just above the lower band (%B ~ 0.11): neutral.
        assert by_key["Bollinger"] == 0
        assert sig.score == approx(0.5)
        assert sig.action == "HOLD"

    def test_oversold_rsi_reason_present(self):
        # Long flat stretch then a hard consistent selloff -> RSI < 30.
        vals = [100.0] * 60 + [100 * 0.97 ** i for i in range(1, 20)]
        sig = compute_signal(vals)
        rsi_reason = next(r for r in sig.reasons if r.key == "RSI")
        assert sig.rsi < 30
        assert rsi_reason.direction == 1  # oversold is a bullish component

    def test_flat_series_documented_tiebreaks(self):
        # Degenerate perfectly-flat input. Documents intentional tie-breaking
        # (kept for parity with the original signal-desk.jsx rules):
        #   trend: SMA20 == SMA50 falls into the "not above" branch  -> -1.0
        #   RSI: flat window is neutral 50                            ->  0
        #   MACD: hist == 0 falls into the "not positive" branch      -> -0.5
        #   momentum: 0% is inside the neutral band                   ->  0
        #   bollinger: collapsed bands => %B defined as 0.5, neutral  ->  0
        #   stochastic/OBV: closes-only input, unavailable            ->  0
        # Total -1.5 == sell threshold -> SELL on flat input.
        sig = compute_signal([100.0] * 80)
        assert sig.score == approx(-1.5)
        assert sig.action == "SELL"

    def test_weights_come_from_config(self):
        vals = [100 * 1.004 ** i for i in range(120)]
        base = compute_signal(vals, SignalConfig())
        heavy = compute_signal(vals, SignalConfig(w_trend=10.0))
        # Same direction components, but the trend piece is now 10x.
        assert heavy.score == approx(base.score + 9.0)

    def test_confidence_clamped_to_1(self):
        # The monotonic-downtrend series nets score -0.5 (see components test);
        # with divisor 0.5 the raw ratio is exactly 1.0 and must not exceed it.
        vals = [100 * 0.99 ** i for i in range(120)]
        sig = compute_signal(vals, SignalConfig(confidence_divisor=0.5))
        assert sig.confidence == approx(1.0)

    def test_confidence_formula(self):
        vals = [100 * 1.004 ** i for i in range(120)]
        cfg = SignalConfig(confidence_divisor=4.0)
        sig = compute_signal(vals, cfg)
        assert sig.confidence == approx(min(abs(sig.score) / 4.0, 1.0))

    def test_macd_bullish_crossover_detected(self):
        # Construct a series whose MACD hist flips negative->positive on the
        # final bar: long decline then a sharp rally.
        vals = [100 * 0.998 ** i for i in range(80)]
        rally = [vals[-1] * 1.012 ** i for i in range(1, 12)]
        series = vals + rally
        cfg = SignalConfig()
        ind = _ind_from(series, cfg)
        # Find a bar where the flip happens; assert score_at flags the cross.
        flip = next(
            (i for i in range(1, len(series)) if ind.macd_hist[i] > 0 >= ind.macd_hist[i - 1]),
            None,
        )
        assert flip is not None, "constructed series must contain a bullish flip"
        sig = score_at(ind, flip, cfg)
        macd_reason = next(r for r in sig.reasons if r.key == "MACD")
        assert "bullish crossover" in macd_reason.detail
        assert macd_reason.direction == 1

    def test_short_history_degrades_gracefully(self):
        sig = compute_signal([100.0, 101.0, 102.0])
        assert sig.action in ("BUY", "SELL", "HOLD")
        assert any("insufficient" in r.detail for r in sig.reasons)

    def test_empty_series_raises(self):
        with pytest.raises(ValueError):
            compute_signal([])

    def test_reasons_cover_all_components(self):
        # closes-only: stochastic/OBV report as unavailable but still appear
        sig = compute_signal(_walk())
        assert {r.key for r in sig.reasons} == {
            "Trend", "RSI", "MACD", "Momentum", "Bollinger", "Stochastic", "OBV"
        }

    def test_reasons_with_full_ohlcv_have_no_unavailable(self):
        closes, highs, lows, volumes = _walk_ohlcv()
        sig = compute_signal(closes, None, highs=highs, lows=lows, volumes=volumes)
        assert not any("unavailable" in r.detail for r in sig.reasons)


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

class TestConfig:
    def test_from_dict_full(self):
        cfg = SignalConfig.from_dict({
            "indicators": {"sma_fast": 10, "sma_slow": 30, "rsi_period": 7,
                           "macd_fast": 5, "macd_slow": 15, "macd_signal": 4,
                           "momentum_days": 5, "bb_period": 10, "bb_std": 2.5,
                           "stoch_k": 9, "stoch_d": 4, "obv_sma": 15},
            "weights": {"trend": 2.0, "rsi": 3.0, "macd_cross": 1.0,
                        "macd_hist": 0.25, "momentum": 0.75,
                        "bollinger": 1.25, "stochastic": 0.6, "obv": 0.4},
            "thresholds": {"rsi_oversold": 25, "rsi_overbought": 75,
                           "momentum_pct": 5.0, "bb_lower": 0.1, "bb_upper": 0.9,
                           "stoch_oversold": 25, "stoch_overbought": 75,
                           "buy_score": 2.0, "sell_score": -2.0,
                           "confidence_divisor": 5.0},
        })
        assert cfg.sma_fast == 10 and cfg.sma_slow == 30
        assert cfg.w_trend == 2.0 and cfg.w_rsi == 3.0
        assert cfg.rsi_oversold == 25 and cfg.buy_score == 2.0
        assert cfg.bb_period == 10 and cfg.bb_std == 2.5
        assert cfg.stoch_k == 9 and cfg.stoch_d == 4 and cfg.obv_sma == 15
        assert cfg.w_bollinger == 1.25 and cfg.w_stoch == 0.6 and cfg.w_obv == 0.4
        assert cfg.bb_lower == 0.1 and cfg.stoch_overbought == 75

    def test_from_dict_empty_uses_defaults(self):
        assert SignalConfig.from_dict({}) == SignalConfig()

    def test_warmup_covers_all_indicators(self):
        cfg = SignalConfig()
        w = cfg.warmup_bars()
        assert w > cfg.sma_slow - 1
        assert w > cfg.rsi_period
        assert w > cfg.momentum_days
        assert w > cfg.macd_slow + cfg.macd_signal
        assert w > cfg.bb_period - 1
        assert w > cfg.stoch_k + cfg.stoch_d - 2
        assert w > cfg.obv_sma - 1

    def test_default_warmup_unchanged_by_new_indicators(self):
        # SMA50 (49 prior bars) still dominates the default warmup — the new
        # indicators (BB 19, stoch 15, OBV 19) are all shorter, so adding them
        # did not shift existing default backtest windows.
        assert SignalConfig().warmup_bars() == 50
