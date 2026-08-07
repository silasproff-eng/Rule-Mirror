from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.imports.csv_parser import NormalizedExecution


@dataclass
class Allocation:
    fingerprint: str
    quantity: Decimal
    role: str


@dataclass
class ReconstructedTrade:
    symbol: str
    account_reference: str
    direction: str
    opened_at: datetime
    closed_at: datetime | None = None
    opened_quantity: Decimal = Decimal("0")
    allocations: list[Allocation] = field(default_factory=list)


def reconstruct(executions: list[NormalizedExecution]) -> list[ReconstructedTrade]:
    groups: dict[tuple[str, str, str], list[NormalizedExecution]] = {}
    for execution in executions:
        key = (execution.account_reference, execution.symbol, execution.asset_type)
        groups.setdefault(key, []).append(execution)
    trades: list[ReconstructedTrade] = []
    for group in groups.values():
        position = Decimal("0")
        active: ReconstructedTrade | None = None
        for execution in sorted(group, key=lambda value: (value.executed_at, value.row_number)):
            signed = execution.quantity if execution.side == "buy" else -execution.quantity
            if position == 0:
                active = ReconstructedTrade(execution.symbol, execution.account_reference, "long" if signed > 0 else "short", execution.executed_at, opened_quantity=abs(signed))
                active.allocations.append(Allocation(execution.fingerprint, abs(signed), "open"))
                position = signed
                continue
            same_direction = position * signed > 0
            if same_direction:
                assert active is not None
                active.opened_quantity += abs(signed)
                active.allocations.append(Allocation(execution.fingerprint, abs(signed), "open"))
                position += signed
                continue
            closing = min(abs(position), abs(signed))
            assert active is not None
            active.allocations.append(Allocation(execution.fingerprint, closing, "close"))
            remainder = abs(signed) - closing
            position += signed
            if position == 0 or remainder > 0:
                active.closed_at = execution.executed_at
                trades.append(active)
                active = None
            if remainder > 0:
                active = ReconstructedTrade(execution.symbol, execution.account_reference, "long" if signed > 0 else "short", execution.executed_at, opened_quantity=remainder)
                active.allocations.append(Allocation(execution.fingerprint, remainder, "open"))
        if active:
            trades.append(active)
    return trades
