from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.indicators import cumulative_vwap, ema, relative_volume
from app.market_data.base import Bar
from app.strategies.vwap_reclaim import RuleEvaluationValue, RuleResult, evaluate, feedback, score


def bar(index: int, close: str, volume: str = "100") -> Bar:
    start = datetime(2026, 8, 5, 13, 30, tzinfo=UTC) + timedelta(minutes=index)
    value = Decimal(close)
    return Bar(start, start + timedelta(minutes=1), value, value + Decimal("1"), value - Decimal("1"), value, Decimal(volume))


def test_hand_calculated_indicators():
    bars = [bar(0, "10", "100"), bar(1, "12", "200")]
    assert cumulative_vwap(bars)[-1] == Decimal("34") / Decimal("3")
    assert ema([Decimal("10"), Decimal("12")], 3) == [Decimal("10"), Decimal("11.0")]
    assert relative_volume([bar(i, "10", "100") for i in range(20)] + [bar(20, "10", "200")]) == Decimal("2")


def test_no_lookahead_ignores_incomplete_entry_bar():
    bars = [bar(i, "100" if i < 21 else "102", "200" if i == 21 else "100") for i in range(23)]
    entry = bars[22].start + timedelta(seconds=30)
    result = evaluate(bars, entry, Decimal("102"))
    assert all(value.measurement != "23" for value in result)


def test_missing_critical_data_withholds_score():
    evaluations = [RuleEvaluationValue("history", None, ">=21", 100, RuleResult.INSUFFICIENT_DATA, True)]
    assert score(evaluations) is None


def test_failed_critical_rule_caps_score():
    evaluations = [RuleEvaluationValue("critical", "false", "true", 1, RuleResult.FAIL, True), RuleEvaluationValue("other", "true", "true", 99, RuleResult.PASS)]
    assert score(evaluations) == 59


def test_feedback_sentences_retain_rule_provenance():
    evaluations = [RuleEvaluationValue("reclaim_relative_volume", "1.2", ">=1.5", 15, RuleResult.FAIL)]
    result = feedback(evaluations)
    assert result[0]["rule"] == "reclaim_relative_volume"
    assert "volume" in result[0]["sentence"].lower()
