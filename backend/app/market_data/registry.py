from app.core.config import Settings
from app.market_data.base import MarketDataProvider
from app.market_data.mock import MockMarketDataProvider
from app.market_data.twelve_data import TwelveDataProvider


def provider_registry(settings: Settings) -> dict[str, MarketDataProvider]:
    return {
        "mock": MockMarketDataProvider(),
        "twelve_data": TwelveDataProvider(settings.twelve_data_api_key, settings.twelve_data_base_url, settings.twelve_data_timeout_seconds),
    }


def configured_provider(settings: Settings) -> MarketDataProvider:
    if settings.market_data_provider == "twelve_data" and not settings.twelve_data_api_key:
        raise RuntimeError("TWELVE_DATA_API_KEY is required when Twelve Data is enabled")
    try:
        return provider_registry(settings)[settings.market_data_provider]
    except KeyError as error:
        raise RuntimeError("Unknown market data provider") from error
