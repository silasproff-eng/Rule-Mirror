import csv
import hashlib
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

ALIASES = {
    "symbol": {"symbol", "ticker", "instrument"},
    "side": {"side", "action", "buy/sell", "order action", "transaction type", "type"},
    "quantity": {"quantity", "quantity face value", "qty", "shares", "filled", "position", "units"},
    "price": {"price", "fill price", "execution price", "avg price", "trade price", "average price"},
    "executed_at": {"execution time", "exec time", "timestamp", "date/time", "filled at", "trade time", "transaction time", "datetime", "date", "time and date et", "last activity date et"},
    "execution_id": {"execution id", "exec id", "fill id", "order number"},
    "commission": {"commission", "commissions"},
    "fees": {"fee", "fees", "fees & comm", "fees and comm"},
    "account_reference": {"account", "account id", "account number", "account #"},
    "asset_type": {"asset type", "asset", "security type"},
}
REQUIRED = {"symbol", "side", "quantity", "price", "executed_at"}
FIELD_LIMITS = {
    "symbol": 32,
    "side": 8,
    "account_reference": 128,
    "asset_type": 20,
    "execution_id": 160,
}
DEFAULT_FIELD_LENGTH = 256
SCHWAB_ORDER_STATUS = {
    "symbol",
    "status",
    "action",
    "quantity face value",
    "fill price",
    "last activity date et",
    "order number",
}


@dataclass(frozen=True)
class NormalizedExecution:
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    executed_at: datetime
    commission: Decimal
    fees: Decimal
    account_reference: str
    asset_type: str
    external_execution_id: str | None
    row_number: int
    row_hash: str
    fingerprint: str


