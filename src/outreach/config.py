from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(repr=False)
    gmail_address: str | None = None
    gmail_app_password: SecretStr | None = None
    resume_path: Path | None = None
    local_data_dir: Path = Path(".local")
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_timezone: str = "Asia/Kolkata"

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql+"):
            sslmode = parse_qs(urlsplit(value).query).get("sslmode", [])
            if sslmode != ["require"]:
                raise ValueError("PostgreSQL connections must set sslmode=require")
        return value

    @field_validator("app_host")
    @classmethod
    def local_host_only(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("APP_HOST must be a loopback address")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
