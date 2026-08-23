"""Environment-driven configuration.

No credential, connection string or proxy appears in source (non-negotiable 4).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_prefix="BIET_",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://biet:biet@localhost:5432/biet"
    sql_echo: bool = False


settings = ApiSettings()
