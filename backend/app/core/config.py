from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────
    app_env: Literal["development", "production", "testing"] = "development"
    app_secret_key: str
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, validation_alias=AliasChoices("APP_PORT", "PORT"))
    allowed_origins: str = (
        "http://localhost:8000,http://127.0.0.1:8000,"
        "http://localhost:5000,http://127.0.0.1:5000,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )
    allowed_hosts: str = "localhost,127.0.0.1"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    # ── Supabase ─────────────────────────────────────────────
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    # ── M-Pesa ───────────────────────────────────────────────
    mpesa_consumer_key: str = ""
    mpesa_consumer_secret: str = ""
    mpesa_shortcode: str = "174379"
    mpesa_passkey: str = ""
    mpesa_callback_url: str = "https://api.kazix.co.ke/v1/mpesa/callback"
    mpesa_env: Literal["sandbox", "production"] = "sandbox"

    @property
    def mpesa_base_url(self) -> str:
        if self.mpesa_env == "production":
            return "https://api.safaricom.co.ke"
        return "https://sandbox.safaricom.co.ke"

    # ── Africa's Talking ─────────────────────────────────────
    at_api_key: str = ""
    at_username: str = "sandbox"
    at_sender_id: str = "KaziX"

    # ── OTP Retry Configuration ──────────────────────────────
    otp_max_retries: int = 3
    otp_initial_backoff_ms: int = 100
    otp_max_backoff_ms: int = 5000
    otp_backoff_multiplier: float = 2.0
    otp_jitter_enabled: bool = True

    # ── Logging ──────────────────────────────────────────────
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — import this everywhere."""
    return Settings()
