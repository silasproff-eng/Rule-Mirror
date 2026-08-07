from decimal import Decimal

from app.analytics.indicators import ema, relative_volume
from app.market_data.base import Bar
from app.strategies.vwap_reclaim import RuleEvaluationValue, RuleResult, result_payload

STRATEGIES = {
    "opening-range-breakout": ("Opening Range Breakout", "breakout"), "moving-average-crossover": ("Moving Average Crossover", "trend"), "macd-cross": ("MACD Cross", "trend"), "rsi-reversion": ("RSI Reversion", "reversion"), "bollinger-band-reversion": ("Bollinger Band Reversion", "reversion"), "bollinger-band-squeeze": ("Bollinger Band Squeeze", "volatility"), "donchian-channel-breakout": ("Donchian Channel Breakout", "breakout"), "keltner-channel-breakout": ("Keltner Channel Breakout", "volatility"), "trendline-break": ("Trendline Break", "breakout"), "support-and-resistance": ("Support and Resistance", "breakout"), "pullback-to-moving-average": ("Pullback to Moving Average", "trend"), "higher-timeframe-alignment": ("Higher-Timeframe Alignment", "trend"), "adx-trend-filter": ("ADX Trend Filter", "trend"), "parabolic-sar-trail": ("Parabolic SAR Trail", "trend"), "supertrend": ("Supertrend", "trend"), "ichimoku-cloud-breakout": ("Ichimoku Cloud Breakout", "breakout"), "pivot-point-reversal": ("Pivot Point Reversal", "reversion"), "fibonacci-retracement": ("Fibonacci Retracement", "reversion"), "fibonacci-extension": ("Fibonacci Extension", "breakout"), "vwap-bounce": ("VWAP Bounce", "reversion"), "vwap-fade": ("VWAP Fade", "reversion"), "anchored-vwap": ("Anchored VWAP", "trend"), "volume-breakout": ("Volume Breakout", "volume"), "relative-volume-spike": ("Relative Volume Spike", "volume"), "accumulation-distribution": ("Accumulation/Distribution", "volume"), "on-balance-volume": ("On-Balance Volume", "volume"), "volume-profile-node": ("Volume Profile Node", "volume"), "gap-and-go": ("Gap and Go", "breakout"), "gap-fill": ("Gap Fill", "reversion"), "inside-bar-breakout": ("Inside Bar Breakout", "breakout"), "pin-bar-reversal": ("Pin Bar Reversal", "reversion"), "engulfing-reversal": ("Engulfing Reversal", "reversion"), "three-bar-reversal": ("Three-Bar Reversal", "reversion"), "bull-flag": ("Bull Flag", "breakout"), "bear-flag": ("Bear Flag", "breakout"), "ascending-triangle": ("Ascending Triangle", "breakout"), "descending-triangle": ("Descending Triangle", "breakout"), "cup-and-handle": ("Cup and Handle", "breakout"), "head-and-shoulders": ("Head and Shoulders", "reversion"), "double-top": ("Double Top", "reversion"), "double-bottom": ("Double Bottom", "reversion"), "mean-reversion-z-score": ("Mean Reversion Z-Score", "reversion"), "pairs-spread-reversion": ("Pairs Spread Reversion", "needs_secondary_symbol"), "seasonality-window": ("Seasonality Window", "needs_history"), "relative-strength-rotation": ("Relative Strength Rotation", "needs_secondary_symbol"), "atr-volatility-breakout": ("ATR Volatility Breakout", "volatility"), "atr-trailing-exit": ("ATR Trailing Exit", "volatility"), "range-expansion": ("Range Expansion", "volatility"), "market-structure-shift": ("Market Structure Shift", "trend"), "liquidity-sweep-reversal": ("Liquidity Sweep Reversal", "reversion"), "fair-value-gap-retest": ("Fair Value Gap Retest", "reversion"),
}


