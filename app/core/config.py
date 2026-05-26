"""Settings cargadas desde .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_token: str = Field(..., alias="TELEGRAM_TOKEN")
    allowed_chat_ids: str = Field("", alias="ALLOWED_CHAT_IDS")

    # LLM
    llm_provider: str = Field("groq", alias="LLM_PROVIDER")
    llm_fallback_order: str = Field(
        "groq,cerebras,mistral,sambanova,nvidia,gemini,openrouter",
        alias="LLM_FALLBACK_ORDER",
    )
    groq_api_key: str = Field("", alias="GROQ_API_KEY")
    cerebras_api_key: str = Field("", alias="CEREBRAS_API_KEY")
    mistral_api_key: str = Field("", alias="MISTRAL_API_KEY")
    nvidia_api_key: str = Field("", alias="NVIDIA_API_KEY")
    sambanova_api_key: str = Field("", alias="SAMBANOVA_API_KEY")
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")
    openrouter_api_key: str = Field("", alias="OPENROUTER_API_KEY")

    # Google Sheets (opcionales)
    google_service_account_file: str = Field("", alias="GOOGLE_SERVICE_ACCOUNT_FILE")
    google_sheet_id: str = Field("", alias="GOOGLE_SHEET_ID")
    google_sheet_tab: str = Field("leads", alias="GOOGLE_SHEET_TAB")

    # Comportamiento
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    max_input_chars: int = Field(2000, alias="MAX_INPUT_CHARS")
    rate_limit_per_minute: int = Field(10, alias="RATE_LIMIT_PER_MINUTE")

    @field_validator("llm_provider")
    @classmethod
    def _valid_provider(cls, v: str) -> str:
        allowed = {"groq", "cerebras", "mistral", "sambanova", "nvidia", "gemini", "openrouter"}
        v = v.strip().lower()
        if v not in allowed:
            raise ValueError(f"LLM_PROVIDER debe ser uno de {sorted(allowed)}, recibido: {v!r}")
        return v

    @property
    def allowed_chat_ids_set(self) -> set[str]:
        return {x.strip() for x in self.allowed_chat_ids.split(",") if x.strip()}

    @property
    def fallback_order_list(self) -> list[str]:
        return [x.strip().lower() for x in self.llm_fallback_order.split(",") if x.strip()]

    @property
    def sheets_enabled(self) -> bool:
        return bool(self.google_service_account_file and self.google_sheet_id)

    def provider_key(self, provider: str) -> str:
        return getattr(self, f"{provider.lower()}_api_key", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
