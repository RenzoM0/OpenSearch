"""
Top-level application package for WindTurbineSim.

This package ties together:
- domain: core models (turbines, messages, attacks, stream config/state)
- infrastructure: OpenSearch client, queues, telemetry sources
- services: streaming orchestration, attack engine, heartbeat monitor
- web: FastAPI app and API routers
"""

from .web import create_app

__all__ = ["create_app"]
