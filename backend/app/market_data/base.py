from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Bar:
    start: datetime
    end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class Session:
    opens_at: datetime
    closes_at: datetime
    timezone: str


@dataclass(frozen=True)
class InstrumentMetadata:
    symbol: str
    asset_type: str
    exchange: str


class MarketDataError(RuntimeError):
    code = "provider_error"


class MarketDataRateLimited(MarketDataError):
    code = "rate_limited"


class MarketDataMalformed(MarketDataError):
    code = "malformed_payload"


class MarketDataTimeout(MarketDataError):
    code = "timeout"


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    async def get_bars(self, instrument: str, start: datetime, end: datetime, timeframe: str) -> list[Bar]: ...

    @abstractmethod
    async def get_quote_context(self, instrument: str, at: datetime) -> dict[str, Decimal | str]: ...

    @abstractmethod
    async def get_session(self, instrument: str, at: datetime) -> Session: ...

    @abstractmethod
    async def get_instrument_metadata(self, instrument: str) -> InstrumentMetadata: ...

    @abstractmethod
    async def get_market_context(self, instrument: str, at: datetime) -> dict[str, Decimal | str]: ...
