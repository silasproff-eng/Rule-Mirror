from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_display_name: str = "RuleMirror"
    database_url: str = "sqlite:///./strategy_audit.db"
    secret_key: str = "local-development-only-change-me"
    environment: str = "development"
    cors_origins: str = "http://localhost:3000,http://localhost:8080"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    market_data_provider: str = "mock"
    twelve_data_api_key: str = ""
    twelve_data_base_url: str = "https://api.twelvedata.com"
    twelve_data_timeout_seconds: float = 8.0
    analysis_run_stale_seconds: int = 120
    max_csv_bytes: int = 2_000_000
    max_csv_rows: int = 20_000
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_secret(self):
        weak = self.secret_key == "local-development-only-change-me" or len(self.secret_key) < 32
        if self.environment != "development" and weak:
            raise ValueError("A strong SECRET_KEY is required outside development")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
