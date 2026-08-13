from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest
from app.imports.csv_parser import (
    ImportValidationError,
    detect_mapping,
    parse_executions,
    parse_decimal,
    parse_timestamp,
    preview,
)
from app.imports.holdings_parser import parse_holdings
from app.imports.reconstruction import reconstruct

FIXTURE = Path(__file__).parents[1] / "fixtures" / "executions.csv"
SCHWAB_FIXTURE = Path(__file__).parents[1] / "fixtures" / "schwab_transactions.csv"


def test_alias_mapping_and_preview_non_mutating():
    data = FIXTURE.read_bytes()
    result = preview(data, 100_000, 100)
    assert result["confidence"] == "high"
    assert result["suggested_mapping"]["executed_at"] == "Execution Time"
    assert len(result["preview"]) == 5


def test_date_first_timestamp_with_time_and_meridiem_uses_timezone():
    parsed = parse_timestamp("08/07/2026 9:43 AM", "America/New_York")
    assert parsed.isoformat() == "2026-08-07T13:43:00+00:00"


def test_binary_and_size_limits():
    with pytest.raises(ImportValidationError, match="binary"):
        preview(b"symbol\x00value", 100, 10)
    with pytest.raises(ImportValidationError, match="upload limit"):
        preview(b"abc", 2, 10)


def test_required_mapping_is_detected():
    result = detect_mapping(["Ticker", "Action", "Filled", "Avg Price", "Exec Time"])
    assert set(result) >= {"symbol", "side", "quantity", "price", "executed_at"}


def test_schwab_positions_preamble_is_detected_before_row_validation():
    data = b'"Positions for account Example ...475 as of 02:01 PM ET, 2026/08/07"\n\n"Symbol","Description","Qty (Quantity)","Price","Mkt Val (Market Value)","Cost Basis","Asset Type",\n"NVDA","NVIDIA CORP","0.05","222.185","$11.11","$11.10","Equity",\n'
    result = preview(data, 100_000, 100)
    assert result["detected_format"] == "positions_snapshot"
    assert result["validation_issues"][0]["code"] == "positions_snapshot"
    with pytest.raises(ImportValidationError) as value:
        parse_executions(data, {"symbol": "Symbol"}, None, 100_000, 100)
    assert value.value.code == "positions_snapshot"


def test_schwab_positions_parse_as_portfolio_holdings():
    data = b'"Positions for account Example ...475 as of 02:01 PM ET, 2026/08/07"\n\n"Symbol","Description","Qty (Quantity)","Price","Mkt Val (Market Value)","Cost Basis","Asset Type",\n"NVDA","NVIDIA CORP","0.05","222.185","$11.11","$11.10","Equity",\n'
    holdings = parse_holdings(data, "Schwab positions.csv", 100_000, 100)
    assert len(holdings) == 1
    assert holdings[0].source == "portfolio"
    assert holdings[0].symbol == "NVDA"
    assert holdings[0].market_value == Decimal("11.11")


def test_schwab_date_only_ledger_is_blocked_without_fabricating_times():
    data = SCHWAB_FIXTURE.read_bytes()
    result = preview(data, 100_000, 100)
    assert result["detected_format"] == "schwab_transaction_ledger"
    assert result["ignored_nontrade_count"] == 2
    assert any(issue["code"] == "date_only_transactions" for issue in result["validation_issues"])
    with pytest.raises(ImportValidationError, match="execution times"):
        parse_executions(data, result["suggested_mapping"], "America/New_York", 100_000, 100)


def test_schwab_order_status_executes_with_quantity_units_and_time():
    data = b"Symbol,Strategy Name,Name of security,Status,Action,Quantity|Face Value,Price,Timing,Fill Price,Fill Price is Average,Time and Date(ET),Last Activity Date(ET),Reinvest Capital Gains,Order Number\nNVDA,,NVIDIA CORP,Filled,Buy,0.05 Shares,Market,Day,$222.04,No,6:26 PM 08/06/2026,9:43 AM 08/07/2026,,1007507852043\nNVDA,,NVIDIA CORP,Canceled,Buy,0.05 Shares,Market,Day,-,No,9:44 AM 08/07/2026,9:44 AM 08/07/2026,,1007507852044\n"
    result = preview(data, 100_000, 100)
    assert result["confidence"] == "high"
    assert result["suggested_mapping"]["quantity"] == "Quantity|Face Value"
    assert result["suggested_mapping"]["price"] == "Fill Price"
    assert result["suggested_mapping"]["executed_at"] == "Last Activity Date(ET)"
    executions = parse_executions(data, result["suggested_mapping"], "America/New_York", 100_000, 100)
    assert len(executions) == 1
    assert executions[0].symbol == "NVDA"
    assert executions[0].quantity == Decimal("0.05")
    assert executions[0].price == Decimal("222.04")
    assert executions[0].executed_at.isoformat() == "2026-08-07T13:43:00+00:00"
    assert executions[0].external_execution_id == "1007507852043"


def test_dst_ambiguity_and_nonexistence_are_rejected():
    with pytest.raises(ImportValidationError) as ambiguous:
        parse_timestamp("2026-11-01T01:30:00", "America/New_York")
    assert ambiguous.value.code == "ambiguous_local_time"
    with pytest.raises(ImportValidationError) as nonexistent:
        parse_timestamp("2026-03-08T02:30:00", "America/New_York")
    assert nonexistent.value.code == "nonexistent_local_time"


