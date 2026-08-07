from datetime import UTC, datetime

import httpx
import pytest
from app.market_data.base import (
    MarketDataError,
    MarketDataMalformed,
    MarketDataRateLimited,
    MarketDataTimeout,
)
from app.market_data.twelve_data import TwelveDataProvider


def provider(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TwelveDataProvider("secret", "https://example.test", 0.1, client)


@pytest.mark.asyncio
async def test_successful_bars_are_normalized():
    value = provider(lambda request: httpx.Response(200, json={"values": [{"datetime": "2026-08-05T14:00:00", "open": "1", "high": "2", "low": "0.5", "close": "1.5", "volume": "100"}]}))
    bars = await value.get_bars("NVDA", datetime(2026, 8, 5, tzinfo=UTC), datetime(2026, 8, 6, tzinfo=UTC), "1min")
    assert bars[0].close == 1.5


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "error"), [(429, MarketDataRateLimited), (503, MarketDataError)])
async def test_http_errors_are_typed(status, error):
    value = provider(lambda request: httpx.Response(status, json={}))
    with pytest.raises(error):
        await value.get_bars("NVDA", datetime.now(UTC), datetime.now(UTC), "1min")


@pytest.mark.asyncio
async def test_malformed_payload_is_typed():
    value = provider(lambda request: httpx.Response(200, json={"values": [{"close": "bad"}]}))
    with pytest.raises(MarketDataMalformed):
        await value.get_bars("NVDA", datetime.now(UTC), datetime.now(UTC), "1min")


@pytest.mark.asyncio
async def test_timeout_is_typed():
    def timeout(request):
        raise httpx.ReadTimeout("late", request=request)
    value = provider(timeout)
    with pytest.raises(MarketDataTimeout):
        await value.get_bars("NVDA", datetime.now(UTC), datetime.now(UTC), "1min")
