"""
Configuration package for WindTurbineSim.

Provides application settings loaded from environment variables / .env.
"""

from .settings import AppSettings, get_settings

__all__ = ["AppSettings", "get_settings"]
