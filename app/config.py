from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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

    # "gemini-api" keeps the MVP fallback. "local-koelectra" loads Model A/B
    # once in FastAPI lifespan startup.
    mode: str = "gemini-api"
    model_package_path: str = "./models"
    model_a_path: str = ""
    model_b_path: str = ""
    model_version: str = "koelectra-absa-v3"

    local_model: bool = False
    model_loaded: bool = False

    @property
    def resolved_model_a_path(self) -> Path:
        return Path(self.model_a_path or Path(self.model_package_path) / "model_a")

    @property
    def resolved_model_b_path(self) -> Path:
        return Path(self.model_b_path or Path(self.model_package_path) / "model_b")

    @property
    def resolved_label_map_path(self) -> Path:
        return Path(self.model_package_path) / "label_map.json"

    @property
    def resolved_thresholds_path(self) -> Path:
        return Path(self.model_package_path) / "thresholds.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
