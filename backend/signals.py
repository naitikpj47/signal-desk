"""Pure signal-engine functions.

No I/O, no database, no framework imports — every function operates on plain
Python lists of floats so the whole module is trivially unit-testable.

Conventions
-----------
- Indicator outputs are lists the same length as the input; positions where the
  indicator is not yet defined hold ``None``.
- EMA is seeded with the first value (matches ``pandas.ewm(span=n, adjust=False)``).
- RSI uses Wilder's smoothing: the first average gain/loss is a simple mean of
  the first ``n`` changes, then ``avg = (avg * (n - 1) + new) / n``.
- Every indicator is a *causal* filter: the value at index ``i`` depends only on
  ``values[: i + 1]``. This property is what makes the backtester lookahead-free
  and is asserted directly by the test suite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignalConfig:
    """Weights / thresholds for the scoring rules. Mirrors signals.yaml."""

    # indicator parameters
    sma_fast: int = 20
    sma_slow: int = 50
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    momentum_days: int = 10
    bb_period: int = 20
    bb_std: float = 2.0
    stoch_k: int = 14
    stoch_d: int = 3
    obv_sma: int = 20

    # component weights
    w_trend: float = 1.0
    w_rsi: float = 1.5
    w_macd_cross: float = 1.5
    w_macd_hist: float = 0.5
    w_momentum: float = 0.5
    w_bollinger: float = 1.0
    w_stoch: float = 0.75
    w_obv: float = 0.5

    # thresholds
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    momentum_pct: float = 4.0
    bb_lower: float = 0.05      # %B below this => at/under lower band (bullish)
    bb_upper: float = 0.95      # %B above this => at/over upper band (bearish)
    stoch_oversold: float = 20.0
    stoch_overbought: float = 80.0
    buy_score: float = 1.5
    sell_score: float = -1.5
    confidence_divisor: float = 4.0

    @staticmethod
    def from_dict(raw: dict) -> "SignalConfig":
        """Build a config from the nested dict shape used by signals.yaml.

        Unknown keys are ignored; missing keys fall back to the defaults above.
        """
        ind = raw.get("indicators", {}) or {}
        w = raw.get("weights", {}) or {}
        th = raw.get("thresholds", {}) or {}
        defaults = SignalConfig()
        return SignalConfig(
            sma_fast=int(ind.get("sma_fast", defaults.sma_fast)),
            sma_slow=int(ind.get("sma_slow", defaults.sma_slow)),
            rsi_period=int(ind.get("rsi_period", defaults.rsi_period)),
            macd_fast=int(ind.get("macd_fast", defaults.macd_fast)),
            macd_slow=int(ind.get("macd_slow", defaults.macd_slow)),
            macd_signal=int(ind.get("macd_signal", defaults.macd_signal)),
            momentum_days=int(ind.get("momentum_days", defaults.momentum_days)),
            bb_period=int(ind.get("bb_period", defaults.bb_period)),
            bb_std=float(ind.get("bb_std", defaults.bb_std)),
            stoch_k=int(ind.get("stoch_k", defaults.stoch_k)),
            stoch_d=int(ind.get("stoch_d", defaults.stoch_d)),
            obv_sma=int(ind.get("obv_sma", defaults.obv_sma)),
            w_trend=float(w.get("trend", defaults.w_trend)),
            w_rsi=float(w.get("rsi", defaults.w_rsi)),
            w_macd_cross=float(w.get("macd_cross", defaults.w_macd_cross)),
            w_macd_hist=float(w.get("macd_hist", defaults.w_macd_hist)),
            w_momentum=float(w.get("momentum", defaults.w_momentum)),
            w_bollinger=float(w.get("bollinger", defaults.w_bollinger)),
            w_stoch=float(w.get("stochastic", defaults.w_stoch)),
            w_obv=float(w.get("obv", defaults.w_obv)),
            rsi_oversold=float(th.get("rsi_oversold", defaults.rsi_oversold)),
            rsi_overbought=float(th.get("rsi_overbought", defaults.rsi_overbought)),
            momentum_pct=float(th.get("momentum_pct", defaults.momentum_pct)),
            bb_lower=float(th.get("bb_lower", defaults.bb_lower)),
            bb_upper=float(th.get("bb_upper", defaults.bb_upper)),
            stoch_oversold=float(th.get("stoch_oversold", defaults.stoch_oversold)),
            stoch_overbought=float(th.get("stoch_overbought", defaults.stoch_overbought)),
            buy_score=float(th.get("buy_score", defaults.buy_score)),
            sell_score=float(th.get("sell_score", defaults.sell_score)),
            confidence_divisor=float(th.get("confidence_divisor", defaults.confidence_divisor)),
        )

    def warmup_bars(self) -> int:
        """Index of the first bar at which every scoring component is reliable.

        - SMA slow needs ``sma_slow - 1`` prior bars.
        - RSI needs ``rsi_period`` prior bars.
        - Momentum needs ``momentum_days`` prior bars.
        - MACD's EMAs are defined from bar 0 (first-value seed) but carry heavy
          seed bias early on, so we require ``macd_slow + macd_signal`` bars.
        - The MACD *crossover* rule looks at ``hist[i - 1]``, hence the ``+ 1``.
        - Bollinger needs ``bb_period`` bars, stochastic %D needs
          ``stoch_k + stoch_d - 1``, OBV's average needs ``obv_sma`` bars.
        """
        return max(
            self.sma_slow - 1,
            self.rsi_period,
            self.momentum_days,
            self.macd_slow + self.macd_signal,
            self.bb_period - 1,
            self.stoch_k + self.stoch_d - 2,
            self.obv_sma - 1,
        ) + 1


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def sma(values: list[float], n: int) -> list[Optional[float]]:
    """Simple moving average. First ``n - 1`` entries are ``None``."""
    if n <= 0:
        raise ValueError("SMA period must be positive")
    out: list[Optional[float]] = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= n:
            running -= values[i - n]
        if i >= n - 1:
            out[i] = running / n
    return out


def ema(values: list[float], n: int) -> list[float]:
    """Exponential moving average, seeded with the first value.

    Matches ``pandas.Series.ewm(span=n, adjust=False).mean()``.
    """
    if n <= 0:
        raise ValueError("EMA period must be positive")
    if not values:
        return []
    k = 2.0 / (n + 1)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(values: list[float], n: int = 14) -> list[Optional[float]]:
    """Wilder's RSI. Defined from index ``n`` onward.

    Edge cases: if the average loss is zero the formula degenerates —
    all-gains yields 100.0, and a perfectly flat window yields a neutral 50.0.
    """
    if n <= 0:
        raise ValueError("RSI period must be positive")
    out: list[Optional[float]] = [None] * len(values)
    if len(values) <= n:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, n + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_gain = gains / n
    avg_loss = losses / n
    out[n] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(n + 1, len(values)):
        d = values[i] - values[i - 1]
        avg_gain = (avg_gain * (n - 1) + max(d, 0.0)) / n
        avg_loss = (avg_loss * (n - 1) + max(-d, 0.0)) / n
        out[i] = _rsi_from_averages(avg_gain, avg_loss)
    return out


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


@dataclass(frozen=True)
class MacdResult:
    line: list[float]
    signal: list[float]
    hist: list[float]


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> MacdResult:
    """MACD line (EMA fast - EMA slow), signal line (EMA of MACD), histogram."""
    e_fast = ema(values, fast)
    e_slow = ema(values, slow)
    line = [f - s for f, s in zip(e_fast, e_slow)]
    sig = ema(line, signal)
    hist = [l - s for l, s in zip(line, sig)]
    return MacdResult(line=line, signal=sig, hist=hist)


def momentum(values: list[float], n: int = 10) -> list[Optional[float]]:
    """Percent change over the last ``n`` bars: ``(v[i] / v[i - n] - 1) * 100``."""
    if n <= 0:
        raise ValueError("Momentum period must be positive")
    out: list[Optional[float]] = [None] * len(values)
    for i in range(n, len(values)):
        base = values[i - n]
        if base != 0:
            out[i] = (values[i] / base - 1.0) * 100.0
    return out


def rolling_std(values: list[float], n: int) -> list[Optional[float]]:
    """Trailing population standard deviation (ddof=0, the Bollinger convention)."""
    if n <= 0:
        raise ValueError("std period must be positive")
    out: list[Optional[float]] = [None] * len(values)
    s = 0.0
    sq = 0.0
    for i, v in enumerate(values):
        s += v
        sq += v * v
        if i >= n:
            s -= values[i - n]
            sq -= values[i - n] * values[i - n]
        if i >= n - 1:
            mean = s / n
            var = max(sq / n - mean * mean, 0.0)  # clamp float cancellation noise
            out[i] = var ** 0.5
    return out


@dataclass(frozen=True)
class BollingerResult:
    upper: list[Optional[float]]
    middle: list[Optional[float]]
    lower: list[Optional[float]]
    percent_b: list[Optional[float]]  # (price - lower) / (upper - lower); 0.5 when bands collapse


def bollinger(values: list[float], n: int = 20, k: float = 2.0) -> BollingerResult:
    """Bollinger Bands: SMA(n) +/- k * population std(n), plus %B position."""
    mid = sma(values, n)
    sd = rolling_std(values, n)
    upper: list[Optional[float]] = [None] * len(values)
    lower: list[Optional[float]] = [None] * len(values)
    pb: list[Optional[float]] = [None] * len(values)
    for i, (m, s) in enumerate(zip(mid, sd)):
        if m is None or s is None:
            continue
        upper[i] = m + k * s
        lower[i] = m - k * s
        width = upper[i] - lower[i]
        # Flat window => bands collapse onto the price; %B is neutral by definition.
        pb[i] = (values[i] - lower[i]) / width if width > 0 else 0.5
    return BollingerResult(upper=upper, middle=mid, lower=lower, percent_b=pb)


@dataclass(frozen=True)
class StochResult:
    k: list[Optional[float]]  # fast %K
    d: list[Optional[float]]  # %D = SMA(k, d_period)


def stochastic(
    highs: list[float], lows: list[float], closes: list[float],
    k_period: int = 14, d_period: int = 3,
) -> StochResult:
    """Stochastic oscillator: %K over the trailing high/low range, %D smoothing.

    A flat range (highest high == lowest low) yields a neutral 50.
    """
    if k_period <= 0 or d_period <= 0:
        raise ValueError("stochastic periods must be positive")
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows and closes must be the same length")
    n = len(closes)
    k: list[Optional[float]] = [None] * n
    for i in range(k_period - 1, n):
        hh = max(highs[i - k_period + 1: i + 1])
        ll = min(lows[i - k_period + 1: i + 1])
        rng = hh - ll
        k[i] = ((closes[i] - ll) / rng * 100.0) if rng > 0 else 50.0
    # %D: SMA of %K over the bars where %K is defined.
    d: list[Optional[float]] = [None] * n
    defined = [v for v in k if v is not None]
    d_vals = sma(defined, d_period)
    for j, i in enumerate(range(k_period - 1, n)):
        d[i] = d_vals[j]
    return StochResult(k=k, d=d)


def obv(closes: list[float], volumes: list[float]) -> list[float]:
    """On-balance volume: cumulative volume signed by the day's close direction."""
    if len(closes) != len(volumes):
        raise ValueError("closes and volumes must be the same length")
    out: list[float] = []
    total = 0.0
    for i, c in enumerate(closes):
        if i > 0:
            if c > closes[i - 1]:
                total += volumes[i]
            elif c < closes[i - 1]:
                total -= volumes[i]
        out.append(total)
    return out


