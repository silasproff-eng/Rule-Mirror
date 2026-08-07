from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.analytics.indicators import cumulative_vwap, ema, relative_volume
from app.market_data.base import Bar


class RuleResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class RuleEvaluationValue:
    rule: str
    measurement: str | None
    threshold: str | None
    weight: int
    result: RuleResult
    critical: bool = False


DEFAULT_DEFINITION = {
    "slug": "vwap-reclaim",
    "version": 1,
    "maximum_bars_after_reclaim": 3,
    "require_ema_alignment": True,
    "rvol_threshold": "1.50",
    "permitted_start": "09:35",
    "permitted_end": "11:30",
    "maximum_vwap_extension_percent": "0.50",
    "weights": {"prior_below": 20, "reclaim": 25, "timing": 15, "ema": 15, "rvol": 15, "time": 5, "extension": 5},
}


def evaluate(bars: list[Bar], execution_time: datetime, entry_price: Decimal, definition: dict = DEFAULT_DEFINITION) -> list[RuleEvaluationValue]:
    completed = [bar for bar in bars if bar.end <= execution_time]
    weights = definition["weights"]
    if len(completed) < 21:
        return [RuleEvaluationValue("market_history", str(len(completed)), ">= 21 completed bars", 100, RuleResult.INSUFFICIENT_DATA, True)]
    vwaps = cumulative_vwap(completed)
    closes = [bar.close for bar in completed]
    reclaim_indexes = [index for index in range(1, len(completed)) if closes[index - 1] < vwaps[index - 1] and closes[index] > vwaps[index]]
    reclaim_index = reclaim_indexes[-1] if reclaim_indexes else None
    prior = any(closes[index] < vwaps[index] for index in range(max(0, len(completed) - 8), len(completed) - 1))
    reclaimed = reclaim_index is not None
    bars_after = len(completed) - 1 - reclaim_index if reclaim_index is not None else None
    ema9 = ema(closes, 9)[-1]
    ema20 = ema(closes, 20)[-1]
    rvol = relative_volume(completed)
    extension = (entry_price - vwaps[-1]) / vwaps[-1] * Decimal("100")
    minute = execution_time.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M")
    evaluations = [
        RuleEvaluationValue("prior_close_below_vwap", str(prior).lower(), "true", weights["prior_below"], RuleResult.PASS if prior else RuleResult.FAIL, True),
        RuleEvaluationValue("completed_close_reclaimed_vwap", str(reclaimed).lower(), "true", weights["reclaim"], RuleResult.PASS if reclaimed else RuleResult.FAIL, True),
        RuleEvaluationValue("entry_within_reclaim_bars", str(bars_after) if bars_after is not None else None, f"<= {definition['maximum_bars_after_reclaim']}", weights["timing"], RuleResult.PASS if bars_after is not None and bars_after <= definition["maximum_bars_after_reclaim"] else RuleResult.FAIL),
        RuleEvaluationValue("ema_9_above_20", f"{ema9:.4f} / {ema20:.4f}", "EMA9 > EMA20", weights["ema"], RuleResult.PASS if ema9 > ema20 else RuleResult.FAIL) if definition["require_ema_alignment"] else RuleEvaluationValue("ema_9_above_20", None, "disabled", weights["ema"], RuleResult.NOT_APPLICABLE),
        RuleEvaluationValue("reclaim_relative_volume", f"{rvol:.2f}" if rvol is not None else None, f">= {definition['rvol_threshold']}", weights["rvol"], RuleResult.PASS if rvol is not None and rvol >= Decimal(definition["rvol_threshold"]) else RuleResult.INSUFFICIENT_DATA if rvol is None else RuleResult.FAIL),
        RuleEvaluationValue("permitted_entry_time", minute, f"{definition['permitted_start']}–{definition['permitted_end']}", weights["time"], RuleResult.PASS if definition["permitted_start"] <= minute <= definition["permitted_end"] else RuleResult.FAIL),
        RuleEvaluationValue("maximum_vwap_extension", f"{extension:.2f}%", f"<= {definition['maximum_vwap_extension_percent']}%", weights["extension"], RuleResult.PASS if extension <= Decimal(definition["maximum_vwap_extension_percent"]) else RuleResult.FAIL),
    ]
    return evaluations


def score(evaluations: list[RuleEvaluationValue]) -> int | None:
    if any(value.critical and value.result == RuleResult.INSUFFICIENT_DATA for value in evaluations):
        return None
    applicable = [value for value in evaluations if value.result not in {RuleResult.NOT_APPLICABLE, RuleResult.INSUFFICIENT_DATA}]
    total = sum(value.weight for value in applicable)
    earned = sum(value.weight for value in applicable if value.result == RuleResult.PASS)
    result = round(earned * 100 / total) if total else None
    if result is not None and any(value.critical and value.result == RuleResult.FAIL for value in evaluations):
        result = min(result, 59)
    return result


def feedback(evaluations: list[RuleEvaluationValue]) -> list[dict[str, str]]:
    templates = {
        ("prior_close_below_vwap", RuleResult.PASS): ("matched", "Price was below VWAP before the reclaim."),
        ("completed_close_reclaimed_vwap", RuleResult.PASS): ("matched", "A completed minute closed back above VWAP before entry."),
        ("entry_within_reclaim_bars", RuleResult.FAIL): ("missed", "Entry occurred outside the configured reclaim-bar window."),
        ("ema_9_above_20", RuleResult.FAIL): ("missed", "EMA 9 was not above EMA 20 at entry."),
        ("reclaim_relative_volume", RuleResult.FAIL): ("missed", "Reclaim volume was below the configured threshold."),
        ("reclaim_relative_volume", RuleResult.INSUFFICIENT_DATA): ("review", "Relative volume could not be evaluated with the available history."),
        ("maximum_vwap_extension", RuleResult.FAIL): ("review", "Entry was more extended from VWAP than the strategy allows."),
    }
    return [{"rule": value.rule, "category": templates[(value.rule, value.result)][0], "sentence": templates[(value.rule, value.result)][1]} for value in evaluations if (value.rule, value.result) in templates]


def result_payload(evaluations: list[RuleEvaluationValue], sample_count: int = 0) -> dict:
    return {"score": score(evaluations), "rules": [{**asdict(value), "result": value.result.value} for value in evaluations], "feedback": feedback(evaluations), "comparison": {"status": "insufficient_sample", "minimum": 20, "available": sample_count, "message": "At least 20 analyzed trades are required for comparison with your history."}}
