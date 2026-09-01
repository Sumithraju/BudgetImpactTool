"""Environment-driven configuration.

No credential, connection string or proxy appears in source (non-negotiable 4).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
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

    @field_validator("database_url")
    @classmethod
    def _name_the_driver(cls, url: str) -> str:
        """Pin psycopg 3 when the URL does not name a driver.

        Managed Postgres hands out a bare `postgresql://…` (Heroku still says
        `postgres://`), and SQLAlchemy reads a URL with no driver as psycopg 2
        — which this project does not install. The failure surfaces a long way
        from its cause: `ModuleNotFoundError: No module named 'psycopg2'`
        raised out of the dialect, on a connection string that looks correct
        in the dashboard.

        A URL that already names a driver is left exactly as given, so
        anything deliberate still wins.
        """
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


settings = ApiSettings()
