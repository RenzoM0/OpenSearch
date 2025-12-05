from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional

from dotenv import load_dotenv

# Load variables from .env file into environment (if present)
load_dotenv()


@dataclass
class AppSettings:
    """
    Application settings loaded from environment variables.

    Values here correspond to the .env file:
    - APP_ENV
    - OPENSEARCH_HOST / PORT / SCHEME / USERNAME / PASSWORD / INDEX
    - STREAM_DATA_INTERVAL_SECONDS / STREAM_HEARTBEAT_INTERVAL_SECONDS / STREAM_MODE
    - LOSS_CONTACT_DURATION_SECONDS (for the Loss of Contact attack)
    """

    # --- App environment ---
    app_env: str = os.getenv("APP_ENV", "development")

    # --- OpenSearch connection ---
    opensearch_host: str = os.getenv("OPENSEARCH_HOST", "localhost")
    opensearch_port: int = int(os.getenv("OPENSEARCH_PORT", "9200"))
    opensearch_scheme: str = os.getenv("OPENSEARCH_SCHEME", "http")

    opensearch_username: Optional[str] = os.getenv("OPENSEARCH_USERNAME") or None
    opensearch_password: Optional[str] = os.getenv("OPENSEARCH_PASSWORD") or None

    # Default index for turbine data
    opensearch_index: str = os.getenv("OPENSEARCH_INDEX", "windturbine")

    # --- Streaming defaults ---
    stream_data_interval_seconds: int = int(
        os.getenv("STREAM_DATA_INTERVAL_SECONDS", "5")
    )
    stream_heartbeat_interval_seconds: int = int(
        os.getenv("STREAM_HEARTBEAT_INTERVAL_SECONDS", "2")
    )
    stream_mode: str = os.getenv("STREAM_MODE", "SYNTHETIC").upper()

    # --- Attack defaults ---
    # Default duration (in seconds) for the Loss of Contact attack profile.
    loss_contact_duration_seconds: int = int(
        os.getenv("LOSS_CONTACT_DURATION_SECONDS", "600")
    )


_settings_instance: Optional[AppSettings] = None


def get_settings() -> AppSettings:
    """
    Return a singleton AppSettings instance.

    Use this from the rest of the application:

        from config import get_settings
        settings = get_settings()
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = AppSettings()
    return _settings_instance
