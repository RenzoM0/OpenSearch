"""
Services package.

Contains application services that implement the core behaviour of the system:
- StreamingService: orchestrates telemetry/heartbeat streaming, queue, attacks, and OpenSearch.
- HeartbeatMonitor: tracks expected heartbeats and connectivity status.
- AttackEngine: applies attack profiles (data manipulation / message suppression).
"""

from .heartbeat_monitor import HeartbeatMonitor
from .attack_engine import AttackEngine
from .streaming_service import StreamingService

__all__ = [
    "HeartbeatMonitor",
    "AttackEngine",
    "StreamingService",
]
