from __future__ import annotations

from functools import lru_cache
from pydantic import BaseSettings


class Settings(BaseSettings):
    # --- App environment ---
    app_env: str = "development"

    # --- OpenSearch connection ---
    opensearch_host: str = "localhost"
    opensearch_port: int = 9200
    opensearch_scheme: str = "http"  # or "https"

    opensearch_username: str | None = None
    opensearch_password: str | None = None

    # Default index for turbine data
    opensearch_index: str = "windturbine"

    # --- Streaming defaults ---
    stream_data_interval_seconds: int = 5
    stream_heartbeat_interval_seconds: int = 2
    stream_mode: str = "SYNTHETIC"  # or "REPLAY_DATASET", "MIXED"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    Usage:
        from config import get_settings
        settings = get_settings()
    """
    return Settings()