def definition_for(slug: str) -> dict | None:
    if slug == "vwap-reclaim":
        return None
    value = STRATEGIES.get(slug)
    if not value:
        return None
    return {"slug": slug, "name": value[0], "version": 1, "engine": value[1], "default_window_bars": 20}


def catalog_payload(slug: str, bars: list[Bar], entry_price: Decimal, direction: str) -> dict:
    definition = definition_for(slug)
    if not definition:
        raise ValueError("unknown_strategy")
    engine = definition["engine"]
    if engine == "needs_secondary_symbol":
        values = [RuleEvaluationValue("secondary_symbol_context", None, "Add a comparison symbol in strategy settings", 100, RuleResult.INSUFFICIENT_DATA, True)]
    elif engine == "needs_history":
        values = [RuleEvaluationValue("multi_session_history", str(len(bars)), "Multi-session historical data", 100, RuleResult.INSUFFICIENT_DATA, True)]
    elif len(bars) < 21:
        values = [RuleEvaluationValue("market_history", str(len(bars)), ">= 21 completed bars", 100, RuleResult.INSUFFICIENT_DATA, True)]
    else:
        label: str
        measurement: str
        target: str
        closes = [bar.close for bar in bars]
        highs = [bar.high for bar in bars]
        lows = [bar.low for bar in bars]
        fast, slow = ema(closes, 9)[-1], ema(closes, 20)[-1]
        gains = [max(closes[index] - closes[index - 1], Decimal("0")) for index in range(1, len(closes))]
        losses = [max(closes[index - 1] - closes[index], Decimal("0")) for index in range(1, len(closes))]
        average_gain = sum(gains[-14:], Decimal("0")) / Decimal("14")
        average_loss = sum(losses[-14:], Decimal("0")) / Decimal("14")
        rsi = Decimal("100") if average_loss == 0 else Decimal("100") - (Decimal("100") / (Decimal("1") + average_gain / average_loss))
        is_long = direction == "long"
        if engine == "breakout":
            threshold = max(highs[-21:-1]) if is_long else min(lows[-21:-1])
            passed = entry_price > threshold if is_long else entry_price < threshold
            label, measurement, target = "default 20-bar breakout", f"{entry_price:.4f}", f"{'>' if is_long else '<'} {threshold:.4f}"
        elif engine == "trend":
            passed = fast > slow if is_long else fast < slow
            label, measurement, target = "default EMA trend alignment", f"EMA9 {fast:.4f} / EMA20 {slow:.4f}", "EMA9 above EMA20" if is_long else "EMA9 below EMA20"
        elif engine == "reversion":
            passed = rsi <= Decimal("35") if is_long else rsi >= Decimal("65")
            label, measurement, target = "default mean-reversion zone", f"RSI14 {rsi:.2f}", "RSI14 <= 35" if is_long else "RSI14 >= 65"
        elif engine == "volume":
            value = relative_volume(bars)
            passed = value is not None and value >= Decimal("1.50")
            label, measurement, target = "default relative-volume confirmation", f"RVOL {value:.2f}" if value is not None else "RVOL unavailable", "RVOL >= 1.50"
        else:
            current_range = highs[-1] - lows[-1]
            prior_range = sum((highs[index] - lows[index] for index in range(len(bars) - 21, len(bars) - 1)), Decimal("0")) / Decimal("20")
            passed = current_range >= prior_range * Decimal("1.25")
            label, measurement, target = "default range-expansion confirmation", f"{current_range:.4f}", f">= {(prior_range * Decimal('1.25')):.4f}"
        values = [RuleEvaluationValue(label, measurement, target, 100, RuleResult.PASS if passed else RuleResult.FAIL, True)]
    payload = result_payload(values)
    payload["feedback"] = [{"rule": value.rule, "category": "matched" if value.result == RuleResult.PASS else "missed" if value.result == RuleResult.FAIL else "review", "sentence": f"{definition['name']} used its documented default {definition['engine'].replace('_', ' ')} rule profile."} for value in values]
    return payload
