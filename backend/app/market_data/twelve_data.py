from datetime import UTC, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import httpx

from app.market_data.base import (
    Bar,
    InstrumentMetadata,
    MarketDataError,
    MarketDataMalformed,
    MarketDataProvider,
    MarketDataRateLimited,
    MarketDataTimeout,
    Session,
)


class TwelveDataProvider(MarketDataProvider):
    name = "twelve_data"

    def __init__(self, api_key: str, base_url: str, timeout: float, client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = client

    async def _request(self, path: str, params: dict[str, str]) -> dict:
        values = {**params, "apikey": self.api_key}
        try:
            if self.client:
                response = await self.client.get(f"{self.base_url}{path}", params=values, timeout=self.timeout)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{self.base_url}{path}", params=values, timeout=self.timeout)
        except httpx.TimeoutException as error:
            raise MarketDataTimeout("Market data request timed out") from error
        except httpx.RequestError as error:
            raise MarketDataError("Market data provider could not be reached") from error
        if response.status_code == 429:
            raise MarketDataRateLimited("Market data rate limit reached")
        if response.status_code >= 400:
            raise MarketDataError("Market data provider rejected the request")
        try:
            payload = response.json()
        except ValueError as error:
            raise MarketDataMalformed("Market data response was not valid JSON") from error
        if payload.get("status") == "error":
            raise MarketDataError("Market data provider returned an error")
        return payload

    async def get_bars(self, instrument: str, start: datetime, end: datetime, timeframe: str) -> list[Bar]:
        payload = await self._request("/time_series", {"symbol": instrument, "interval": timeframe, "start_date": start.isoformat(), "end_date": end.isoformat(), "timezone": "UTC", "order": "ASC"})
        try:
            bars = []
            for value in payload["values"]:
                bar_start = datetime.fromisoformat(value["datetime"])
                bar_start = bar_start.replace(tzinfo=UTC) if bar_start.tzinfo is None else bar_start.astimezone(UTC)
                bars.append(Bar(bar_start, bar_start + timedelta(minutes=1), Decimal(value["open"]), Decimal(value["high"]), Decimal(value["low"]), Decimal(value["close"]), Decimal(value["volume"])))
            return bars
        except (KeyError, TypeError, ValueError, InvalidOperation) as error:
            raise MarketDataMalformed("Market data bars were malformed") from error

    async def get_quote_context(self, instrument: str, at: datetime) -> dict[str, Decimal | str]:
        payload = await self._request("/quote", {"symbol": instrument})
        try:
            return {"close": Decimal(payload["close"]), "source": self.name}
        except (KeyError, InvalidOperation) as error:
            raise MarketDataMalformed("Quote context was malformed") from error

    async def get_session(self, instrument: str, at: datetime) -> Session:
        eastern = ZoneInfo("America/New_York")
        local = at.astimezone(eastern)
        if local.weekday() >= 5:
            raise MarketDataError("The trade timestamp is outside regular market sessions")
        opened = datetime.combine(local.date(), time(9, 30), tzinfo=eastern)
        closed = datetime.combine(local.date(), time(16, 0), tzinfo=eastern)
        if local < opened or local > closed:
            raise MarketDataError("The trade timestamp is outside regular market sessions")
        return Session(opened, closed, "America/New_York")

    async def get_instrument_metadata(self, instrument: str) -> InstrumentMetadata:
        payload = await self._request("/symbol_search", {"symbol": instrument})
        try:
            item = payload["data"][0]
            return InstrumentMetadata(item["symbol"], item.get("instrument_type", "stock").lower(), item.get("exchange", "unknown"))
        except (KeyError, IndexError, TypeError) as error:
            raise MarketDataMalformed("Instrument metadata was malformed") from error

    async def get_market_context(self, instrument: str, at: datetime) -> dict[str, Decimal | str]:
        return {"source": self.name, "benchmark_alignment": "not_requested"}
