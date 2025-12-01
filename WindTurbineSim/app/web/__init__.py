"""
Web package.

Contains the FastAPI application, API routers and web UI assets.
"""

from .main_app import create_app

__all__ = ["create_app"]
