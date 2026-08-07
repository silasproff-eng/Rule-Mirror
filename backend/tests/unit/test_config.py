import pytest
from app.core.config import Settings
from app.market_data.mock import MockMarketDataProvider
from pydantic import ValidationError


def test_production_rejects_default_or_weak_secret():
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="local-development-only-change-me")
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="short")


@pytest.mark.asyncio
async def test_mock_sessions_follow_est_and_edt():
    provider = MockMarketDataProvider()
    summer = await provider.get_session("NVDA", __import__("datetime").datetime(2026, 8, 5, 14, tzinfo=__import__("datetime").UTC))
    winter = await provider.get_session("NVDA", __import__("datetime").datetime(2026, 1, 5, 15, tzinfo=__import__("datetime").UTC))
    assert summer.opens_at.hour == 13
    assert winter.opens_at.hour == 14
