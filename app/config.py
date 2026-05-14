from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    app_name: str = "NewsPin ABSA API"
    app_env: str = "local"
    api_key: str = ""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = Field(default=60, ge=5, le=180)

    max_snippets_default: int = Field(default=12, ge=1, le=50)
    max_snippets_limit: int = Field(default=30, ge=1, le=100)

    preprocess_version: str = "news_v2_snippet_rules_v1"

    # MVP uses Gemini as the inference engine. A future KoELECTRA provider can
    # flip these values after loading Model A/B in lifespan startup.
    mode: str = "gemini-api"
    local_model: bool = False
    model_loaded: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