def test_fingerprint_is_deterministic_and_reconstruction_splits_reversal():
    data = FIXTURE.read_bytes()
    mapping = preview(data, 100_000, 100)["suggested_mapping"]
    first = parse_executions(data, mapping, None, 100_000, 100)
    second = parse_executions(data, mapping, None, 100_000, 100)
    assert [value.fingerprint for value in first] == [value.fingerprint for value in second]
    trades = reconstruct(first)
    assert len(trades) == 2
    assert trades[0].direction == "long"
    assert trades[0].opened_quantity == 100
    assert trades[1].direction == "short"
    assert trades[1].opened_quantity == 20
    assert [value.role for value in trades[0].allocations] == ["open", "open", "close", "close"]


def test_malformed_optional_values_are_structured():
    data = b"Symbol,Side,Quantity,Price,Execution Time,Commission\nNVDA,Buy,1,10,2026-08-05T14:00:00Z,nope\n"
    mapping = preview(data, 1000, 10)["suggested_mapping"]
    with pytest.raises(ImportValidationError) as value:
        parse_executions(data, mapping, None, 1000, 10)
    assert value.value.code == "invalid_optional_decimal"
    assert value.value.row == 2


@pytest.mark.parametrize(("raw", "expected"), [
    ("$1,234.50", Decimal("1234.50")),
    ("-$1,234.50", Decimal("-1234.50")),
    ("$-1,234.50", Decimal("-1234.50")),
    ("+42.25", Decimal("42.25")),
    ("(1,234.50)", Decimal("-1234.50")),
])
def test_financial_decimal_formats_are_parsed_strictly(raw, expected):
    assert parse_decimal(raw) == expected


@pytest.mark.parametrize("raw", ["12 shares", "USD 12", "1,23.45", "12.3.4", "1,000x"])
def test_financial_decimal_rejects_mixed_or_malformed_text(raw):
    with pytest.raises(InvalidOperation):
        parse_decimal(raw)


def test_duplicate_mapping_is_rejected():
    data = b"Symbol,Side,Quantity,Price,Execution Time\nNVDA,Buy,1,10,2026-08-05T14:00:00Z\n"
    mapping = preview(data, 1000, 10)["suggested_mapping"]
    mapping["price"] = mapping["quantity"]
    with pytest.raises(ImportValidationError) as value:
        parse_executions(data, mapping, None, 1000, 10)
    assert value.value.code == "duplicate_mapping"


def test_ragged_and_extra_rows_are_structured():
    ragged = b"Symbol,Side,Quantity,Price,Execution Time\nAAPL,Buy,10,200\n"
    with pytest.raises(ImportValidationError) as missing:
        preview(ragged, 1000, 10)
    assert missing.value.code == "invalid_row"
    assert missing.value.row == 2
    extra = b"Symbol,Side,Quantity,Price,Execution Time\nAAPL,Buy,10,200,2026-08-05T14:00:00Z,extra\n"
    with pytest.raises(ImportValidationError) as overflow:
        preview(extra, 1000, 10)
    assert overflow.value.code == "extra_columns"


def test_execution_field_length_is_bounded_with_row_and_field():
    symbol = "A" * 257
    data = f"Symbol,Side,Quantity,Price,Execution Time\n{symbol},Buy,1,10,2026-08-05T14:00:00Z\n".encode()
    mapping = {"symbol": "Symbol", "side": "Side", "quantity": "Quantity", "price": "Price", "executed_at": "Execution Time"}
    with pytest.raises(ImportValidationError) as value:
        parse_executions(data, mapping, None, 100_000, 10)
    assert value.value.code == "field_too_long"
    assert value.value.field == "symbol"
    assert value.value.row == 2


def test_holding_field_length_is_bounded_with_row_and_field():
    data = ("Symbol,Description,Qty (Quantity)\n" + "NVDA," + "x" * 257 + ",1\n").encode()
    with pytest.raises(ImportValidationError) as value:
        parse_holdings(data, "holdings.csv", 100_000, 10)
    assert value.value.code == "field_too_long"
    assert value.value.field == "description"
    assert value.value.row == 2


@pytest.mark.parametrize("data", [
    b"Symbol,Description,Quantity,Price\n",
    b"Symbol,Description,Quantity,Price\nCASH,Cash,100,1\n",
    b"Symbol,Description,Quantity,Price\nNVDA,NVIDIA,0,100\n",
])
def test_empty_holdings_are_rejected(data):
    with pytest.raises(ImportValidationError) as value:
        parse_holdings(data, "positions.csv", 100_000, 10)
    assert value.value.code == "empty_holdings"


def test_schema_aligned_symbol_limit_accepts_32_and_rejects_33():
    mapping = {"symbol": "Symbol", "side": "Side", "quantity": "Quantity", "price": "Price", "executed_at": "Execution Time"}
    valid = ("Symbol,Side,Quantity,Price,Execution Time\n" + "A" * 32 + ",Buy,1,10,2026-08-05T14:00:00Z\n").encode()
    assert len(parse_executions(valid, mapping, None, 100_000, 10)) == 1
    invalid = ("Symbol,Side,Quantity,Price,Execution Time\n" + "A" * 33 + ",Buy,1,10,2026-08-05T14:00:00Z\n").encode()
    with pytest.raises(ImportValidationError) as value:
        parse_executions(invalid, mapping, None, 100_000, 10)
    assert value.value.code == "field_too_long"
    assert value.value.field == "symbol"
