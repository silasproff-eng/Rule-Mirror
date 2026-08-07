from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.market_data.base import Bar, InstrumentMetadata, MarketDataProvider, Session


class MockMarketDataProvider(MarketDataProvider):
    name = "mock"

    async def get_bars(self, instrument: str, start: datetime, end: datetime, timeframe: str) -> list[Bar]:
        bars = []
        cursor = start.replace(second=0, microsecond=0)
        index = 0
        while cursor < end:
            base = Decimal("100") + Decimal(index) * Decimal("0.08")
            close = base - Decimal("0.18") if index < 22 else base + Decimal("0.34")
            volume = Decimal("1000") if index < 22 else Decimal("1900")
            bars.append(Bar(cursor, cursor + timedelta(minutes=1), base, max(base, close) + Decimal("0.12"), min(base, close) - Decimal("0.10"), close, volume))
            cursor += timedelta(minutes=1)
            index += 1
        return bars

    async def get_quote_context(self, instrument: str, at: datetime) -> dict[str, Decimal | str]:
        return {"spread": Decimal("0.02"), "source": self.name}

    async def get_session(self, instrument: str, at: datetime) -> Session:
        zone = ZoneInfo("America/New_York")
        day = at.astimezone(zone).date()
        opens = datetime(day.year, day.month, day.day, 9, 30, tzinfo=zone).astimezone(UTC)
        closes = datetime(day.year, day.month, day.day, 16, 0, tzinfo=zone).astimezone(UTC)
        return Session(opens, closes, "America/New_York")

    async def get_instrument_metadata(self, instrument: str) -> InstrumentMetadata:
        return InstrumentMetadata(instrument, "stock", "NASDAQ")

    async def get_market_context(self, instrument: str, at: datetime) -> dict[str, Decimal | str]:
        return {"benchmark_alignment": "not_required", "source": self.name}