class ImportValidationError(ValueError):
    def __init__(self, code: str, message: str, field: str | None = None, row: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.row = row


def decode_csv(data: bytes, max_bytes: int) -> str:
    if len(data) > max_bytes:
        raise ImportValidationError("file_too_large", "CSV exceeds the upload limit")
    if b"\x00" in data:
        raise ImportValidationError("binary_file", "CSV contains binary data")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ImportValidationError("invalid_encoding", "CSV must use UTF-8 encoding") from error


def normalized_header(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def tabular_csv(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        fields = next(csv.reader([line]), [])
        headers = {normalized_header(value) for value in fields}
        if "symbol" in headers and len(fields) >= 3:
            return "\n".join(lines[index:]), index + 1
    return text, 1


def detect_mapping(headers: Sequence[str]) -> dict[str, str]:
    normalized = {normalized_header(header): header for header in headers}
    if set(normalized) >= SCHWAB_ORDER_STATUS:
        return {
            "symbol": normalized["symbol"],
            "side": normalized["action"],
            "quantity": normalized["quantity face value"],
            "price": normalized["fill price"],
            "executed_at": normalized["last activity date et"],
            "execution_id": normalized["order number"],
        }
    result: dict[str, str] = {}
    if "fill price" in normalized:
        result["price"] = normalized["fill price"]
    if "last activity date et" in normalized:
        result["executed_at"] = normalized["last activity date et"]
    for target, aliases in ALIASES.items():
        if target in result:
            continue
        match = next((normalized[alias] for alias in aliases if alias in normalized), None)
        if match:
            result[target] = match
    return result


def is_positions_snapshot(headers: Sequence[str]) -> bool:
    normalized = {normalized_header(header) for header in headers}
    position_markers = {"market value", "cost basis", "quantity", "current price", "average cost", "description"}
    marker_count = sum(any(marker in header for header in normalized) for marker in position_markers)
    return "symbol" in normalized and marker_count >= 2 and not any(value in header for header in normalized for value in {"side", "action", "buy sell", "execution time", "exec time", "filled at"})


def is_schwab_order_status(headers: Sequence[str]) -> bool:
    return {normalized_header(header) for header in headers} >= SCHWAB_ORDER_STATUS


def preview(data: bytes, max_bytes: int, max_rows: int) -> dict:
    text = decode_csv(data, max_bytes)
    table, header_line = tabular_csv(text)
    reader = csv.DictReader(io.StringIO(table))
    headers = reader.fieldnames or []
    if not headers:
        raise ImportValidationError("empty_file", "CSV must include a header row")
    if is_positions_snapshot(headers):
        return {"detected_format": "positions_snapshot", "confidence": "high", "headers": headers, "suggested_mapping": {}, "validation_issues": [{"code": "positions_snapshot", "message": "This looks like a holdings/positions snapshot. Export account activity or executions with side, quantity, price, and execution time; positions are not fabricated into trades."}], "preview": []}
    mapping = detect_mapping(headers)
    rows = []
    ignored_nontrade_count = 0
    for index, row in enumerate(reader):
        if index >= max_rows:
            raise ImportValidationError("too_many_rows", "CSV exceeds the row limit")
        if None in row:
            raise ImportValidationError("extra_columns", "Row contains more values than the header", row=header_line + index + 1)
        if not any((value or "").strip() for value in row.values()):
            continue
        raw_side = (row.get(mapping.get("side", ""), "") or "").strip().lower()
        raw_symbol = (row.get(mapping.get("symbol", ""), "") or "").strip()
        if not raw_symbol and raw_side not in {"buy", "sell", "b", "s", "bought", "sold"}:
            ignored_nontrade_count += 1
            continue
        for field in REQUIRED & mapping.keys():
            if not (row.get(mapping[field]) or "").strip():
                raise ImportValidationError("invalid_row", f"Required {field} value is missing", field, header_line + index + 1)
        if index < 5:
            rows.append({key: (value or "")[:120] for key, value in row.items()})
    missing = sorted(REQUIRED - mapping.keys())
    issues = [{"code": "missing_mapping", "field": value, "message": f"Map {value}"} for value in missing]
    if mapping.get("executed_at", "").strip().lower() == "date":
        issues.append({"code": "date_only_transactions", "field": "executed_at", "message": "This transaction ledger has dates but no execution times. Export execution timestamps; midnight times are not fabricated."})
    normalized_headers = {normalized_header(header) for header in headers}
    schwab_ledger = {"date", "action", "symbol", "description", "quantity", "price", "amount"} <= normalized_headers
    schwab_order_status = normalized_headers >= SCHWAB_ORDER_STATUS
    return {
        "detected_format": "schwab_order_status" if schwab_order_status else "schwab_transaction_ledger" if schwab_ledger else ("canonical" if not missing else "unknown"),
        "confidence": "high" if not missing else "low",
        "headers": headers,
        "suggested_mapping": mapping,
        "validation_issues": issues,
        "preview": rows,
        "ignored_nontrade_count": ignored_nontrade_count,
    }


def parse_timestamp(value: str, timezone_name: str | None) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        try:
            parsed = datetime.strptime(value.strip(), "%m/%d/%Y")
        except ValueError:
            try:
                parsed = datetime.strptime(value.strip(), "%I:%M %p %m/%d/%Y")
            except ValueError:
                try:
                    parsed = datetime.strptime(value.strip(), "%m/%d/%Y %I:%M %p")
                except ValueError:
                    raise ImportValidationError("invalid_timestamp", "Execution timestamp is invalid", "executed_at") from error
    if parsed.tzinfo:
        return parsed.astimezone(UTC)
    if not timezone_name:
        raise ImportValidationError("timezone_required", "Offset-less timestamps require an IANA timezone", "timezone")
    try:
        zone = ZoneInfo(timezone_name)
    except Exception as error:
        raise ImportValidationError("invalid_timezone", "Timezone must be a valid IANA name", "timezone") from error
    first = parsed.replace(tzinfo=zone, fold=0)
    second = parsed.replace(tzinfo=zone, fold=1)
    roundtrip_first = first.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    roundtrip_second = second.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    if roundtrip_first != parsed and roundtrip_second != parsed:
        raise ImportValidationError("nonexistent_local_time", "Timestamp falls in a daylight-saving gap", "executed_at")
    if first.utcoffset() != second.utcoffset():
        raise ImportValidationError("ambiguous_local_time", "Timestamp is ambiguous during daylight-saving change", "executed_at")
    return first.astimezone(UTC)


def optional_value(row: dict[str, str | None], mapping: dict[str, str], key: str, default: str = "") -> str:
    value = row.get(mapping.get(key, ""), default)
    return value.strip() if value is not None else default


def required_value(row: dict[str, str | None], mapping: dict[str, str], key: str) -> str:
    value = row.get(mapping[key])
    if value is None:
        raise ValueError
    return value.strip()


def validate_field_length(value: str, field: str, row: int | None = None) -> str:
    limit = FIELD_LIMITS.get(field, DEFAULT_FIELD_LENGTH)
    if len(value) > limit:
        raise ImportValidationError("field_too_long", f"{field} exceeds the {limit}-character limit", field, row)
    return value


def parse_decimal(value: str) -> Decimal:
    cleaned = value.strip()
    parenthesized = cleaned.startswith("(") and cleaned.endswith(")")
    if parenthesized:
        cleaned = cleaned[1:-1]
    if not re.fullmatch(r"(?:[+-]?\$?|\$[+-]?)(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", cleaned):
        raise InvalidOperation
    normalized = cleaned.replace("$", "").replace(",", "")
    return Decimal(f"-{normalized}" if parenthesized else normalized)


def parse_executions(data: bytes, mapping: dict[str, str], timezone_name: str | None, max_bytes: int, max_rows: int) -> list[NormalizedExecution]:
    text = decode_csv(data, max_bytes)
    table, header_line = tabular_csv(text)
    headers = csv.DictReader(io.StringIO(table)).fieldnames or []
    if is_positions_snapshot(headers):
        raise ImportValidationError("positions_snapshot", "Holdings snapshots cannot be imported as executions; export account activity instead")
    if detect_mapping(headers).get("executed_at", "").strip().lower() == "date":
        raise ImportValidationError("date_only_transactions", "Transaction ledger has no execution times; export executions with timestamps instead")
    missing = REQUIRED - mapping.keys()
    if missing:
        raise ImportValidationError("missing_mapping", f"Missing required mappings: {', '.join(sorted(missing))}")
    if len(set(mapping.values())) != len(mapping):
        raise ImportValidationError("duplicate_mapping", "Each CSV column can map to only one field", "mapping")
    rows: list[NormalizedExecution] = []
    for row_number, row in enumerate(csv.DictReader(io.StringIO(table)), start=header_line + 1):
        if row_number - header_line > max_rows:
            raise ImportValidationError("too_many_rows", "CSV exceeds the row limit")
        if None in row:
            raise ImportValidationError("extra_columns", "Row contains more values than the header", row=row_number)
        if not any((value or "").strip() for value in row.values()):
            continue
        for field, column in mapping.items():
            validate_field_length((row.get(column) or "").strip(), field, row_number)
        raw_status = (row.get("Status", "") or row.get("status", "") or "").strip().lower()
        if is_schwab_order_status(headers) and raw_status != "filled":
            continue
        raw_side = (row.get(mapping.get("side", ""), "") or "").strip().lower()
        raw_symbol = (row.get(mapping.get("symbol", ""), "") or "").strip()
        if not raw_symbol and raw_side not in {"buy", "sell", "b", "s", "bought", "sold"}:
            continue
        try:
            symbol = required_value(row, mapping, "symbol").upper()
            side_raw = required_value(row, mapping, "side").lower()
            side = "buy" if side_raw in {"buy", "b", "bought"} else "sell" if side_raw in {"sell", "s", "sold"} else ""
            quantity_value = required_value(row, mapping, "quantity")
            if is_schwab_order_status(headers):
                quantity_value = re.sub(r"\s+shares?$", "", quantity_value, flags=re.IGNORECASE)
            quantity = parse_decimal(quantity_value).copy_abs()
            price = parse_decimal(required_value(row, mapping, "price"))
            executed_at = parse_timestamp(required_value(row, mapping, "executed_at"), timezone_name)
            if not symbol or not side or quantity <= 0 or price <= 0:
                raise ValueError
        except (KeyError, InvalidOperation, ValueError) as error:
            raise ImportValidationError("invalid_row", "Required execution value is missing or invalid", row=row_number) from error
        try:
            commission = parse_decimal(optional_value(row, mapping, "commission", "0") or "0")
            fees = parse_decimal(optional_value(row, mapping, "fees", "0") or "0")
        except InvalidOperation as error:
            raise ImportValidationError("invalid_optional_decimal", "Commission and fees must be numeric", "commission", row_number) from error
        account = optional_value(row, mapping, "account_reference", "default") or "default"
        asset_type = optional_value(row, mapping, "asset_type", "stock").lower() or "stock"
        execution_id = optional_value(row, mapping, "execution_id") or None
        normalized = f"{account}|{symbol}|{side}|{quantity}|{price}|{executed_at.isoformat()}|{execution_id or ''}"
        row_text = "|".join(str(value) for value in row.values())
        rows.append(NormalizedExecution(symbol, side, quantity, price, executed_at, commission, fees, account, asset_type, execution_id, row_number, hashlib.sha256(row_text.encode()).hexdigest(), hashlib.sha256(normalized.encode()).hexdigest()))
    return rows
