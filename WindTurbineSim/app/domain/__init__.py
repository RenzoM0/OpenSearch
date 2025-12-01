"""
Domain package.

Provides core domain models for the WindTurbineSim application:
- WindTurbine & enums
- Turbine messages (telemetry & heartbeat)
- Attack profiles/events
- Streaming configuration & state
"""

from .wind_turbine import WindTurbine, TurbineStatus
from .messages import (
    TurbineMessage,
    TelemetryReading,
    HeartbeatMessage,
    MessageType,
    MessageSource,
    HeartbeatStatus,
)
from .attacks import (
    AttackProfile,
    AttackEvent,
    AttackCategory,
    ManipulationType,
    DurationMode,
    AttackEventStatus,
)
from .stream_models import (
    StreamConfig,
    StreamState,
    StreamStatus,
    ConnectivityStatus,
)

__all__ = [
    # wind_turbine
    "WindTurbine",
    "TurbineStatus",
    # messages
    "TurbineMessage",
    "TelemetryReading",
    "HeartbeatMessage",
    "MessageType",
    "MessageSource",
    "HeartbeatStatus",
    # attacks
    "AttackProfile",
    "AttackEvent",
    "AttackCategory",
    "ManipulationType",
    "DurationMode",
    "AttackEventStatus",
    # stream models
    "StreamConfig",
    "StreamState",
    "StreamStatus",
    "ConnectivityStatus",
]
