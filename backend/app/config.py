"""Settings, read from the environment once and checked at startup."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(min_length=32)
    jwt_ttl_minutes: int = Field(default=480, ge=5, le=7 * 24 * 60)
    cookie_secure: bool = False

    database_url: str = "sqlite:///./data/deskpilot.db"
    checkpoint_path: str = "./data/checkpoints.db"

    # Any OpenAI-compatible chat API: llama.cpp (default), Groq, Gemini, Ollama, Claude.
    llm_base_url: str = "http://localhost:8090/v1"
    llm_model: str = "local"
    llm_api_key: str = "not-needed"
    llm_timeout_seconds: float = 180

    # "llm" asks the chat model, "remote" calls the fine-tuned router service (ROUTER_URL),
    # "keywords" needs no model at all (tests, offline demos).
    router_mode: Literal["llm", "remote", "keywords"] = "llm"
    router_url: str | None = None

    qdrant_url: str = ":memory:"
    embed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    kb_min_score: float = Field(default=0.45, ge=0, le=1)

    # Refunds above this need a manager; support staff can refund up to it.
    support_refund_limit: float = Field(default=50, ge=0)

    voice_enabled: bool = False
    whisper_model: str = "base"
    piper_voices_dir: str = "./data/voices"

    cors_origins: list[str] = []

    @field_validator("jwt_secret")
    @classmethod
    def _no_placeholder(cls, value: str) -> str:
        if "change-me" in value:
            raise ValueError("JWT_SECRET still holds the placeholder from .env.example")
        return value

    @field_validator("router_url")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.rstrip("/") if value else None


@lru_cache
def get_settings() -> Settings:
    settings = Settings()  # type: ignore[call-arg]
    if settings.router_mode == "remote" and not settings.router_url:
        raise ValueError("ROUTER_MODE=remote needs ROUTER_URL")
    return settings
