"""Runtime configuration loaded from environment variables."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    captcha_api_key: str = Field("", description="2Captcha/RuCaptcha/Anti-Captcha API key")
    captcha_service_host: str = Field(
        "2captcha.com",
        description="Solver host — swap to rucaptcha.com if needed",
    )
    captcha_poll_interval: int = Field(5, ge=1, le=30)
    captcha_poll_max_tries: int = Field(24, ge=1, le=120)

    host: str = "0.0.0.0"
    port: int = 8080
    grpc_port: int = 50051

    headless: bool = True
    http_proxy: str = ""
    keep_open_seconds: int = Field(0, ge=0, le=120, description="Wait N seconds before closing browser (debug)")
    disable_stealth: bool = Field(False, description="Turn off anti-detect — guarantees Yandex shows the captcha (debug)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
