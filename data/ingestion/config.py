"""Environment-driven configuration.

No credential, proxy string or connection string appears in source. Proxy support
is optional: every endpoint is reachable directly.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class IngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_prefix="BIET_",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://biet:biet@localhost:5432/biet"

    http_proxy: str | None = None
    https_proxy: str | None = None

    request_timeout_s: float = Field(default=90.0, gt=0)
    request_retries: int = Field(default=3, ge=1, le=10)
    request_backoff_s: float = Field(default=2.0, gt=0)

    raw_dir: Path = _PROJECT_ROOT / "data" / "raw"
    seed_dir: Path = _PROJECT_ROOT / "data" / "seed"
    corpus_dir: Path = _PROJECT_ROOT / "data" / "corpus"

    @property
    def proxies(self) -> str | None:
        """httpx accepts a single proxy URL; https takes precedence."""
        return self.https_proxy or self.http_proxy


settings = IngestionSettings()
