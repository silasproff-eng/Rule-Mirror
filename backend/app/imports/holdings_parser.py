import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.imports.csv_parser import (
    ImportValidationError,
    decode_csv,
    normalized_header,
    parse_decimal,
    tabular_csv,
)

ALIASES = {
    "symbol": {"symbol", "ticker", "security symbol"},
    "description": {"description", "name", "security", "name of security", "company", "asset name"},
    "quantity": {"quantity", "qty quantity", "qty", "shares", "units", "share quantity"},
    "price": {"price", "current price", "last price", "market price", "share price", "current value per share"},
    "market_value": {"mkt val market value", "market value", "value", "current value", "total value", "amount"},
    "cost_basis": {"cost basis", "total cost", "cost", "avg cost", "average cost"},
    "asset_type": {"asset type", "asset", "type", "security type"},
    "account_reference": {"account", "account number", "account id", "account name"},
}
REQUIRED = {"symbol", "quantity"}


@dataclass(frozen=True)
class NormalizedHolding:
    source: str
    account_reference: str
    symbol: str
    description: str | None
    quantity: Decimal
    price: Decimal | None
    market_value: Decimal | None
    cost_basis: Decimal | None
    asset_type: str


def detect_holding_mapping(headers: Sequence[str]) -> dict[str, str]:
    normalized = {normalized_header(header): header for header in headers}
    result: dict[str, str] = {}
    for target, aliases in ALIASES.items():
        match = next((normalized[alias] for alias in aliases if alias in normalized), None)
        if match:
            result[target] = match
    return result


def optional_decimal(value: str | None) -> Decimal | None:
    if not value or not value.strip() or value.strip() in {"-", "--"}:
        return None
    try:
        return parse_decimal(value)
    except InvalidOperation:
        return None


def parse_holdings(data: bytes, filename: str | None, max_bytes: int, max_rows: int) -> list[NormalizedHolding]:
    text = decode_csv(data, max_bytes)
    table, header_line = tabular_csv(text)
    reader = csv.DictReader(io.StringIO(table))
    headers = reader.fieldnames or []
    mapping = detect_holding_mapping(headers)
    missing = REQUIRED - mapping.keys()
    if missing:
        raise ImportValidationError("missing_holding_mapping", f"Missing required holding mappings: {', '.join(sorted(missing))}")
    source = "portfolio"
    holdings: list[NormalizedHolding] = []
    for row_number, row in enumerate(reader, start=header_line + 1):
        if row_number - header_line > max_rows:
            raise ImportValidationError("too_many_rows", "CSV exceeds the row limit")
        if None in row:
            raise ImportValidationError("extra_columns", "Row contains more values than the header", row=row_number)
        symbol = (row.get(mapping["symbol"]) or "").strip().upper()
        if not symbol or symbol in {"CASH", "USD"}:
            continue
        try:
            quantity = parse_decimal(row.get(mapping["quantity"]) or "")
        except InvalidOperation as error:
            raise ImportValidationError("invalid_row", "Holding quantity is missing or invalid", "quantity", row_number) from error
        if quantity <= 0:
            continue
        price = optional_decimal(row.get(mapping.get("price", "")))
        market_value = optional_decimal(row.get(mapping.get("market_value", "")))
        if market_value is None and price is not None:
            market_value = quantity * price
        description = (row.get(mapping.get("description", ""), "") or "").strip() or None
        account = (row.get(mapping.get("account_reference", ""), "") or "").strip() or source
        asset_type = (row.get(mapping.get("asset_type", ""), "stock") or "stock").strip().lower()
        holdings.append(NormalizedHolding(source, account, symbol, description, quantity, price, market_value, optional_decimal(row.get(mapping.get("cost_basis", ""))), asset_type))
    return holdings
