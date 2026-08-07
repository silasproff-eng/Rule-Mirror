from decimal import Decimal

from app.market_data.base import Bar


def typical_price(bar: Bar) -> Decimal:
    return (bar.high + bar.low + bar.close) / Decimal("3")


def cumulative_vwap(bars: list[Bar]) -> list[Decimal]:
    total_value = Decimal("0")
    total_volume = Decimal("0")
    values = []
    for bar in bars:
        total_value += typical_price(bar) * bar.volume
        total_volume += bar.volume
        values.append(total_value / total_volume)
    return values


def ema(values: list[Decimal], period: int) -> list[Decimal]:
    if not values:
        return []
    multiplier = Decimal("2") / Decimal(period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def relative_volume(bars: list[Bar], lookback: int = 20) -> Decimal | None:
    if len(bars) <= lookback:
        return None
    baseline = sum((bar.volume for bar in bars[-lookback - 1:-1]), Decimal("0")) / Decimal(lookback)
    return bars[-1].volume / baseline if baseline else None
