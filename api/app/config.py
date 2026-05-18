import os
from pathlib import Path
import structlog
from pydantic_settings import BaseSettings
from pydantic import Field

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

log = structlog.get_logger()


class Settings(BaseSettings):
    # LLM
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    claude_model: str = "claude-sonnet-4-6"

    # News sources
    newsapi_key: str = Field(default="", alias="NEWSAPI_KEY")
    finnhub_api_key: str = Field(default="", alias="FINNHUB_API_KEY")
    alphavantage_api_key: str = Field(default="", alias="ALPHAVANTAGE_API_KEY")
    forexfactory_user_agent: str = Field(
        default="NewsImpactAgent/1.0", alias="FOREXFACTORY_USER_AGENT"
    )

    # DB
    database_url: str = Field(default="sqlite+aiosqlite:///./local.db", alias="DATABASE_URL")
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")

    # App
    app_env: str = Field(default="development", alias="APP_ENV")
    refresh_interval_minutes: int = Field(default=5, alias="REFRESH_INTERVAL_MINUTES")
    internal_api_token: str = Field(default="", alias="INTERNAL_API_TOKEN")

    # Feed
    feed_page_size: int = 25

    # Calibration
    neutral_threshold_eurusd: float = Field(default=0.002, alias="NEUTRAL_THRESHOLD_EURUSD")
    neutral_threshold_default: float = Field(default=0.002, alias="NEUTRAL_THRESHOLD_DEFAULT")

    model_config = {"env_file": str(_ENV_FILE), "extra": "ignore", "populate_by_name": True, "env_ignore_empty": True}

    def check_missing_keys(self) -> None:
        warnings = []
        if not self.anthropic_api_key:
            warnings.append("ANTHROPIC_API_KEY — LLM klasifikace bude nedostupná")
        if not self.newsapi_key:
            warnings.append("NEWSAPI_KEY — NewsAPI adaptér přeskočen")
        if not self.finnhub_api_key:
            warnings.append("FINNHUB_API_KEY — Finnhub adaptér přeskočen")
        if not self.alphavantage_api_key:
            warnings.append("ALPHAVANTAGE_API_KEY — AlphaVantage adaptér přeskočen")
        if not self.internal_api_token or self.internal_api_token == "change-me-in-production":
            warnings.append("INTERNAL_API_TOKEN — /api/refresh endpoint není zabezpečen")

        if warnings:
            log.warning("Chybějící konfigurace (aplikace poběží s omezenou funkcionalitou)")
            for w in warnings:
                log.warning("MISSING", key=w)

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.database_url

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
