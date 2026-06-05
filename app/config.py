from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SKAVA Data Discovery Service"
    env: Literal["dev", "staging", "production"] = "dev"

    database_url: str | None = None
    public_base_url: str | None = None

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    internal_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INTERNAL_API_KEY", "SKAVA_INTERNAL_API_KEY"),
    )
    access_tokens: str | None = None
    federated_src_urls: str | None = None
    federation_timeout_seconds: float = Field(default=2.0, ge=0.1)

    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_timeout: int = Field(default=30, ge=1)
    db_pool_recycle: int = Field(default=1800, ge=30)
    db_connect_retries: int = Field(default=10, ge=1)
    db_connect_retry_delay: float = Field(default=1.5, ge=0.1)

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SKAVA_", extra="ignore")

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        if not self.database_url:
            if self.env == "dev":
                self.database_url = "postgresql+psycopg://skava:skava@localhost:5432/skava"
            else:
                raise ValueError("SKAVA_DATABASE_URL is required for staging/production environments")

        if not self.public_base_url:
            if self.env == "dev":
                self.public_base_url = "http://localhost:8000"
            else:
                raise ValueError("SKAVA_PUBLIC_BASE_URL is required for staging/production environments")

        if self.env == "production" and self.public_base_url.startswith("http://"):
            raise ValueError("SKAVA_PUBLIC_BASE_URL must use https:// in production")

        return self

    @property
    def access_token_set(self) -> set[str]:
        if not self.access_tokens:
            return set()
        return {token.strip() for token in self.access_tokens.split(",") if token.strip()}

    @property
    def federated_sources(self) -> list[str]:
        if not self.federated_src_urls:
            return []
        return [url.strip().rstrip("/") for url in self.federated_src_urls.split(",") if url.strip()]


settings = Settings()