# ---------------------------------------------------------------------------
# Indicator bundle + scoring
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IndicatorSet:
    """All indicator series for one price history, computed once.

    Because every indicator is causal (value at ``i`` uses only bars ``<= i``),
    reading ``IndicatorSet`` values at index ``i`` inside a walk-forward loop is
    equivalent to recomputing the indicators on ``closes[: i + 1]`` — verified
    by ``test_signals.py::TestCausality``.
    """
    closes: list[float]
    sma_fast: list[Optional[float]]
    sma_slow: list[Optional[float]]
    rsi: list[Optional[float]]
    macd_line: list[float]
    macd_signal: list[float]
    macd_hist: list[float]
    momentum: list[Optional[float]]
    # Optional series: None when the required inputs weren't provided.
    bb_upper: Optional[list[Optional[float]]] = None
    bb_lower: Optional[list[Optional[float]]] = None
    bb_percent: Optional[list[Optional[float]]] = None
    stoch_k: Optional[list[Optional[float]]] = None
    stoch_d: Optional[list[Optional[float]]] = None
    obv: Optional[list[float]] = None
    obv_avg: Optional[list[Optional[float]]] = None


def compute_indicators(
    closes: list[float],
    cfg: SignalConfig,
    highs: Optional[list[float]] = None,
    lows: Optional[list[float]] = None,
    volumes: Optional[list[float]] = None,
) -> IndicatorSet:
    """Compute all indicator series. Stochastic needs highs/lows; OBV needs
    volumes — those series stay ``None`` when the inputs are absent and their
    scoring components simply sit out."""
    m = macd(closes, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    bb = bollinger(closes, cfg.bb_period, cfg.bb_std)
    st = stochastic(highs, lows, closes, cfg.stoch_k, cfg.stoch_d) if highs and lows else None
    ov = obv(closes, volumes) if volumes else None
    return IndicatorSet(
        closes=closes,
        sma_fast=sma(closes, cfg.sma_fast),
        sma_slow=sma(closes, cfg.sma_slow),
        rsi=rsi(closes, cfg.rsi_period),
        macd_line=m.line,
        macd_signal=m.signal,
        macd_hist=m.hist,
        momentum=momentum(closes, cfg.momentum_days),
        bb_upper=bb.upper,
        bb_lower=bb.lower,
        bb_percent=bb.percent_b,
        stoch_k=st.k if st else None,
        stoch_d=st.d if st else None,
        obv=ov,
        obv_avg=sma(ov, cfg.obv_sma) if ov is not None else None,
    )


@dataclass(frozen=True)
class Reason:
    key: str        # "Trend" | "RSI" | "MACD" | "Momentum" | "Bollinger" | "Stochastic" | "OBV"
    detail: str     # human-readable explanation
    direction: int  # +1 bullish, -1 bearish, 0 neutral


@dataclass(frozen=True)
class SignalResult:
    action: str          # "BUY" | "SELL" | "HOLD"
    score: float
    confidence: float    # 0..1
    reasons: list[Reason] = field(default_factory=list)
    rsi: Optional[float] = None
    macd_hist: Optional[float] = None
    sma_fast: Optional[float] = None
    sma_slow: Optional[float] = None
    momentum_pct: Optional[float] = None
    percent_b: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None


def score_at(ind: IndicatorSet, i: int, cfg: SignalConfig) -> SignalResult:
    """Score the bar at index ``i`` using only information available at ``i``.

    This single function drives BOTH the live signal endpoint and the
    backtester, so the two can never drift apart.
    """
    if i < 0:
        i += len(ind.closes)
    if not 0 <= i < len(ind.closes):
        raise IndexError(f"index {i} out of range for {len(ind.closes)} bars")

    reasons: list[Reason] = []
    score = 0.0

    # --- Trend: SMA fast vs slow -------------------------------------------
    sf, sl = ind.sma_fast[i], ind.sma_slow[i]
    if sf is not None and sl is not None:
        if sf > sl:
            score += cfg.w_trend
            reasons.append(Reason("Trend", f"SMA{cfg.sma_fast} above SMA{cfg.sma_slow}, uptrend", 1))
        else:
            score -= cfg.w_trend
            reasons.append(Reason("Trend", f"SMA{cfg.sma_fast} below SMA{cfg.sma_slow}, downtrend", -1))
    else:
        reasons.append(Reason("Trend", "insufficient history for SMA trend", 0))

    # --- RSI ----------------------------------------------------------------
    rv = ind.rsi[i]
    if rv is not None:
        if rv < cfg.rsi_oversold:
            score += cfg.w_rsi
            reasons.append(Reason("RSI", f"{rv:.0f} oversold", 1))
        elif rv > cfg.rsi_overbought:
            score -= cfg.w_rsi
            reasons.append(Reason("RSI", f"{rv:.0f} overbought", -1))
        else:
            reasons.append(Reason("RSI", f"{rv:.0f} neutral zone", 0))
    else:
        reasons.append(Reason("RSI", "insufficient history for RSI", 0))

    # --- MACD crossover / histogram ----------------------------------------
    h = ind.macd_hist[i]
    h_prev = ind.macd_hist[i - 1] if i >= 1 else None
    if h_prev is not None and h > 0 and h_prev <= 0:
        score += cfg.w_macd_cross
        reasons.append(Reason("MACD", "bullish crossover today", 1))
    elif h_prev is not None and h < 0 and h_prev >= 0:
        score -= cfg.w_macd_cross
        reasons.append(Reason("MACD", "bearish crossover today", -1))
    elif h > 0:
        score += cfg.w_macd_hist
        reasons.append(Reason("MACD", "histogram positive", 1))
    else:
        score -= cfg.w_macd_hist
        reasons.append(Reason("MACD", "histogram negative", -1))

    # --- Momentum -----------------------------------------------------------
    mv = ind.momentum[i]
    if mv is not None:
        if mv > cfg.momentum_pct:
            score += cfg.w_momentum
            reasons.append(Reason("Momentum", f"+{mv:.1f}% over {cfg.momentum_days} days", 1))
        elif mv < -cfg.momentum_pct:
            score -= cfg.w_momentum
            reasons.append(Reason("Momentum", f"{mv:.1f}% over {cfg.momentum_days} days", -1))
        else:
            reasons.append(Reason("Momentum", f"{mv:+.1f}% over {cfg.momentum_days} days", 0))
    else:
        reasons.append(Reason("Momentum", "insufficient history for momentum", 0))

    # --- Bollinger %B -------------------------------------------------------
    pb = ind.bb_percent[i] if ind.bb_percent is not None else None
    if pb is not None:
        if pb < cfg.bb_lower:
            score += cfg.w_bollinger
            reasons.append(Reason("Bollinger", f"%B {pb:.2f}, at lower band", 1))
        elif pb > cfg.bb_upper:
            score -= cfg.w_bollinger
            reasons.append(Reason("Bollinger", f"%B {pb:.2f}, at upper band", -1))
        else:
            reasons.append(Reason("Bollinger", f"%B {pb:.2f}, inside bands", 0))
    else:
        reasons.append(Reason("Bollinger", "insufficient history for Bollinger Bands", 0))

    # --- Stochastic %D ------------------------------------------------------
    sd = ind.stoch_d[i] if ind.stoch_d is not None else None
    sk = ind.stoch_k[i] if ind.stoch_k is not None else None
    if sd is not None:
        if sd < cfg.stoch_oversold:
            score += cfg.w_stoch
            reasons.append(Reason("Stochastic", f"%D {sd:.0f} oversold", 1))
        elif sd > cfg.stoch_overbought:
            score -= cfg.w_stoch
            reasons.append(Reason("Stochastic", f"%D {sd:.0f} overbought", -1))
        else:
            reasons.append(Reason("Stochastic", f"%D {sd:.0f} mid-range", 0))
    elif ind.stoch_d is None:
        reasons.append(Reason("Stochastic", "needs high/low history (unavailable)", 0))
    else:
        reasons.append(Reason("Stochastic", "insufficient history for stochastic", 0))

    # --- OBV vs its average -------------------------------------------------
    ov = ind.obv[i] if ind.obv is not None else None
    om = ind.obv_avg[i] if ind.obv_avg is not None else None
    if ov is not None and om is not None:
        if ov > om:
            score += cfg.w_obv
            reasons.append(Reason("OBV", f"above its {cfg.obv_sma}-day average, accumulation", 1))
        elif ov < om:
            score -= cfg.w_obv
            reasons.append(Reason("OBV", f"below its {cfg.obv_sma}-day average, distribution", -1))
        else:
            reasons.append(Reason("OBV", "at its average", 0))
    elif ind.obv is None:
        reasons.append(Reason("OBV", "needs volume history (unavailable)", 0))
    else:
        reasons.append(Reason("OBV", "insufficient history for OBV average", 0))

    # --- Aggregate ----------------------------------------------------------
    action = "HOLD"
    if score >= cfg.buy_score:
        action = "BUY"
    elif score <= cfg.sell_score:
        action = "SELL"
    confidence = min(abs(score) / cfg.confidence_divisor, 1.0)

    return SignalResult(
        action=action,
        score=score,
        confidence=confidence,
        reasons=reasons,
        rsi=rv,
        macd_hist=h,
        sma_fast=sf,
        sma_slow=sl,
        momentum_pct=mv,
        percent_b=pb,
        stoch_k=sk,
        stoch_d=sd,
    )


def compute_signal(
    closes: list[float],
    cfg: Optional[SignalConfig] = None,
    highs: Optional[list[float]] = None,
    lows: Optional[list[float]] = None,
    volumes: Optional[list[float]] = None,
) -> SignalResult:
    """Convenience wrapper: score the most recent bar of a price history."""
    cfg = cfg or SignalConfig()
    if not closes:
        raise ValueError("cannot compute a signal on an empty price series")
    ind = compute_indicators(closes, cfg, highs=highs, lows=lows, volumes=volumes)
    return score_at(ind, len(closes) - 1, cfg)
